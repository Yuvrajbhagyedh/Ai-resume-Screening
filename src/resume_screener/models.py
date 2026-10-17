"""Single source of truth for all data schemas used across the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, computed_field

FileKind = Literal["pdf", "docx", "txt"]

IntegrityFlag = Literal[
    "white_or_near_background_text",
    "near_zero_alpha_text",
    "text_outside_page_bounds",
    "abnormally_tiny_font",
]

EligibilityCategory = Literal["python", "ai"]

GitHubStatus = Literal["ok", "not_found", "rate_limited", "no_url", "error", "disabled"]


class EvidenceHit(BaseModel):
    """One concrete piece of textual evidence backing a claim (skill, flag, score, etc.)."""

    category: str
    term: str
    snippet: str
    source: str = "resume_text"


class Project(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    evidence: list[EvidenceHit] = Field(default_factory=list)


class Candidate(BaseModel):
    name: str | None = None
    email: str | None = None
    github_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    raw_text_length: int = 0


class IntegrityReport(BaseModel):
    """Result of scanning the PDF text layer for visually-hidden or off-page text.

    Presence of flags is informational only and must never, by itself, cause
    rejection or a scoring penalty. See README for heuristic limitations.
    """

    flags: list[IntegrityFlag] = Field(default_factory=list)
    suspicious_span_count: int = 0
    total_span_count: int = 0
    details: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_clean(self) -> bool:
        return not self.flags


class EligibilityResult(BaseModel):
    eligible: bool
    python_evidence: list[EvidenceHit] = Field(default_factory=list)
    ai_evidence: list[EvidenceHit] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class PenaltyItem(BaseModel):
    reason: str
    points: float  # negative number


class ScoreBreakdown(BaseModel):
    ai_agentic_rag_depth: float = 0.0  # max 40
    python_backend_engineering: float = 0.0  # max 30
    cloud_deployment_fullstack: float = 0.0  # max 15
    github_activity: float = 0.0  # max 10
    engineering_depth: float = 0.0  # max 5
    penalties: list[PenaltyItem] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> float:
        return (
            self.ai_agentic_rag_depth
            + self.python_backend_engineering
            + self.cloud_deployment_fullstack
            + self.github_activity
            + self.engineering_depth
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def penalty_total(self) -> float:
        return sum(p.points for p in self.penalties)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> float:
        return max(0.0, min(100.0, self.subtotal + self.penalty_total))


class GitHubRepoSummary(BaseModel):
    name: str
    stars: int = 0
    language: str | None = None
    description: str | None = None
    fork: bool = False


class GitHubEnrichment(BaseModel):
    status: GitHubStatus
    username: str | None = None
    public_repos: int | None = None
    followers: int | None = None
    account_created_at: str | None = None
    top_repos: list[GitHubRepoSummary] = Field(default_factory=list)
    error_message: str | None = None


class ScreeningResult(BaseModel):
    source_file: str
    candidate: Candidate
    integrity: IntegrityReport
    eligibility: EligibilityResult
    github: GitHubEnrichment
    score: ScoreBreakdown | None = None
    rank: int | None = None
    # Integrity-filtered resume text, kept in memory so the API can reuse it
    # instead of parsing the PDF a second time. Private: never serialized.
    _clean_text: str | None = PrivateAttr(default=None)
    scoring_error: str | None = Field(
        default=None,
        description=(
            "Set when the configured scorer (e.g. Gemini) failed for an "
            "eligible candidate; score stays None rather than a fabricated "
            "fallback value. Never set for a deterministically ineligible "
            "candidate, since score is simply never computed for those."
        ),
    )


class ProcessingFailure(BaseModel):
    source_file: str
    stage: str
    error: str


class BatchReport(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    input_dir: str
    total_files_discovered: int
    eligible_count: int
    ineligible_count: int
    failed_count: int
    ranked: list[ScreeningResult] = Field(default_factory=list)
    ineligible: list[ScreeningResult] = Field(default_factory=list)
    failures: list[ProcessingFailure] = Field(default_factory=list)
