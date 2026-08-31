"""The scorer seam -- a future Gemini-based semantic scorer implements this
same Protocol and can be swapped in via pipeline wiring with no changes to
ingestion, extraction, eligibility, GitHub enrichment, or ranking.
"""

from __future__ import annotations

from typing import Protocol

from resume_screener.models import Candidate, GitHubEnrichment, ScoreBreakdown


class Scorer(Protocol):
    def score(
        self, candidate: Candidate, clean_text: str, github: GitHubEnrichment
    ) -> ScoreBreakdown: ...
