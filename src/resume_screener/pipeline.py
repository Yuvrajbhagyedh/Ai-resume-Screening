"""Orchestrates ingestion -> extraction -> integrity -> info -> eligibility ->
scoring -> GitHub enrichment -> ranking.

Each resume is processed inside its own try/except: a malformed or
unreadable file is recorded as a `ProcessingFailure` and the batch
continues. Nothing here ever lets one bad file abort the run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from resume_screener.config import Settings, get_settings
from resume_screener.eligibility import evaluate_eligibility
from resume_screener.extraction.document import extract_document
from resume_screener.extraction.info import build_candidate
from resume_screener.extraction.integrity import analyze_spans
from resume_screener.github_enrich import enrich as enrich_github
from resume_screener.ingestion import DiscoveredFile, discover_resumes
from resume_screener.models import (
    BatchReport,
    GitHubEnrichment,
    IntegrityReport,
    ProcessingFailure,
    ScreeningResult,
)
from resume_screener.ranking import rank_candidates
from resume_screener.scoring.base import Scorer
from resume_screener.scoring.deterministic import DeterministicScorer

logger = logging.getLogger(__name__)


def _process_one(
    file: DiscoveredFile, settings: Settings, scorer: Scorer, do_github: bool
) -> ScreeningResult:
    doc = extract_document(file.path, file.kind)

    if file.kind == "pdf":
        integrity, clean_text, _suspicious_text = analyze_spans(doc.spans)
    else:
        integrity = IntegrityReport()
        clean_text = doc.full_text

    candidate = build_candidate(clean_text)
    eligibility = evaluate_eligibility(clean_text)

    if do_github:
        github = enrich_github(candidate.github_url, settings)
    else:
        github = GitHubEnrichment(status="disabled")

    score = None
    scoring_error = None
    if eligibility.eligible:
        try:
            score = scorer.score(candidate, clean_text, github)
        except Exception as exc:  # noqa: BLE001 -- a scorer failure (e.g. Gemini) must
            # never crash the batch or drop the candidate; score stays None
            # and the failure is recorded instead of fabricating a fallback.
            logger.error("Scoring failed for %s: %s", file.path.name, exc)
            scoring_error = str(exc)

    return ScreeningResult(
        source_file=file.path.name,
        candidate=candidate,
        integrity=integrity,
        eligibility=eligibility,
        github=github,
        score=score,
        scoring_error=scoring_error,
    )


def run_pipeline(
    input_dir: Path,
    settings: Settings | None = None,
    scorer: Scorer | None = None,
    github_enrichment: bool | None = None,
) -> BatchReport:
    settings = settings or get_settings()
    scorer = scorer or DeterministicScorer()
    do_github = settings.github_enrichment_enabled if github_enrichment is None else github_enrichment

    discovered = discover_resumes(input_dir)
    logger.info("Discovered %d resume file(s) in %s", len(discovered), input_dir)

    eligible_results: list[ScreeningResult] = []
    ineligible_results: list[ScreeningResult] = []
    failures: list[ProcessingFailure] = []

    for file in discovered:
        try:
            result = _process_one(file, settings, scorer, do_github)
        except Exception as exc:  # noqa: BLE001 -- one bad resume must not halt the batch
            logger.error("Failed to process %s: %s", file.path.name, exc)
            failures.append(
                ProcessingFailure(source_file=file.path.name, stage="pipeline", error=str(exc))
            )
            continue

        if result.eligibility.eligible:
            eligible_results.append(result)
        else:
            ineligible_results.append(result)

    ranked = rank_candidates(eligible_results)

    return BatchReport(
        input_dir=str(input_dir),
        total_files_discovered=len(discovered),
        eligible_count=len(ranked),
        ineligible_count=len(ineligible_results),
        failed_count=len(failures),
        ranked=ranked,
        ineligible=ineligible_results,
        failures=failures,
    )
