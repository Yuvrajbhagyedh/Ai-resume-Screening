"""Lightweight, display-only requirements matching for the web API.

Intentionally separate from eligibility.py/scoring/ -- it never affects
whether a candidate is eligible or how they're scored/ranked. It only
annotates a candidate with how they compare to recruiter-supplied extras
(required/preferred skills, a pasted/uploaded JD, minimum experience) so
the frontend can show that context alongside the real, unmodified
deterministic/Gemini result. Reuses existing extraction utilities
(`find_literal_hits`, `GENERAL_SKILL_VOCAB`) rather than re-implementing
skill detection.
"""

from __future__ import annotations

import re

from resume_screener.api.schemas import RequirementsMatch
from resume_screener.evidence import find_literal_hits
from resume_screener.extraction.info import GENERAL_SKILL_VOCAB

_EXPERIENCE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\.?\s*(?:of\s+)?(?:experience|exp)\b",
    re.IGNORECASE,
)


def detect_years_experience(text: str) -> float | None:
    """Best-effort regex scan for phrasing like "5 years of experience" or
    "3+ yrs exp". Returns the largest match found, or None if nothing
    matches -- callers must treat None as "unknown", not "zero"."""
    matches = [float(m.group(1)) for m in _EXPERIENCE_RE.finditer(text)]
    return max(matches) if matches else None


def _match_skills(requested: list[str], candidate_skills: list[str]) -> tuple[list[str], list[str]]:
    normalized_candidate = [s.lower() for s in candidate_skills]
    matched: list[str] = []
    missing: list[str] = []
    for raw in requested:
        skill = raw.strip()
        if not skill:
            continue
        norm = skill.lower()
        if any(norm == cs or norm in cs or cs in norm for cs in normalized_candidate):
            matched.append(skill)
        else:
            missing.append(skill)
    return matched, missing


def detect_jd_skills(job_description_text: str) -> list[str]:
    """Auto-detect known technology terms mentioned in a job description,
    reusing the same vocabulary the resume skill extractor uses."""
    if not job_description_text.strip():
        return []
    hits = find_literal_hits(job_description_text, "jd", GENERAL_SKILL_VOCAB)
    return sorted({h.term for h in hits})


def build_requirements_match(
    candidate_skills: list[str],
    candidate_text: str | None,
    required_skills: list[str],
    preferred_skills: list[str],
    minimum_experience_years: float | None,
    job_description_text: str | None,
) -> RequirementsMatch:
    required_matched, required_missing = _match_skills(required_skills, candidate_skills)
    preferred_matched, preferred_missing = _match_skills(preferred_skills, candidate_skills)

    jd_skills = detect_jd_skills(job_description_text) if job_description_text else []
    jd_matched, jd_missing = _match_skills(jd_skills, candidate_skills)

    experience_detected = detect_years_experience(candidate_text) if candidate_text else None
    meets_minimum = (
        None
        if minimum_experience_years is None or experience_detected is None
        else experience_detected >= minimum_experience_years
    )

    return RequirementsMatch(
        required_skills_matched=required_matched,
        required_skills_missing=required_missing,
        preferred_skills_matched=preferred_matched,
        preferred_skills_missing=preferred_missing,
        jd_detected_skills_matched=jd_matched,
        jd_detected_skills_missing=jd_missing,
        experience_years_detected=experience_detected,
        minimum_experience_years=minimum_experience_years,
        meets_minimum_experience=meets_minimum,
    )
