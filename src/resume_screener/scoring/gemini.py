"""Gemini-based semantic scorer -- an optional, LLM-backed alternative to
DeterministicScorer. Implements the same `Scorer` Protocol (scoring/base.py)
so nothing else in the pipeline changes to support it.

Design constraints (see README "Gemini scorer" section for the full writeup):

  - Gemini only ever scores a candidate that has ALREADY passed deterministic
    eligibility -- enforced by pipeline.py (it only calls scorer.score() when
    `eligibility.eligible` is True), not by anything here. This class has no
    way to set or influence eligibility: ScoreBreakdown carries no
    eligibility field, and `clean_text` (raw resume text) is accepted for
    Protocol-compatibility but deliberately never sent to Gemini.
  - The ONLY data Gemini receives is `_build_evidence_payload(candidate)`:
    the already-extracted, already integrity-filtered structured Candidate
    (name, skills, project name/description/technologies/evidence-snippets).
    Suspicious/hidden PDF spans never reach `Candidate` in the first place
    (see extraction/integrity.py), so they can't reach Gemini either.
  - GitHub activity (0-10) is never scored by Gemini -- `score_github_activity`
    from scoring/deterministic.py is reused unchanged.
  - Every evidence string Gemini returns is checked against the exact
    payload text we sent; anything that isn't an actual substring is
    dropped rather than trusted (a model can still echo a quote it made up
    even when told not to).
  - Any failure -- API error, timeout, malformed JSON, a missing field, or
    an out-of-range score -- raises GeminiScoringError with a clear
    message. pipeline.py catches this, leaves `score=None`, and records
    `ScreeningResult.scoring_error` instead of crashing the batch or
    fabricating a fallback score.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from pydantic import BaseModel, Field, ValidationError

from resume_screener.config import Settings
from resume_screener.models import Candidate, GitHubEnrichment, PenaltyItem, ScoreBreakdown
from resume_screener.scoring.deterministic import score_github_activity

logger = logging.getLogger(__name__)


class GeminiScoringError(Exception):
    """Any Gemini failure: API error, timeout, malformed JSON, a missing
    field, or an out-of-range score. Callers should treat this as "scoring
    unavailable for this candidate," never as a batch-ending error."""


# --- Wire schema for Gemini's structured JSON response ----------------------


class _CategoryScore(BaseModel):
    score: float
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = None


class _GeminiPenalty(BaseModel):
    points: float
    reason: str
    evidence: list[str] = Field(default_factory=list)


class _GeminiResponse(BaseModel):
    ai_agentic_rag_depth: _CategoryScore
    python_backend_engineering: _CategoryScore
    cloud_deployment_fullstack: _CategoryScore
    engineering_depth: _CategoryScore
    penalties: list[_GeminiPenalty] = Field(default_factory=list)


_CATEGORY_CAPS: dict[str, float] = {
    "ai_agentic_rag_depth": 40.0,
    "python_backend_engineering": 30.0,
    "cloud_deployment_fullstack": 15.0,
    "engineering_depth": 5.0,
}

_SYSTEM_INSTRUCTION = """\
You are a semantic evaluator scoring a job candidate's resume evidence for \
an AI/backend engineering role. The candidate has ALREADY passed a separate, \
deterministic eligibility check (genuine Python evidence AND genuine \
AI/LLM/RAG/agentic evidence were both confirmed). You are not deciding \
eligibility -- only scoring the depth of the evidence for a candidate who \
already qualifies.

STRICT RULES -- accuracy and evidence matter more than a complete-looking score:
1. Use ONLY the candidate data given below. Do not use outside knowledge \
about companies, schools, tools, or "typical" resumes.
2. Never infer that a candidate knows or used a technology just because \
another technology usually implies it (e.g. do not assume a vector \
database was used just because "RAG" is mentioned, unless a vector \
database is explicitly named in the data).
3. Never invent project details, implementation details, metrics, \
architecture, or deployment information beyond what is written.
4. Do not invent or reference GitHub activity, repositories, commits, or \
stars -- GitHub is scored separately and is not part of your evaluation.
5. Every evidence string you return must be copied verbatim from the \
candidate data below. Do not paraphrase, summarize, or invent evidence text.
6. If the evidence for a category is thin or ambiguous, give a LOW, \
conservative score rather than a generous guess.
7. A technology listed only in the generic skills list, with no project \
description showing it was actually used, is weak evidence -- do not \
score it as demonstrated implementation depth.
8. If a project is described only as e.g. "AI chatbot" or "used OpenAI \
API" with no further implementation detail, do NOT assume it involves \
RAG, agents, tool use, vector databases, orchestration, or evaluation -- \
score it as a shallow/minimal implementation.
9. If a specific framework (e.g. LangChain, LangGraph, LlamaIndex, Google \
ADK) is named but no implementation detail is given, you may credit \
knowledge of that framework, but do not invent what was built with it.
10. If a candidate has strong backend/cloud engineering evidence that is \
UNRELATED to their AI project(s), do not use that unrelated strength to \
inflate the AI-project-depth score, and do not use it to avoid or reduce \
a thin-AI-wrapper penalty. Judge each AI project on its own supporting \
evidence only.

SCORE THESE FOUR CATEGORIES ONLY (numbers within the given range):
- ai_agentic_rag_depth: 0 to 40 -- depth/specificity of actual AI/LLM/RAG/agentic implementation evidence.
- python_backend_engineering: 0 to 30 -- depth of genuine Python and backend engineering evidence.
- cloud_deployment_fullstack: 0 to 15 -- depth of cloud/deployment/full-stack evidence.
- engineering_depth: 0 to 5 -- general engineering rigor evidence (testing, CI/CD, system design, etc.).

For each category return: score (number in range), explanation (short, \
evidence-based), evidence (list of verbatim quotes from the candidate data \
below -- empty list if you cannot quote anything specific), and confidence \
(0 to 1, or null if not useful).

PENALTIES: if you find a thin/shallow AI implementation (e.g. a bare "used \
the OpenAI API" with no further detail) or a tutorial/clone-style project, \
return a penalty with a NEGATIVE points value (between -15 and -5), a \
reason, and verbatim evidence. Only add a penalty when the evidence \
actually supports it -- do not invent a problem to seem thorough.

Return ONLY a single JSON object matching exactly this shape -- no prose, \
no markdown code fences, no extra keys:
{
  "ai_agentic_rag_depth": {"score": <number>, "explanation": "<string>", "evidence": ["<string>", ...], "confidence": <number or null>},
  "python_backend_engineering": {"score": <number>, "explanation": "<string>", "evidence": ["<string>", ...], "confidence": <number or null>},
  "cloud_deployment_fullstack": {"score": <number>, "explanation": "<string>", "evidence": ["<string>", ...], "confidence": <number or null>},
  "engineering_depth": {"score": <number>, "explanation": "<string>", "evidence": ["<string>", ...], "confidence": <number or null>},
  "penalties": [{"points": <negative number>, "reason": "<string>", "evidence": ["<string>", ...]}]
}
"""


def _build_evidence_payload(candidate: Candidate) -> dict:
    """The ONLY candidate data sent to Gemini. Built entirely from fields
    already extracted deterministically by extraction/info.py -- no raw
    resume text, no suspicious/hidden PDF content (that never reaches
    `Candidate` at all)."""
    return {
        "name": candidate.name,
        "skills": candidate.skills,
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "technologies": p.technologies,
                # dedupe: multiple matched terms can share one source line
                "evidence_snippets": list(dict.fromkeys(e.snippet for e in p.evidence)),
            }
            for p in candidate.projects
        ],
    }


def _build_prompt(payload: dict) -> str:
    return _SYSTEM_INSTRUCTION + "\n\nCANDIDATE DATA (JSON):\n" + json.dumps(payload, indent=2)


def _validate_ranges(parsed: _GeminiResponse) -> None:
    for field_name, cap in _CATEGORY_CAPS.items():
        category: _CategoryScore = getattr(parsed, field_name)
        if not (0.0 <= category.score <= cap):
            raise GeminiScoringError(
                f"Gemini returned an out-of-range score for {field_name}: "
                f"{category.score} (allowed 0-{cap})"
            )
    for penalty in parsed.penalties:
        if penalty.points > 0:
            raise GeminiScoringError(
                f"Gemini returned a non-negative 'penalty' value: "
                f"{penalty.points} for {penalty.reason!r} (penalties must subtract points)"
            )


def _filter_grounded_evidence(snippets: list[str], payload_text: str) -> list[str]:
    """Drop any evidence string that isn't an actual substring of what we
    sent Gemini -- defense-in-depth against a fabricated quote, since a
    model can still echo something it made up even when told not to."""
    lowered_payload = payload_text.lower()
    grounded = [s for s in snippets if s and s.lower() in lowered_payload]
    dropped = len(snippets) - len(grounded)
    if dropped:
        logger.warning("Dropped %d ungrounded Gemini evidence snippet(s)", dropped)
    return grounded


def _to_score_breakdown(
    parsed: _GeminiResponse, github: GitHubEnrichment, payload_text: str
) -> ScoreBreakdown:
    github_activity, github_evidence = score_github_activity(github)

    evidence: list[str] = []
    for field_name in _CATEGORY_CAPS:
        category: _CategoryScore = getattr(parsed, field_name)
        grounded = _filter_grounded_evidence(category.evidence, payload_text)
        confidence_note = (
            f" (confidence={category.confidence:.2f})" if category.confidence is not None else ""
        )
        evidence.append(f"Gemini {field_name}{confidence_note}: {category.explanation}")
        evidence += [f"Gemini {field_name} evidence: '{s}'" for s in grounded]
    evidence += github_evidence

    penalties: list[PenaltyItem] = []
    for p in parsed.penalties:
        grounded = _filter_grounded_evidence(p.evidence, payload_text)
        reason = p.reason
        if grounded:
            reason += " Evidence: " + "; ".join(f"'{s}'" for s in grounded)
        penalties.append(PenaltyItem(reason=reason, points=p.points))

    return ScoreBreakdown(
        ai_agentic_rag_depth=parsed.ai_agentic_rag_depth.score,
        python_backend_engineering=parsed.python_backend_engineering.score,
        cloud_deployment_fullstack=parsed.cloud_deployment_fullstack.score,
        github_activity=github_activity,
        engineering_depth=parsed.engineering_depth.score,
        penalties=penalties,
        evidence=evidence,
    )


class GeminiScorer:
    """Semantic scorer backed by the Gemini API. Implements the `Scorer`
    Protocol (scoring/base.py). Raises `GeminiScoringError` on any failure
    -- it never silently falls back to a fabricated or deterministic score;
    that decision belongs to the caller (pipeline.py records the failure
    and leaves `score=None`; DeterministicScorer remains available as a
    separate `--scorer deterministic` mode)."""

    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise GeminiScoringError(
                "GEMINI_API_KEY is not configured -- set it in the environment or .env"
            )
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._timeout_seconds = settings.gemini_timeout_seconds
        # gemini-2.5-flash "thinks" before answering by default, which costs
        # several seconds per candidate. Scoring structured evidence against a
        # rubric doesn't need it, so the default budget is 0 (off).
        self._thinking_budget = settings.gemini_thinking_budget
        self._max_retries = max(0, settings.gemini_max_retries)
        self._client = None
        self._client_lock = threading.Lock()
        self._use_thinking_config = self._thinking_budget >= 0

    def _get_client(self):
        # One client per scorer: it is thread-safe and reuses connections, so
        # concurrent candidates don't each pay for a new TLS handshake.
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from google import genai  # local import: optional dependency
                    from google.genai import types

                    self._client = genai.Client(
                        api_key=self._api_key,
                        http_options=types.HttpOptions(timeout=int(self._timeout_seconds * 1000)),
                    )
        return self._client

    def _generate(self, prompt: str):
        from google.genai import types

        config = {"response_mime_type": "application/json", "temperature": 0.0}
        if self._use_thinking_config:
            config["thinking_config"] = types.ThinkingConfig(thinking_budget=self._thinking_budget)
        return self._get_client().models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(**config),
        )

    def _call_gemini(self, prompt: str) -> str:
        """Isolated in its own method so tests can mock this instead of the
        network -- everything else here is pure parsing/validation logic
        exercised directly, with no Gemini SDK or API access required."""
        attempt = 0
        while True:
            try:
                response = self._generate(prompt)
                break
            except Exception as exc:  # noqa: BLE001 -- classified below
                message = str(exc).lower()
                if self._use_thinking_config and "thinking" in message:
                    # This model doesn't accept a thinking budget; retry without it.
                    self._use_thinking_config = False
                    continue
                busy = any(t in message for t in ("429", "503", "resource_exhausted", "unavailable"))
                if not busy or attempt >= self._max_retries:
                    raise
                attempt += 1
                logger.warning("Gemini busy; retrying (attempt %d): %s", attempt, exc)
                time.sleep(2.0 * attempt)
        if not response.text:
            raise GeminiScoringError("Gemini returned an empty response")
        return response.text

    def score(
        self, candidate: Candidate, clean_text: str, github: GitHubEnrichment
    ) -> ScoreBreakdown:
        # `clean_text` (the full resume) is intentionally unused: Gemini only
        # ever sees the structured, already-extracted evidence payload below.
        payload = _build_evidence_payload(candidate)
        payload_text = json.dumps(payload)
        prompt = _build_prompt(payload)

        try:
            raw_text = self._call_gemini(prompt)
        except GeminiScoringError:
            raise
        except Exception as exc:  # noqa: BLE001 -- any SDK/network/auth failure
            raise GeminiScoringError(f"Gemini API call failed: {exc}") from exc

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise GeminiScoringError(f"Gemini returned invalid JSON: {exc}") from exc

        try:
            parsed = _GeminiResponse.model_validate(data)
        except ValidationError as exc:
            raise GeminiScoringError(f"Gemini response failed schema validation: {exc}") from exc

        _validate_ranges(parsed)

        return _to_score_breakdown(parsed, github, payload_text)
