"""Concurrency and Gemini call-path tests. No network: scorers, the Gemini
SDK call, and GitHub HTTP are all faked."""

from __future__ import annotations

import threading
import time

import httpx
import pymupdf
import pytest

from resume_screener import github_enrich
from resume_screener.config import Settings
from resume_screener.models import GitHubEnrichment
from resume_screener.pipeline import run_pipeline
from resume_screener.scoring.deterministic import DeterministicScorer
from resume_screener.scoring.gemini import GeminiScorer


def _write_resume(folder, name, person):
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        person,
        "Skills: Python, LangChain, FastAPI",
        "Projects",
        "RAG Assistant",
        "- Built a retrieval augmented generation pipeline using LangChain and a vector database.",
    ]
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 14 * i), line, fontsize=10, color=(0, 0, 0))
    doc.save(str(folder / name))
    doc.close()


@pytest.fixture
def four_resumes(tmp_path):
    folder = tmp_path / "resumes"
    folder.mkdir()
    for i, person in enumerate(["Asha Rao", "Ben Lee", "Chen Wu", "Dana Kim"]):
        _write_resume(folder, f"{i}_candidate.pdf", person)
    return folder


class _SlowScorer:
    """Stands in for Gemini: each call takes 0.5s of network-like waiting."""

    def __init__(self):
        self.max_in_flight = 0
        self._in_flight = 0
        self._lock = threading.Lock()

    def score(self, candidate, clean_text, github):
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        time.sleep(0.5)
        with self._lock:
            self._in_flight -= 1
        return DeterministicScorer().score(candidate, clean_text, github)


def test_candidates_are_scored_concurrently(four_resumes):
    scorer = _SlowScorer()
    start = time.monotonic()
    report = run_pipeline(four_resumes, settings=Settings(max_workers=4), scorer=scorer, github_enrichment=False)
    elapsed = time.monotonic() - start

    assert report.eligible_count == 4
    assert scorer.max_in_flight == 4
    assert elapsed < 1.5  # sequential would be >= 2.0s


def test_max_workers_one_is_sequential(four_resumes):
    scorer = _SlowScorer()
    run_pipeline(four_resumes, settings=Settings(max_workers=1), scorer=scorer, github_enrichment=False)
    assert scorer.max_in_flight == 1


def test_results_match_sequential_run(four_resumes):
    sequential = run_pipeline(four_resumes, settings=Settings(max_workers=1), github_enrichment=False)
    concurrent = run_pipeline(four_resumes, settings=Settings(max_workers=4), github_enrichment=False)
    as_rows = lambda r: [(x.source_file, x.rank, x.score.total) for x in r.ranked]  # noqa: E731
    assert as_rows(sequential) == as_rows(concurrent)


def test_pipeline_keeps_clean_text_for_api_reuse(four_resumes):
    report = run_pipeline(four_resumes, github_enrichment=False)
    assert "LangChain" in report.ranked[0]._clean_text
    assert "_clean_text" not in report.ranked[0].model_dump()


def test_one_failing_scorer_call_does_not_affect_others(four_resumes):
    class _FlakyScorer:
        def score(self, candidate, clean_text, github):
            if candidate.name == "Ben Lee":
                raise RuntimeError("simulated outage")
            return DeterministicScorer().score(candidate, clean_text, github)

    report = run_pipeline(four_resumes, settings=Settings(max_workers=4), scorer=_FlakyScorer(), github_enrichment=False)
    errors = {r.candidate.name: r.scoring_error for r in report.ranked}
    assert errors["Ben Lee"] == "simulated outage"
    assert sum(1 for e in errors.values() if e is None) == 3


# ---- Gemini call path ----

class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _gemini(monkeypatch, **overrides):
    monkeypatch.setattr("resume_screener.scoring.gemini.time.sleep", lambda s: None)
    return GeminiScorer(Settings(gemini_api_key="test-key", **overrides))


def test_gemini_retries_when_rate_limited(monkeypatch):
    scorer = _gemini(monkeypatch)
    calls = iter([RuntimeError("429 RESOURCE_EXHAUSTED"), _FakeResponse('{"ok": true}')])

    def fake_generate(prompt):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(scorer, "_generate", fake_generate)
    assert scorer._call_gemini("p") == '{"ok": true}'


def test_gemini_gives_up_after_max_retries(monkeypatch):
    scorer = _gemini(monkeypatch, gemini_max_retries=2)
    attempts = []

    def always_busy(prompt):
        attempts.append(1)
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(scorer, "_generate", always_busy)
    with pytest.raises(RuntimeError):
        scorer._call_gemini("p")
    assert len(attempts) == 3


def test_gemini_does_not_retry_other_errors(monkeypatch):
    scorer = _gemini(monkeypatch)
    attempts = []

    def bad_request(prompt):
        attempts.append(1)
        raise RuntimeError("400 INVALID_ARGUMENT: bad prompt")

    monkeypatch.setattr(scorer, "_generate", bad_request)
    with pytest.raises(RuntimeError):
        scorer._call_gemini("p")
    assert len(attempts) == 1


def test_gemini_drops_thinking_config_when_unsupported(monkeypatch):
    scorer = _gemini(monkeypatch)
    used_thinking = []

    def fake_generate(prompt):
        used_thinking.append(scorer._use_thinking_config)
        if scorer._use_thinking_config:
            raise RuntimeError("400 Thinking is not supported for this model")
        return _FakeResponse("{}")

    monkeypatch.setattr(scorer, "_generate", fake_generate)
    assert scorer._call_gemini("p") == "{}"
    assert used_thinking == [True, False]


def test_gemini_thinking_off_by_default(monkeypatch):
    assert _gemini(monkeypatch)._use_thinking_config is True
    assert _gemini(monkeypatch)._thinking_budget == 0
    assert _gemini(monkeypatch, gemini_thinking_budget=-1)._use_thinking_config is False


# ---- GitHub cache ----

def test_github_profile_fetched_once_per_username(monkeypatch):
    github_enrich._cache.clear()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("/repos"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"public_repos": 3, "followers": 1, "created_at": "2020-01-01"})

    real_client = httpx.Client
    monkeypatch.setattr(
        github_enrich.httpx, "Client", lambda *a, **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    settings = Settings(github_enrichment_enabled=True)
    first = github_enrich.enrich("https://github.com/SameUser", settings)
    second = github_enrich.enrich("https://github.com/sameuser/", settings)

    assert first.status == second.status == "ok"
    assert len(requests) == 2  # user + repos, once
    github_enrich._cache.clear()


def test_github_failures_are_not_cached(monkeypatch):
    github_enrich._cache.clear()
    requests = []

    def handler(request):
        requests.append(1)
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(
        github_enrich.httpx, "Client", lambda *a, **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    settings = Settings(github_enrichment_enabled=True)
    github_enrich.enrich("https://github.com/ghost", settings)
    github_enrich.enrich("https://github.com/ghost", settings)
    assert len(requests) == 2
