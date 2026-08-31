"""Stage 8: rank eligible candidates by score, descending.

Deterministic tiebreak: higher AI/agentic/RAG depth first, then name -- so
re-running on the same input always produces the same order.
"""

from __future__ import annotations

from resume_screener.models import ScreeningResult


def rank_candidates(results: list[ScreeningResult]) -> list[ScreeningResult]:
    def sort_key(r: ScreeningResult) -> tuple[float, float, str]:
        score = r.score.total if r.score else 0.0
        ai_depth = r.score.ai_agentic_rag_depth if r.score else 0.0
        name = (r.candidate.name or "").lower()
        return (-score, -ai_depth, name)

    ranked = sorted(results, key=sort_key)
    for idx, result in enumerate(ranked, start=1):
        result.rank = idx
    return ranked
