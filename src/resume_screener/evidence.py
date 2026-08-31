"""Shared keyword/phrase matching over resume text.

Line-scoped, case-insensitive, word-boundary matching. Kept in one place so
eligibility and scoring apply the exact same notion of "a term matched" --
including the context-gating for ambiguous acronyms like "RAG" or "agent",
and for generic provider-API/model names like "OpenAI API" or "GPT-4".
"""

from __future__ import annotations

import re

from resume_screener.keywords import (
    AI_AMBIGUOUS_TERMS,
    AI_GENERIC_TERMS,
    AI_PROVIDER_API_TERMS,
    AI_STRONG_TERMS,
    PYTHON_FRAMEWORKS,
)
from resume_screener.models import EvidenceHit

# How many lines on either side of a term's own line also count as its
# "context" when checking for a nearby qualifying word. Small and local on
# purpose: enough to survive a PDF wrapping one sentence across two lines,
# not so wide that an unrelated mention elsewhere in the resume can satisfy
# the requirement.
AMBIGUOUS_CONTEXT_WINDOW = 1

_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _term_pattern(term: str) -> re.Pattern[str]:
    pattern = _PATTERN_CACHE.get(term)
    if pattern is None:
        # Split on whitespace/hyphen first, then escape each piece, so that
        # e.g. "scikit-learn" matches both "scikit-learn" and "scikit learn".
        parts = [p for p in re.split(r"[\s\-]+", term.strip()) if p]
        joined = r"[\s\-]+".join(re.escape(p) for p in parts)
        pattern = re.compile(rf"\b{joined}\b", re.IGNORECASE)
        _PATTERN_CACHE[term] = pattern
    return pattern


def _snippet(line: str, limit: int = 140) -> str:
    line = line.strip()
    return line if len(line) <= limit else line[: limit - 1] + "…"


def find_literal_hits(text: str, category: str, terms: set[str]) -> list[EvidenceHit]:
    hits: list[EvidenceHit] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        for term in terms:
            if term in seen:
                continue
            if _term_pattern(term).search(line):
                hits.append(EvidenceHit(category=category, term=term, snippet=_snippet(line)))
                seen.add(term)
    return hits


def find_ambiguous_hits(
    text: str,
    category: str,
    ambiguous_terms: dict[str, set[str]],
    context_window: int = AMBIGUOUS_CONTEXT_WINDOW,
) -> list[EvidenceHit]:
    """Match a term that only counts when a context word appears nearby.

    "Nearby" means within `context_window` lines of the term's own line
    (default: the line itself plus one line before/after), not merely the
    same line -- this tolerates a PDF wrapping one sentence across two
    lines without letting an unrelated mention elsewhere in the resume
    satisfy the requirement.
    """
    lines = text.splitlines()
    hits: list[EvidenceHit] = []
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        for term, context_words in ambiguous_terms.items():
            if term in seen:
                continue
            if not _term_pattern(term).search(line):
                continue
            start = max(0, idx - context_window)
            end = min(len(lines), idx + context_window + 1)
            window_text = " ".join(lines[start:end]).lower()
            if any(ctx in window_text for ctx in context_words):
                hits.append(EvidenceHit(category=category, term=term, snippet=_snippet(line)))
                seen.add(term)
    return hits


_PYTHON_LITERAL = {"python", "python3"}


def find_python_evidence(text: str) -> list[EvidenceHit]:
    literal = find_literal_hits(text, "python", _PYTHON_LITERAL)
    frameworks = find_literal_hits(text, "python", PYTHON_FRAMEWORKS)
    return literal + frameworks


def find_ai_strong_evidence(text: str) -> list[EvidenceHit]:
    return find_literal_hits(text, "ai", AI_STRONG_TERMS)


def find_ai_ambiguous_evidence(text: str) -> list[EvidenceHit]:
    return find_ambiguous_hits(text, "ai", AI_AMBIGUOUS_TERMS) + find_ambiguous_hits(
        text, "ai", AI_PROVIDER_API_TERMS
    )


def find_ai_generic_evidence(text: str) -> list[EvidenceHit]:
    return find_literal_hits(text, "ai_generic", AI_GENERIC_TERMS)


def find_meaningful_ai_evidence(text: str) -> list[EvidenceHit]:
    """AI evidence specific enough to satisfy the hard-eligibility bar."""
    return find_ai_strong_evidence(text) + find_ai_ambiguous_evidence(text)
