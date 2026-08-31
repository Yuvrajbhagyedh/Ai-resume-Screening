"""FastAPI layer around the existing screening pipeline.

This module contains NO screening logic of its own. It:
  1. Validates and saves uploaded files to a temp directory.
  2. Calls the exact same `run_pipeline()` the CLI uses (pipeline.py) --
     eligibility, scoring, integrity, and GitHub enrichment are completely
     unchanged and untouched by the web layer.
  3. Adds a purely additive, display-only requirements-match annotation
     (api/matching.py) for recruiter-supplied extras.
  4. Deletes the temp directory before returning.

Security: `Settings` (which holds GITHUB_TOKEN/GEMINI_API_KEY) is read once
from the server environment and never serialized into any response --
`ScreenResponse` has no field that could carry it.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from resume_screener.api.matching import build_requirements_match
from resume_screener.api.schemas import ScreenResponse, ScreeningResultOut
from resume_screener.config import Settings, get_settings
from resume_screener.extraction.document import extract_document
from resume_screener.extraction.integrity import analyze_spans
from resume_screener.ingestion import SUPPORTED_EXTENSIONS
from resume_screener.logging_setup import configure_logging
from resume_screener.models import ProcessingFailure, ScreeningResult
from resume_screener.pipeline import run_pipeline
from resume_screener.scoring.base import Scorer
from resume_screener.scoring.deterministic import DeterministicScorer

logger = logging.getLogger(__name__)

MAX_RESUMES = 50
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB -- generous for a resume PDF

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="AI Resume Screening API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_scorer(name: str, settings: Settings) -> Scorer:
    """Mirrors cli.py's scorer dispatch. Duplicated rather than imported
    because it's 4 lines and cli._build_scorer is a private helper -- not
    worth the cross-module coupling."""
    if name == "gemini":
        from resume_screener.scoring.gemini import GeminiScorer  # optional dependency

        return GeminiScorer(settings)
    return DeterministicScorer()


def _parse_skill_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _read_clean_text(path: Path) -> str | None:
    """Best-effort re-extraction of a saved file's integrity-filtered text,
    used only for the display-only experience-years heuristic. Never used
    for eligibility/scoring -- those already ran inside run_pipeline()."""
    kind = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
    if kind is None or not path.exists():
        return None
    try:
        doc = extract_document(path, kind)
        if kind == "pdf":
            _, clean_text, _ = analyze_spans(doc.spans)
        else:
            clean_text = doc.full_text
        return clean_text
    except Exception as exc:  # noqa: BLE001 -- best-effort only, never blocks the response
        logger.warning("Could not re-read text for requirements matching (%s): %s", path.name, exc)
        return None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/screen", response_model=ScreenResponse)
async def screen_candidates(
    resumes: list[UploadFile] = File(...),
    job_description_text: str | None = Form(None),
    job_description_file: UploadFile | None = File(None),
    required_skills: str | None = Form(None),
    preferred_skills: str | None = Form(None),
    minimum_experience_years: float | None = Form(None),
    scorer: Literal["deterministic", "gemini"] = Form("deterministic"),
    github_enrichment: bool | None = Form(None),
) -> ScreenResponse:
    if not resumes:
        raise HTTPException(status_code=400, detail="At least one resume file is required.")
    if len(resumes) > MAX_RESUMES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: {len(resumes)} uploaded, maximum is {MAX_RESUMES}.",
        )

    try:
        scorer_instance = _build_scorer(scorer, settings)
    except Exception as exc:  # noqa: BLE001 -- e.g. missing GEMINI_API_KEY or missing SDK
        raise HTTPException(status_code=400, detail=f"'{scorer}' scorer unavailable: {exc}") from exc

    tmpdir = Path(tempfile.mkdtemp(prefix="resume_screen_"))
    upload_failures: list[ProcessingFailure] = []
    saved_names: set[str] = set()
    jd_path: Path | None = None

    try:
        for upload in resumes:
            filename = Path(upload.filename or "").name  # strip any path components
            suffix = Path(filename).suffix.lower()
            if not filename or suffix not in SUPPORTED_EXTENSIONS:
                upload_failures.append(
                    ProcessingFailure(
                        source_file=filename or "(unnamed file)",
                        stage="upload",
                        error=f"Unsupported file type '{suffix or 'unknown'}'. Allowed: .pdf, .docx, .txt",
                    )
                )
                continue

            content = await upload.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                upload_failures.append(
                    ProcessingFailure(
                        source_file=filename,
                        stage="upload",
                        error=f"File too large ({len(content)} bytes, max {MAX_FILE_SIZE_BYTES}).",
                    )
                )
                continue

            # de-duplicate filenames so two uploads named "resume.pdf" don't clobber each other
            target_name = filename
            counter = 1
            while target_name in saved_names:
                target_name = f"{Path(filename).stem}_{counter}{suffix}"
                counter += 1
            saved_names.add(target_name)

            (tmpdir / target_name).write_bytes(content)

        job_description_text_final = (job_description_text or "").strip()
        if job_description_file is not None and job_description_file.filename:
            jd_suffix = Path(job_description_file.filename).suffix.lower()
            jd_kind = SUPPORTED_EXTENSIONS.get(jd_suffix)
            if jd_kind:
                jd_bytes = await job_description_file.read()
                fd, jd_path_str = tempfile.mkstemp(suffix=jd_suffix)
                os.close(fd)
                jd_path = Path(jd_path_str)
                jd_path.write_bytes(jd_bytes)
                jd_clean_text = _read_clean_text(jd_path)
                if jd_clean_text and jd_clean_text.strip():
                    job_description_text_final = jd_clean_text

        report = run_pipeline(
            tmpdir,
            settings=settings,
            scorer=scorer_instance,
            github_enrichment=github_enrichment,
        )

        # Strip the server's internal temp-dir path out of any pipeline error
        # message before it goes to the client -- filesystem layout isn't a
        # secret, but there's no reason to expose it either.
        for failure in report.failures:
            failure.error = failure.error.replace(f"{tmpdir}/", "").replace(str(tmpdir), "")

        required = _parse_skill_list(required_skills)
        preferred = _parse_skill_list(preferred_skills)

        def _to_out(result: ScreeningResult) -> ScreeningResultOut:
            candidate_text = _read_clean_text(tmpdir / result.source_file)
            match = build_requirements_match(
                candidate_skills=result.candidate.skills,
                candidate_text=candidate_text,
                required_skills=required,
                preferred_skills=preferred,
                minimum_experience_years=minimum_experience_years,
                job_description_text=job_description_text_final,
            )
            return ScreeningResultOut(**result.__dict__, requirements_match=match)

        ranked_out = [_to_out(r) for r in report.ranked]
        ineligible_out = [_to_out(r) for r in report.ineligible]
        all_failures = upload_failures + report.failures

        return ScreenResponse(
            generated_at=report.generated_at,
            total_files_discovered=len(resumes),
            eligible_count=report.eligible_count,
            ineligible_count=report.ineligible_count,
            failed_count=len(all_failures),
            ranked=ranked_out,
            ineligible=ineligible_out,
            failures=all_failures,
            scorer_used=scorer,
            job_description_provided=bool(job_description_text_final.strip()),
            required_skills=required,
            preferred_skills=preferred,
            minimum_experience_years=minimum_experience_years,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if jd_path is not None:
            jd_path.unlink(missing_ok=True)
