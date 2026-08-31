"""CLI entry point.

    python -m resume_screener --input ./resumes --output result.json
    python -m resume_screener --input ./resumes --output result.json --scorer gemini
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from resume_screener.config import Settings, get_settings
from resume_screener.logging_setup import configure_logging
from resume_screener.pipeline import run_pipeline
from resume_screener.scoring.base import Scorer
from resume_screener.scoring.deterministic import DeterministicScorer

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Resume Screening & Ranking System")
    parser.add_argument("--input", required=True, type=Path, help="Folder containing resumes")
    parser.add_argument("--output", type=Path, default=Path("result.json"), help="Output JSON path")
    parser.add_argument(
        "--no-github", action="store_true", help="Disable GitHub enrichment for this run"
    )
    parser.add_argument(
        "--scorer",
        choices=["deterministic", "gemini"],
        default="deterministic",
        help=(
            "Scoring backend for eligible candidates. 'deterministic' (default) "
            "makes no LLM calls; 'gemini' requires GEMINI_API_KEY."
        ),
    )
    return parser


def _build_scorer(name: str, settings: Settings) -> Scorer:
    if name == "gemini":
        from resume_screener.scoring.gemini import GeminiScorer  # optional dependency

        return GeminiScorer(settings)
    return DeterministicScorer()


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    args = build_arg_parser().parse_args(argv)

    try:
        scorer = _build_scorer(args.scorer, settings)
    except Exception as exc:  # noqa: BLE001 -- e.g. missing GEMINI_API_KEY or missing SDK
        logger.error("Could not initialize '%s' scorer: %s", args.scorer, exc)
        return 1

    report = run_pipeline(
        args.input,
        settings=settings,
        scorer=scorer,
        github_enrichment=False if args.no_github else None,
    )

    args.output.write_text(report.model_dump_json(indent=2))
    logger.info(
        "Processed %d file(s): %d eligible, %d ineligible, %d failed. Output -> %s",
        report.total_files_discovered,
        report.eligible_count,
        report.ineligible_count,
        report.failed_count,
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
