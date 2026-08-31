"""Tests for the Gemini scorer. NO real API calls are made anywhere here --
`GeminiScorer._call_gemini` (the one method that talks to the network) is
monkeypatched in every test to return a canned string, so these exercise the
real parsing/validation/grounding logic without needing google-genai
installed or a GEMINI_API_KEY configured.
"""

from __future__ import annotations

import json

import pytest

from resume_screener.config import Settings
from resume_screener.extraction.info import build_candidate
from resume_screener.models import GitHubEnrichment, GitHubRepoSummary
from resume_screener.scoring.gemini import GeminiScorer, GeminiScoringError


def _settings() -> Settings:
    return Settings(gemini_api_key="test-key-not-real", gemini_model="gemini-test")


def _valid_response_dict(
    ai_score: float = 32.0,
    ai_evidence: list[str] | None = None,
    penalties: list[dict] | None = None,
) -> dict:
    return {
        "ai_agentic_rag_depth": {
            "score": ai_score,
            "explanation": "Built a RAG pipeline with LangChain and a vector database.",
            "evidence": ai_evidence
            if ai_evidence is not None
            else ["Built a retrieval augmented generation pipeline using LangChain"],
            "confidence": 0.8,
        },
        "python_backend_engineering": {
            "score": 24.0,
            "explanation": "Python and FastAPI backend evidence present.",
            "evidence": ["Python, FastAPI, LangChain"],
            "confidence": 0.7,
        },
        "cloud_deployment_fullstack": {
            "score": 6.0,
            "explanation": "AWS and Docker mentioned.",
            "evidence": ["deployed on AWS with Docker"],
            "confidence": 0.6,
        },
        "engineering_depth": {
            "score": 2.0,
            "explanation": "Unit tests and CI/CD mentioned.",
            "evidence": ["unit tests and CI/CD"],
            "confidence": 0.5,
        },
        "penalties": penalties or [],
    }


def _rag_candidate_and_text():
    text = (
        "Skills\nPython, FastAPI, LangChain, Docker, AWS\n\n"
        "Projects\n"
        "RAG Assistant | Python, LangChain\n"
        "- Built a retrieval augmented generation pipeline using LangChain\n"
        "  and a vector database, deployed on AWS with Docker.\n"
        "- Added unit tests and CI/CD.\n"
    )
    return build_candidate(text), text


def _thin_candidate_and_text():
    text = "Skills\nPython\n\nProjects\nAI Tool\n- used the OpenAI API to summarize text.\n"
    return build_candidate(text), text


# --- 1. Valid structured Gemini response ------------------------------------


def test_valid_structured_response_maps_to_score_breakdown(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(_valid_response_dict()))

    result = scorer.score(candidate, text, GitHubEnrichment(status="no_url"))

    assert result.ai_agentic_rag_depth == 32.0
    assert result.python_backend_engineering == 24.0
    assert result.cloud_deployment_fullstack == 6.0
    assert result.engineering_depth == 2.0
    assert result.github_activity == 0.0  # no_url -> deterministic 0, never scored by Gemini
    assert result.penalties == []
    assert any("Built a retrieval augmented generation pipeline" in e for e in result.evidence)


# --- 2. Invalid JSON response ------------------------------------------------


def test_invalid_json_response_raises_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: "{not valid json at all")

    with pytest.raises(GeminiScoringError, match="invalid JSON"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


# --- 3. Missing required fields ---------------------------------------------


def test_missing_required_field_raises_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    incomplete = _valid_response_dict()
    del incomplete["engineering_depth"]
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(incomplete))

    with pytest.raises(GeminiScoringError, match="schema validation"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


# --- 4. Score outside allowed ranges -----------------------------------------


def test_score_above_category_cap_raises_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    out_of_range = _valid_response_dict(ai_score=999.0)
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(out_of_range))

    with pytest.raises(GeminiScoringError, match="out-of-range"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


def test_negative_score_raises_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    negative = _valid_response_dict(ai_score=-5.0)
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(negative))

    with pytest.raises(GeminiScoringError, match="out-of-range"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


def test_positive_penalty_value_raises_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    bad_penalty = _valid_response_dict(
        penalties=[{"points": 5.0, "reason": "should be negative", "evidence": []}]
    )
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(bad_penalty))

    with pytest.raises(GeminiScoringError, match="non-negative"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


# --- 5. Gemini API exception --------------------------------------------------


def test_api_exception_is_wrapped_as_gemini_scoring_error(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())

    def _raise(prompt: str) -> str:
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(scorer, "_call_gemini", _raise)

    with pytest.raises(GeminiScoringError, match="Gemini API call failed"):
        scorer.score(candidate, text, GitHubEnrichment(status="no_url"))


def test_missing_api_key_raises_immediately():
    with pytest.raises(GeminiScoringError, match="GEMINI_API_KEY"):
        GeminiScorer(Settings(gemini_api_key=None))


# --- 6. Candidate with insufficient evidence ---------------------------------


def test_candidate_with_insufficient_evidence_gets_conservative_score(monkeypatch):
    """A candidate with almost nothing to go on should be reflected as a low
    score from Gemini -- we don't force this, but verify the pipeline simply
    passes through whatever (valid, in-range) low score Gemini returns."""
    text = "Skills\nPython\n\nProjects\nMisc\n- Did some work with an LLM once.\n"
    candidate = build_candidate(text)
    scorer = GeminiScorer(_settings())
    low_score_response = _valid_response_dict(ai_score=4.0, ai_evidence=["Did some work with an LLM once."])
    low_score_response["python_backend_engineering"]["score"] = 3.0
    low_score_response["cloud_deployment_fullstack"]["score"] = 0.0
    low_score_response["engineering_depth"]["score"] = 0.0
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(low_score_response))

    result = scorer.score(candidate, text, GitHubEnrichment(status="no_url"))
    assert result.ai_agentic_rag_depth == 4.0
    assert result.total < 20.0


# --- 7. Candidate with a thin LLM-wrapper project ----------------------------


def test_thin_llm_wrapper_project_penalty_is_recorded(monkeypatch):
    candidate, text = _thin_candidate_and_text()
    scorer = GeminiScorer(_settings())
    thin_response = _valid_response_dict(
        ai_score=6.0,
        ai_evidence=["used the OpenAI API to summarize text."],
        penalties=[
            {
                "points": -12.0,
                "reason": "Thin LLM wrapper: a single API call with no further implementation detail.",
                "evidence": ["used the OpenAI API to summarize text."],
            }
        ],
    )
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(thin_response))

    result = scorer.score(candidate, text, GitHubEnrichment(status="no_url"))
    assert len(result.penalties) == 1
    assert result.penalties[0].points == -12.0
    assert "Thin LLM wrapper" in result.penalties[0].reason
    assert "used the OpenAI API to summarize text." in result.penalties[0].reason


# --- 8. Candidate with strong RAG/agentic implementation evidence -----------


def test_strong_rag_agentic_candidate_scores_high(monkeypatch):
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    strong_response = _valid_response_dict(ai_score=38.0)
    strong_response["python_backend_engineering"]["score"] = 28.0
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(strong_response))

    github = GitHubEnrichment(
        status="ok", username="dev", public_repos=12, top_repos=[GitHubRepoSummary(name="r", stars=10)]
    )
    result = scorer.score(candidate, text, github)
    assert result.ai_agentic_rag_depth == 38.0
    assert result.python_backend_engineering == 28.0
    assert result.github_activity == 10.0  # deterministic GitHub scoring, unaffected by Gemini
    assert result.total > 70.0


# --- Evidence-grounding safeguard -------------------------------------------


def test_ungrounded_evidence_snippet_is_dropped_not_trusted(monkeypatch):
    """If Gemini echoes an evidence quote that isn't actually in the payload
    we sent it, that quote must be dropped, not surfaced as if it were real."""
    candidate, text = _rag_candidate_and_text()
    scorer = GeminiScorer(_settings())
    fabricated = _valid_response_dict(
        ai_evidence=[
            "Built a retrieval augmented generation pipeline using LangChain",  # real, grounded
            "Scaled the system to 10 million requests per day",  # fabricated, not in payload
        ]
    )
    monkeypatch.setattr(scorer, "_call_gemini", lambda prompt: json.dumps(fabricated))

    result = scorer.score(candidate, text, GitHubEnrichment(status="no_url"))
    joined = " ".join(result.evidence)
    assert "10 million requests" not in joined
    assert "Built a retrieval augmented generation pipeline" in joined


# --- Pipeline-level: Gemini failure must not crash the batch ---------------


def test_pipeline_records_scoring_error_and_keeps_candidate(monkeypatch, tmp_path):
    """End-to-end: a Gemini failure for an eligible candidate must not raise
    out of run_pipeline, must not drop the candidate, and must leave
    score=None with scoring_error set instead of a fabricated score."""
    import pymupdf

    from resume_screener.pipeline import run_pipeline

    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "Jane Doe",
        "Skills: Python, LangChain",
        "Projects",
        "RAG Assistant",
        "- Built a retrieval augmented generation pipeline using LangChain.",
    ]
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=10, color=(0, 0, 0))
        y += 14
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()
    doc.save(str(resumes_dir / "candidate.pdf"))
    doc.close()

    class _AlwaysFailsScorer:
        def score(self, candidate, clean_text, github):
            raise GeminiScoringError("Gemini API call failed: simulated outage")

    report = run_pipeline(
        resumes_dir,
        scorer=_AlwaysFailsScorer(),
        github_enrichment=False,
    )

    assert report.failed_count == 0
    assert report.eligible_count == 1
    result = report.ranked[0]
    assert result.score is None
    assert result.scoring_error is not None
    assert "simulated outage" in result.scoring_error
    assert result.eligibility.eligible is True
