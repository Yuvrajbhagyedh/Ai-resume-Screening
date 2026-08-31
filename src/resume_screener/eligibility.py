"""Deterministic hard eligibility gate.

Both conditions must hold:

1. Genuine Python evidence -- the literal word "python" (as a skill, project
   technology, work/internship technology, or stated implementation
   language -- any context counts, per the assignment) OR a Python-specific
   framework/library (Django, FastAPI, pandas, PyTorch, ...).
2. Meaningful AI/LLM/RAG/agentic evidence -- a specific term (LLM,
   LangChain, RAG pipeline, vector database, fine-tuning, ...) or an
   ambiguous acronym/word (RAG, agent, chatbot) used in an AI-specific
   context. Bare, generic words like "AI" or "machine learning" alone do
   NOT satisfy this -- they carry no evidence of actual implementation.

Evidence is drawn only from `clean_text` (the integrity-filtered text), so
text that is visually hidden in the PDF can never manufacture eligibility.
Other languages/frameworks (JS, Java, React, Next.js, ...) never disqualify
a candidate -- they simply don't count toward either requirement above.
"""

from __future__ import annotations

from resume_screener.evidence import find_meaningful_ai_evidence, find_python_evidence
from resume_screener.models import EligibilityResult


def evaluate_eligibility(clean_text: str) -> EligibilityResult:
    python_hits = find_python_evidence(clean_text)
    ai_hits = find_meaningful_ai_evidence(clean_text)

    reasons: list[str] = []
    if not python_hits:
        reasons.append(
            "No genuine Python evidence found (no mention of Python, or a "
            "Python-specific framework/library such as Django, FastAPI, pandas)."
        )
    if not ai_hits:
        reasons.append(
            "No meaningful AI/LLM/RAG/agentic evidence found -- generic words "
            "like 'AI' or 'machine learning' alone don't qualify; a specific "
            "technology or implementation (LLM, RAG, agent, LangChain, "
            "vector database, fine-tuning, etc.) is required."
        )

    return EligibilityResult(
        eligible=not reasons,
        python_evidence=python_hits,
        ai_evidence=ai_hits,
        rejection_reasons=reasons,
    )
