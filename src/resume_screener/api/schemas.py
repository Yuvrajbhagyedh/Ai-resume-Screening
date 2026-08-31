"""API-only response schemas.

These extend the core `models.py` schemas via subclassing rather than
modifying them -- the core pipeline and its output contract are completely
unaffected by the web layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from resume_screener.models import ProcessingFailure, ScreeningResult


class RequirementsMatch(BaseModel):
    """Display-only comparison against recruiter-supplied extras (required/
    preferred skills, a pasted/uploaded JD, minimum experience).

    This never affects eligibility or score -- see api/matching.py. It is a
    plain, deterministic overlap check against the *already-extracted*
    `Candidate.skills`, plus a regex-based years-of-experience detector.
    """

    required_skills_matched: list[str] = Field(default_factory=list)
    required_skills_missing: list[str] = Field(default_factory=list)
    preferred_skills_matched: list[str] = Field(default_factory=list)
    preferred_skills_missing: list[str] = Field(default_factory=list)
    jd_detected_skills_matched: list[str] = Field(default_factory=list)
    jd_detected_skills_missing: list[str] = Field(default_factory=list)
    experience_years_detected: float | None = None
    minimum_experience_years: float | None = None
    meets_minimum_experience: bool | None = None


class ScreeningResultOut(ScreeningResult):
    """`ScreeningResult` plus the optional requirements-match annotation."""

    requirements_match: RequirementsMatch | None = None


class ScreenResponse(BaseModel):
    generated_at: str
    total_files_discovered: int
    eligible_count: int
    ineligible_count: int
    failed_count: int
    ranked: list[ScreeningResultOut] = Field(default_factory=list)
    ineligible: list[ScreeningResultOut] = Field(default_factory=list)
    failures: list[ProcessingFailure] = Field(default_factory=list)
    scorer_used: str
    job_description_provided: bool
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_experience_years: float | None = None
