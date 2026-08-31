"""Deterministic baseline scorer -- no LLM involved.

Every component below is a plain, reproducible count over `clean_text` and
`GitHubEnrichment`, so the same resume always yields the same score and each
point is traceable to a specific piece of evidence (see `ScoreBreakdown.evidence`).
"""

from __future__ import annotations

from resume_screener.evidence import (
    find_ai_ambiguous_evidence,
    find_ai_generic_evidence,
    find_ai_strong_evidence,
    find_literal_hits,
    find_python_evidence,
)
from resume_screener.keywords import (
    AI_INFRA_SIGNAL_TERMS,
    BACKEND_ENGINEERING_TERMS,
    CLOUD_DEPLOYMENT_TERMS,
    TUTORIAL_PENALTY_TERMS,
)
from resume_screener.models import Candidate, GitHubEnrichment, PenaltyItem, ScoreBreakdown

_FULLSTACK_FRONTEND_TERMS = {
    "react", "react.js", "next.js", "node.js", "angular", "vue.js", "express.js",
}
_ENGINEERING_DEPTH_TERMS = {
    "unit test", "unit testing", "ci/cd", "system design", "docker",
    "kubernetes", "pytest", "code review", "design pattern",
}

# Lines on either side of a meaningful AI-term mention that count as "near"
# it when looking for supporting infra/engineering signal. Keeps the
# thin-wrapper check scoped to the AI evidence itself -- an unrelated
# backend section elsewhere in the resume must not rescue a thin AI mention.
_AI_INFRA_CONTEXT_WINDOW = 2


def _score_ai_depth(clean_text: str, candidate: Candidate) -> tuple[float, list[str]]:
    strong = find_ai_strong_evidence(clean_text)
    ambiguous = find_ai_ambiguous_evidence(clean_text)
    generic = find_ai_generic_evidence(clean_text)

    raw = len(strong) * 8 + len(ambiguous) * 5 + len(generic) * 2
    project_bonus = 5 if any(
        set(t.lower() for t in p.technologies) & {h.term for h in strong}
        for p in candidate.projects
    ) else 0
    total = min(40.0, raw + project_bonus)

    evidence = [f"AI depth: strong term '{h.term}'" for h in strong]
    evidence += [f"AI depth: contextual term '{h.term}'" for h in ambiguous]
    evidence += [f"AI depth: generic signal '{h.term}'" for h in generic]
    if project_bonus:
        evidence.append("AI depth: +5 bonus for AI technology named within a Projects entry")
    return total, evidence


def _score_python_backend(clean_text: str) -> tuple[float, list[str]]:
    python_hits = find_python_evidence(clean_text)
    backend_hits = find_literal_hits(clean_text, "backend", BACKEND_ENGINEERING_TERMS)

    total = min(30.0, len(python_hits) * 6 + len(backend_hits) * 3)

    evidence = [f"Python: '{h.term}'" for h in python_hits]
    evidence += [f"Backend engineering: '{h.term}'" for h in backend_hits]
    return total, evidence


def _score_cloud_fullstack(clean_text: str) -> tuple[float, list[str]]:
    cloud_hits = find_literal_hits(clean_text, "cloud", CLOUD_DEPLOYMENT_TERMS)
    frontend_hits = find_literal_hits(clean_text, "fullstack", _FULLSTACK_FRONTEND_TERMS)

    total = min(15.0, len(cloud_hits) * 4 + len(frontend_hits) * 2)

    evidence = [f"Cloud/deployment: '{h.term}'" for h in cloud_hits]
    evidence += [f"Full-stack: '{h.term}'" for h in frontend_hits]
    return total, evidence


def score_github_activity(github: GitHubEnrichment) -> tuple[float, list[str]]:
    """Public (not prefixed): reused as-is by scoring/gemini.py, since GitHub
    activity is always scored deterministically by the application, never
    by Gemini."""
    if github.status != "ok":
        return 0.0, [f"GitHub activity: unavailable (status={github.status})"]

    repos = github.public_repos or 0
    if repos == 0:
        base = 0.0
    elif repos <= 3:
        base = 3.0
    elif repos <= 8:
        base = 6.0
    else:
        base = 9.0

    star_bonus = 1.0 if any(r.stars >= 5 for r in github.top_repos) else 0.0
    total = min(10.0, base + star_bonus)

    evidence = [f"GitHub activity: {repos} public repos -> {base:.0f} pts"]
    if star_bonus:
        evidence.append("GitHub activity: +1 bonus for a repo with 5+ stars")
    return total, evidence


def _score_engineering_depth(clean_text: str, candidate: Candidate) -> tuple[float, list[str]]:
    hits = find_literal_hits(clean_text, "engineering", _ENGINEERING_DEPTH_TERMS)
    total = min(5.0, float(len(hits)))
    evidence = [f"Engineering depth: '{h.term}'" for h in hits]
    return total, evidence


def _local_ai_evidence_context(clean_text: str, meaningful_terms: set[str]) -> str:
    """Lines within a small window around each meaningful AI-term mention.

    Used to judge whether infra/engineering signal actually supports the AI
    work itself, rather than letting an unrelated backend/cloud paragraph
    elsewhere in the resume mask a thin AI mention.
    """
    if not meaningful_terms:
        return ""
    lines = clean_text.splitlines()
    lowered_terms = [t.lower() for t in meaningful_terms]
    window_indices: set[int] = set()
    for idx, line in enumerate(lines):
        lowered_line = line.lower()
        if any(term in lowered_line for term in lowered_terms):
            start = max(0, idx - _AI_INFRA_CONTEXT_WINDOW)
            end = min(len(lines), idx + _AI_INFRA_CONTEXT_WINDOW + 1)
            window_indices.update(range(start, end))
    return "\n".join(lines[i] for i in sorted(window_indices))


def _thin_wrapper_penalty(clean_text: str) -> PenaltyItem | None:
    strong = find_ai_strong_evidence(clean_text)
    ambiguous = find_ai_ambiguous_evidence(clean_text)
    meaningful_count = len(strong) + len(ambiguous)
    if meaningful_count > 1:
        return None

    meaningful_terms = {h.term for h in strong} | {h.term for h in ambiguous}
    local_context = _local_ai_evidence_context(clean_text, meaningful_terms)
    infra_hits = find_literal_hits(local_context, "ai_infra", AI_INFRA_SIGNAL_TERMS)
    if not infra_hits:
        return PenaltyItem(
            reason=(
                "Thin LLM-wrapper penalty: only one AI mention and no supporting "
                "engineering signal near that mention (no API integration, "
                "backend, pipeline, evaluation, etc. mentioned nearby)."
            ),
            points=-15.0,
        )
    if len(infra_hits) == 1:
        return PenaltyItem(
            reason=(
                "Thin LLM-wrapper penalty: minimal AI evidence with only one "
                "supporting engineering signal near that mention."
            ),
            points=-8.0,
        )
    return None


def _tutorial_penalty(clean_text: str) -> PenaltyItem | None:
    hits = find_literal_hits(clean_text, "tutorial", TUTORIAL_PENALTY_TERMS)
    if not hits:
        return None
    points = -5.0 - min(5.0, (len(hits) - 1) * 3.0)
    return PenaltyItem(
        reason=(
            f"Tutorial-style project penalty: resume text matches "
            f"{len(hits)} tutorial/bootcamp/clone-style term(s) "
            f"({', '.join(h.term for h in hits)})."
        ),
        points=points,
    )


class DeterministicScorer:
    """The v1 scorer. Implements the `Scorer` Protocol -- no LLM calls."""

    def score(
        self, candidate: Candidate, clean_text: str, github: GitHubEnrichment
    ) -> ScoreBreakdown:
        ai_depth, ai_evidence = _score_ai_depth(clean_text, candidate)
        python_backend, python_evidence = _score_python_backend(clean_text)
        cloud_fullstack, cloud_evidence = _score_cloud_fullstack(clean_text)
        github_activity, github_evidence = score_github_activity(github)
        engineering_depth, engineering_evidence = _score_engineering_depth(clean_text, candidate)

        penalties = [
            p for p in (_thin_wrapper_penalty(clean_text), _tutorial_penalty(clean_text)) if p
        ]

        return ScoreBreakdown(
            ai_agentic_rag_depth=ai_depth,
            python_backend_engineering=python_backend,
            cloud_deployment_fullstack=cloud_fullstack,
            github_activity=github_activity,
            engineering_depth=engineering_depth,
            penalties=penalties,
            evidence=[
                *ai_evidence,
                *python_evidence,
                *cloud_evidence,
                *github_evidence,
                *engineering_evidence,
            ],
        )
