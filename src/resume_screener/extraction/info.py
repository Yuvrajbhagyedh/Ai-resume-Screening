"""Candidate information extraction: name, email, GitHub, skills, projects.

Operates only on `clean_text` (the integrity-filtered text) so that
visually-hidden content can never masquerade as genuine resume evidence.
All heuristics here are intentionally simple/regex-based to stay
deterministic and unit-testable -- see README for known limitations.
"""

from __future__ import annotations

import re

from resume_screener.evidence import (
    find_literal_hits,
    find_meaningful_ai_evidence,
    find_python_evidence,
)
from resume_screener.keywords import (
    AI_GENERIC_TERMS,
    AI_STRONG_TERMS,
    BACKEND_ENGINEERING_TERMS,
    CLOUD_DEPLOYMENT_TERMS,
    GENERAL_SKILLS,
    PYTHON_FRAMEWORKS,
)
from resume_screener.models import Candidate, Project

GENERAL_SKILL_VOCAB: set[str] = (
    GENERAL_SKILLS
    | PYTHON_FRAMEWORKS
    | AI_STRONG_TERMS
    | AI_GENERIC_TERMS
    | BACKEND_ENGINEERING_TERMS
    | CLOUD_DEPLOYMENT_TERMS
    | {"python"}
)

SECTION_HEADERS: dict[str, set[str]] = {
    "skills": {"skills", "technical skills", "core competencies", "technologies", "tech stack"},
    "projects": {"projects", "personal projects", "academic projects", "key projects", "project"},
    "experience": {
        "experience", "work experience", "professional experience",
        "internship", "internships", "work history",
    },
    "education": {"education", "academic background"},
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)",
    re.IGNORECASE,
)
_GITHUB_RESERVED = {
    "sponsors", "settings", "topics", "marketplace", "notifications",
    "issues", "pulls", "orgs", "about", "features", "pricing", "apps", "login",
}
_NAME_RE = re.compile(r"^[A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,3}$")
_NAME_BLOCKLIST = {
    "resume", "curriculum vitae", "cv", "bio data", "biodata", "profile",
    "contact", "address", "contact information", "contact info",
    "personal details", "objective", "summary", "career objective",
    "professional summary",
}
_BULLET_RE = re.compile(r"^[\-\*•●▪]\s*")
_SKILL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+#./\- ]{0,28}[A-Za-z0-9+#)]$")
_SKILL_STOPWORDS = {"and", "etc", "other", "others", "skills", "technologies", "tools"}


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        norm = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip()
        matched = None
        if line and len(norm) <= 40:
            for name, aliases in SECTION_HEADERS.items():
                if norm in aliases:
                    matched = name
                    break
        if matched:
            current = matched
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw_line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def extract_github_url(text: str) -> str | None:
    for match in _GITHUB_RE.finditer(text):
        username = match.group(1)
        if username.lower() in _GITHUB_RESERVED:
            continue
        return f"https://github.com/{username}"
    return None


def extract_name(text: str) -> str | None:
    for line in text.splitlines()[:6]:
        candidate = line.strip()
        if not candidate or len(candidate) > 60:
            continue
        if "@" in candidate or any(ch.isdigit() for ch in candidate):
            continue
        if candidate.lower() in _NAME_BLOCKLIST:
            continue
        if _NAME_RE.match(candidate):
            return candidate
    return None


def extract_skills(clean_text: str, sections: dict[str, str]) -> list[str]:
    found: dict[str, str] = {}

    for hit in find_literal_hits(clean_text, "skill", GENERAL_SKILL_VOCAB):
        found[hit.term.lower()] = hit.term

    for chunk in re.split(r"[,\|••;\n]", sections.get("skills", "")):
        token = chunk.strip(" -\t*")
        if not token:
            continue
        key = token.lower()
        if key in _SKILL_STOPWORDS or not _SKILL_TOKEN_RE.match(token):
            continue
        found.setdefault(key, token)

    return sorted(found.values(), key=str.lower)


def extract_projects(projects_section_text: str) -> list[Project]:
    blocks: list[list[str]] = []
    current: list[str] = []
    # A non-bulleted line only starts a new project if the previous line
    # looks "finished" (ends in sentence-terminal punctuation) or wasn't
    # itself a bullet. Otherwise it's treated as a wrapped continuation of
    # the previous bullet -- PDF text extraction often splits one wrapped
    # sentence into separate lines with no bullet marker on the tail end.
    prev_was_bullet = False
    prev_ends_sentence = True
    for raw_line in projects_section_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        is_bullet = bool(_BULLET_RE.match(stripped))
        is_wrapped_continuation = (
            not is_bullet and current and prev_was_bullet and not prev_ends_sentence
        )

        if not is_bullet and current and not is_wrapped_continuation:
            blocks.append(current)
            current = [stripped]
        else:
            current.append(stripped)

        prev_was_bullet = is_bullet
        prev_ends_sentence = stripped.endswith((".", "!", "?", ":"))
    if current:
        blocks.append(current)

    projects: list[Project] = []
    for block in blocks:
        title_line = block[0]
        title, _, tail = title_line.partition("|")
        title = _BULLET_RE.sub("", title).strip(" :-")
        if not title:
            continue

        description_lines = list(block[1:])
        if tail.strip():
            description_lines = [tail.strip()] + description_lines
        description = " ".join(_BULLET_RE.sub("", line).strip() for line in description_lines)

        block_text = "\n".join(block)
        technologies = sorted(
            {hit.term for hit in find_literal_hits(block_text, "tech", GENERAL_SKILL_VOCAB)}
        )
        evidence = find_python_evidence(block_text) + find_meaningful_ai_evidence(block_text)

        projects.append(
            Project(
                name=title[:120],
                description=description[:500],
                technologies=technologies,
                evidence=evidence,
            )
        )
    return projects


def build_candidate(clean_text: str) -> Candidate:
    sections = split_sections(clean_text)
    return Candidate(
        name=extract_name(clean_text),
        email=extract_email(clean_text),
        github_url=extract_github_url(clean_text),
        skills=extract_skills(clean_text, sections),
        projects=extract_projects(sections.get("projects", "")),
        raw_text_length=len(clean_text),
    )
