"""API-layer tests only -- eligibility/scoring/integrity logic is already
covered by the other test files and is NOT re-tested here. These just
verify the FastAPI layer correctly wires uploads into run_pipeline(),
validates input, isolates failures, and never leaks credentials.

No real GitHub or Gemini network calls are made: every test either passes
github_enrichment=false explicitly or overrides settings so scoring stays
deterministic and offline, regardless of what's configured in this
environment's real .env file.
"""

from __future__ import annotations

import io

import pymupdf
import pytest
from fastapi.testclient import TestClient

from resume_screener.api.main import app, settings as app_settings
from resume_screener.config import Settings

client = TestClient(app)


def _make_pdf_bytes(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=10, color=(0, 0, 0))
        y += 14
    data = doc.tobytes()
    doc.close()
    return data


ELIGIBLE_RESUME_LINES = [
    "Jane Doe",
    "jane@example.com",
    "Skills: Python, LangChain, FastAPI, Docker, AWS",
    "Projects",
    "RAG Assistant | Python, LangChain",
    "- Built a retrieval augmented generation pipeline using LangChain",
    "  and a vector database, deployed on AWS with Docker.",
]

INELIGIBLE_RESUME_LINES = [
    "John Smith",
    "john@example.com",
    "Skills: Java, React, Next.js",
    "Projects",
    "Website | Java",
    "- Built a website.",
]


def _resume_file(name: str, lines: list[str]):
    return (name, io.BytesIO(_make_pdf_bytes(lines)), "application/pdf")


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_screen_zero_files_rejected():
    resp = client.post("/api/screen", files=[], data={"github_enrichment": "false"})
    assert resp.status_code in (400, 422)


def test_screen_too_many_files_rejected():
    files = [
        ("resumes", _resume_file(f"r{i}.pdf", ELIGIBLE_RESUME_LINES)) for i in range(51)
    ]
    resp = client.post("/api/screen", files=files, data={"github_enrichment": "false"})
    assert resp.status_code == 400
    assert "maximum is 50" in resp.json()["detail"]


def test_screen_eligible_and_ineligible_candidates(monkeypatch):
    files = [
        ("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES)),
        ("resumes", _resume_file("ineligible.pdf", INELIGIBLE_RESUME_LINES)),
    ]
    resp = client.post(
        "/api/screen",
        files=files,
        data={"scorer": "deterministic", "github_enrichment": "false"},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_files_discovered"] == 2
    assert body["eligible_count"] == 1
    assert body["ineligible_count"] == 1
    assert body["failed_count"] == 0
    assert body["scorer_used"] == "deterministic"

    ranked = body["ranked"]
    assert len(ranked) == 1
    assert ranked[0]["source_file"] == "eligible.pdf"
    assert ranked[0]["candidate"]["name"] == "Jane Doe"
    assert ranked[0]["score"]["total"] > 0
    assert ranked[0]["rank"] == 1

    ineligible = body["ineligible"]
    assert len(ineligible) == 1
    assert ineligible[0]["source_file"] == "ineligible.pdf"
    assert ineligible[0]["eligibility"]["eligible"] is False
    assert ineligible[0]["eligibility"]["rejection_reasons"]


def test_screen_malformed_pdf_recorded_as_failure_not_crash():
    files = [
        ("resumes", ("corrupt.pdf", io.BytesIO(b"%PDF-1.4 not a real pdf body"), "application/pdf")),
        ("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES)),
    ]
    resp = client.post("/api/screen", files=files, data={"github_enrichment": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["failed_count"] == 1
    assert body["eligible_count"] == 1
    failure = next(f for f in body["failures"] if f["source_file"] == "corrupt.pdf")
    assert "/tmp" not in failure["error"] and "resume_screen_" not in failure["error"]


def test_screen_unsupported_file_type_recorded_as_upload_failure():
    files = [
        ("resumes", ("resume.exe", io.BytesIO(b"not a resume"), "application/octet-stream")),
        ("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES)),
    ]
    resp = client.post("/api/screen", files=files, data={"github_enrichment": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible_count"] == 1
    failure = next(f for f in body["failures"] if f["source_file"] == "resume.exe")
    assert "Unsupported file type" in failure["error"]


def test_requirements_match_computed_for_eligible_candidate():
    files = [("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES))]
    resp = client.post(
        "/api/screen",
        files=files,
        data={
            "required_skills": "Python, Docker",
            "preferred_skills": "Kubernetes",
            "minimum_experience_years": "3",
            "github_enrichment": "false",
        },
    )
    assert resp.status_code == 200
    match = resp.json()["ranked"][0]["requirements_match"]
    assert "Python" in match["required_skills_matched"]
    assert "Docker" in match["required_skills_matched"]
    assert "Kubernetes" in match["preferred_skills_missing"]
    assert match["minimum_experience_years"] == 3.0
    # no "N years of experience" phrasing in the sample resume -> unknown, not false
    assert match["experience_years_detected"] is None
    assert match["meets_minimum_experience"] is None


def test_job_description_pasted_text_detects_skills():
    files = [("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES))]
    resp = client.post(
        "/api/screen",
        files=files,
        data={
            "job_description_text": "Looking for a Python engineer experienced with Docker and Kubernetes.",
            "github_enrichment": "false",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_description_provided"] is True
    match = body["ranked"][0]["requirements_match"]
    assert "python" in match["jd_detected_skills_matched"]
    assert "docker" in match["jd_detected_skills_matched"]
    assert "kubernetes" in match["jd_detected_skills_missing"]


def test_gemini_scorer_unavailable_returns_clean_400():
    """main.py reads a module-level `settings` (built once from the real
    env at import time), not a FastAPI Depends() -- so forcing the
    "no key configured" case for this test means patching that module
    attribute directly, regardless of what's actually in .env."""
    import resume_screener.api.main as main_module

    original = main_module.settings
    main_module.settings = Settings(gemini_api_key=None, github_enrichment_enabled=False)
    try:
        files = [("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES))]
        resp = client.post(
            "/api/screen",
            files=files,
            data={"scorer": "gemini", "github_enrichment": "false"},
        )
        assert resp.status_code == 400
        assert "GEMINI_API_KEY" in resp.json()["detail"]
    finally:
        main_module.settings = original


def test_response_never_contains_configured_secrets():
    """Whatever GITHUB_TOKEN/GEMINI_API_KEY happen to be configured in this
    environment's real .env, they must never appear anywhere in a response
    body -- this is a blunt but effective leak guard."""
    real_settings = app_settings
    files = [("resumes", _resume_file("eligible.pdf", ELIGIBLE_RESUME_LINES))]
    resp = client.post("/api/screen", files=files, data={"github_enrichment": "false"})
    assert resp.status_code == 200
    raw_body = resp.text

    if real_settings.github_token:
        assert real_settings.github_token not in raw_body
    if real_settings.gemini_api_key:
        assert real_settings.gemini_api_key not in raw_body


@pytest.mark.parametrize("field", ["github_token", "gemini_api_key"])
def test_settings_object_has_no_route_exposing_it(field):
    """Sanity check: no route in the app returns a Settings/config object
    directly (which would risk exposing credential fields by accident)."""
    for route in app.routes:
        response_model = getattr(route, "response_model", None)
        if response_model is not None:
            assert response_model is not Settings
