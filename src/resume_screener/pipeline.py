"""Orchestrates ingestion -> extraction -> integrity -> info -> eligibility ->
scoring -> GitHub enrichment -> ranking.

Each resume is processed inside its own try/except: a malformed or
unreadable file is recorded as a `ProcessingFailure` and the batch
continues. Nothing here ever lets one bad file abort the run.

The local stages run sequentially; the network stages (GitHub, Gemini) run
concurrently across candidates, up to `Settings.max_workers` at a time.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
    Candidate,
    EligibilityResult,
    GitHubEnrichment,
    IntegrityReport,
    ProcessingFailure,
    ScreeningResult,
)
from resume_screener.ranking import rank_candidates
from resume_screener.scoring.base import Scorer
from resume_screener.scoring.deterministic import DeterministicScorer

logger = logging.getLogger(__name__)


@dataclass
class _Analyzed:
    """Output of the local, CPU-only stages for one resume."""

    file: DiscoveredFile
    candidate: Candidate
    integrity: IntegrityReport
    eligibility: EligibilityResult
    clean_text: str


def _analyze(file: DiscoveredFile) -> _Analyzed:
    """Extraction -> integrity -> info -> eligibility. Runs sequentially:
    PyMuPDF is not thread-safe, and these stages take milliseconds anyway."""
    doc = extract_document(file.path, file.kind)

    if file.kind == "pdf":
        integrity, clean_text, _suspicious_text = analyze_spans(doc.spans)
    else:
        integrity = IntegrityReport()
        clean_text = doc.full_text

    return _Analyzed(
        file=file,
        candidate=build_candidate(clean_text),
        integrity=integrity,
        eligibility=evaluate_eligibility(clean_text),
        clean_text=clean_text,
    )


def _enrich_and_score(
    item: _Analyzed, settings: Settings, scorer: Scorer, do_github: bool
) -> ScreeningResult:
    """GitHub enrichment + scoring: the network-bound stages (GitHub API,
    Gemini), so these run concurrently across candidates."""
    if do_github:
        github = enrich_github(item.candidate.github_url, settings)
    else:
        github = GitHubEnrichment(status="disabled")

    score = None
    scoring_error = None
    if item.eligibility.eligible:
        try:
            score = scorer.score(item.candidate, item.clean_text, github)
        except Exception as exc:  # noqa: BLE001 -- a scorer failure (e.g. Gemini) must
            # never crash the batch or drop the candidate; score stays None
            # and the failure is recorded instead of fabricating a fallback.
            logger.error("Scoring failed for %s: %s", item.file.path.name, exc)
            scoring_error = str(exc)

    result = ScreeningResult(
        source_file=item.file.path.name,
        candidate=item.candidate,
        integrity=item.integrity,
        eligibility=item.eligibility,
        github=github,
        score=score,
        scoring_error=scoring_error,
    )
    result._clean_text = item.clean_text
    return result


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

    failures: list[ProcessingFailure] = []

    def _fail(file: DiscoveredFile, exc: Exception) -> None:
        logger.error("Failed to process %s: %s", file.path.name, exc)
        failures.append(
            ProcessingFailure(source_file=file.path.name, stage="pipeline", error=str(exc))
        )

    analyzed: list[_Analyzed] = []
    for file in discovered:
        try:
            analyzed.append(_analyze(file))
        except Exception as exc:  # noqa: BLE001 -- one bad resume must not halt the batch
            _fail(file, exc)

    def _safe_enrich_and_score(item: _Analyzed) -> ScreeningResult | Exception:
        try:
            return _enrich_and_score(item, settings, scorer, do_github)
        except Exception as exc:  # noqa: BLE001 -- isolate per resume, as above
            return exc

    # Network calls used to run one candidate after another; with Gemini that
    # meant ~10s x every eligible resume. pool.map keeps the input order.
    workers = max(1, min(settings.max_workers, len(analyzed)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(_safe_enrich_and_score, analyzed))

    eligible_results: list[ScreeningResult] = []
    ineligible_results: list[ScreeningResult] = []
    for item, outcome in zip(analyzed, outcomes):
        if isinstance(outcome, Exception):
            _fail(item.file, outcome)
        elif outcome.eligibility.eligible:
            eligible_results.append(outcome)
        else:
            ineligible_results.append(outcome)

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
