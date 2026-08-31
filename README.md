# AI Resume Screening & Ranking System

A deterministic, explainable backend that screens a folder of resumes for
genuine Python + AI/LLM/RAG/agentic experience, scores eligible candidates
out of 100, enriches them with public GitHub activity, and ranks them.

Eligibility is **always** deterministic -- no LLM is ever involved in
deciding whether a candidate qualifies. Scoring has two interchangeable
backends selected with `--scorer`:

- `deterministic` (default) -- a plain, reproducible rule over extracted
  text. No LLM calls, no API key needed. The same input always produces the
  same output and every point traces to a specific piece of evidence.
- `gemini` -- a semantic evaluator (Gemini API) that judges the *depth* of
  the same already-extracted evidence for candidates who already passed
  eligibility. See [Gemini scorer](#gemini-scorer) below for exactly what
  it can and can't do.

## Quickstart

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# optional: GitHub API token for higher rate limits
cp .env.example .env

python -m resume_screener --input ./resumes --output result.json
```

Run the tests:

```bash
pytest
```

Generate a small set of synthetic sample resumes (for a quick demo without
needing 50 real PDFs):

```bash
python scripts/make_sample_resumes.py
python -m resume_screener --input ./resumes --output result.json --no-github
```

### CLI options

| Flag | Description |
|---|---|
| `--input` | Folder containing resumes (required) |
| `--output` | Output JSON path (default `result.json`) |
| `--no-github` | Skip GitHub enrichment for this run |
| `--scorer` | `deterministic` (default, no LLM calls) or `gemini` (requires `GEMINI_API_KEY`) |

### Environment variables (`.env` or real env)

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | unset | Raises GitHub API rate limit from 60/hr to 5000/hr |
| `GITHUB_ENRICHMENT_ENABLED` | `true` | Turn GitHub enrichment off globally |
| `GITHUB_TIMEOUT_SECONDS` | `10` | HTTP timeout per GitHub API call |
| `GEMINI_API_KEY` | unset | Required only for `--scorer gemini` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Which Gemini model to call |
| `GEMINI_TIMEOUT_SECONDS` | `30` | HTTP timeout per Gemini API call |
| `LOG_LEVEL` | `INFO` | Python logging level |

`--scorer gemini` additionally needs the optional dependency group:
`pip install -e ".[gemini]"`. Without it (or without `GEMINI_API_KEY` set),
the CLI fails fast with a clear one-line error and exit code 1 -- it never
falls through to the deterministic scorer silently, since that would hide
a misconfiguration rather than surface it.

No credentials are ever hardcoded; `config.py` reads them exclusively from
the environment via `pydantic-settings`.

## Web UI (FastAPI + React)

A thin web layer sits on top of the CLI/pipeline for recruiters who'd rather
not use the command line: upload resumes, optionally paste/upload a job
description and custom requirements (required/preferred skills, minimum
experience), pick a scorer, and see ranked results in the browser.

**This adds no new screening logic.** `src/resume_screener/api/main.py`
saves uploads to a temp directory and calls the exact same `run_pipeline()`
the CLI uses -- eligibility, scoring, integrity, and GitHub enrichment are
completely unchanged. The only new code is:

- `api/main.py` -- the FastAPI app (`POST /api/screen`, `GET /api/health`)
- `api/matching.py` -- a small, purely additive, display-only comparison
  against recruiter-supplied extras (skill overlap, a regex years-of-
  experience detector). This never touches eligibility or score.
- `api/schemas.py` -- extends `ScreeningResult`/`BatchReport` via
  subclassing (`ScreeningResultOut`, `ScreenResponse`) rather than
  modifying the core models.

Run the backend:

```bash
pip install -e ".[api]"       # fastapi, uvicorn, python-multipart
uvicorn resume_screener.api.main:app --reload --port 8000
```

Run the frontend (separate terminal, requires Node 18+):

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

The frontend calls the backend at `VITE_API_BASE_URL` (default
`http://localhost:8000`; see `frontend/.env.example`). CORS is restricted
to `localhost:5173`/`127.0.0.1:5173` in `api/main.py`.

**Security notes specific to this layer:**
- `GITHUB_TOKEN`/`GEMINI_API_KEY` are read server-side only (`Settings`,
  built once from the environment) and never appear in any response --
  `ScreenResponse` has no field that could carry them, and
  `tests/test_api.py` asserts this directly against whatever real
  credentials happen to be configured in `.env`.
- File count (max 50) and type (`.pdf`/`.docx`/`.txt`) are validated.
  Too many files is a hard 400; an unsupported type or a file that's too
  large (>15MB) is recorded as a failure for that one file, not a batch
  rejection -- consistent with the rest of the system never letting one
  bad file take down a run.
- A malformed PDF is caught by the existing per-file isolation in
  `pipeline.py` and shows up as a `failures` entry; internal server temp-file
  paths are stripped from that error text before it reaches the client.

## Architecture

```
ingestion → document extraction → integrity analysis → info extraction
   → eligibility → scoring → GitHub enrichment → ranking → JSON output
```

| Stage | Module | Responsibility |
|---|---|---|
| Schemas | [`models.py`](src/resume_screener/models.py) | Every Pydantic model used across the pipeline (`Candidate`, `Project`, `IntegrityReport`, `ScoreBreakdown`, `GitHubEnrichment`, `ScreeningResult`, `BatchReport`) |
| Config | [`config.py`](src/resume_screener/config.py) | Environment-driven `Settings` (no secrets in code) |
| Vocabulary | [`keywords.py`](src/resume_screener/keywords.py) | Python/AI/cloud/backend/tutorial keyword sets -- plain data, easy to inspect and tune |
| Matching | [`evidence.py`](src/resume_screener/evidence.py) | Shared line-scoped keyword matcher used by both eligibility and scoring |
| 1. Ingestion | [`ingestion.py`](src/resume_screener/ingestion.py) | Discovers resume files, skips unsupported types |
| 2. Extraction | [`extraction/document.py`](src/resume_screener/extraction/document.py) | PyMuPDF text + span extraction (PDF, mandatory); DOCX/TXT readers (optional) |
| 3. Integrity | [`extraction/integrity.py`](src/resume_screener/extraction/integrity.py) | Flags visually-hidden PDF text; produces `clean_text` |
| 4. Info extraction | [`extraction/info.py`](src/resume_screener/extraction/info.py) | Name, email, GitHub URL, skills, projects |
| 5. Eligibility | [`eligibility.py`](src/resume_screener/eligibility.py) | Hard gate: genuine Python **and** meaningful AI/LLM/RAG/agentic evidence |
| 6. Scoring | [`scoring/deterministic.py`](src/resume_screener/scoring/deterministic.py), [`scoring/gemini.py`](src/resume_screener/scoring/gemini.py) | Weighted score + quality penalties; two interchangeable `Scorer` implementations, selected with `--scorer` (see below) |
| 7. GitHub enrichment | [`github_enrich.py`](src/resume_screener/github_enrich.py) | Public GitHub API, fault-tolerant |
| 8. Ranking | [`ranking.py`](src/resume_screener/ranking.py) | Sorts eligible candidates by score |
| 9. Output | [`cli.py`](src/resume_screener/cli.py) | Argument parsing + JSON output |
| Orchestration | [`pipeline.py`](src/resume_screener/pipeline.py) | Wires stages together; isolates per-resume errors |

### The Scorer seam

[`scoring/base.py`](src/resume_screener/scoring/base.py) defines a `Scorer`
Protocol:

```python
class Scorer(Protocol):
    def score(self, candidate: Candidate, clean_text: str, github: GitHubEnrichment) -> ScoreBreakdown: ...
```

Both `DeterministicScorer` ([`scoring/deterministic.py`](src/resume_screener/scoring/deterministic.py))
and `GeminiScorer` ([`scoring/gemini.py`](src/resume_screener/scoring/gemini.py))
implement this same Protocol and are interchangeable via `cli.py`'s
`--scorer` flag or by passing `scorer=...` to `run_pipeline()` directly --
nothing else in the system changes: ingestion, extraction, integrity,
eligibility, GitHub enrichment, and ranking are all scorer-agnostic.

### Gemini scorer

`GeminiScorer` is a semantic evaluator, not a second eligibility check and
not a general-purpose LLM call over the raw resume. Specifically:

- **Eligibility stays 100% deterministic and outside Gemini.** `pipeline.py`
  only ever calls `scorer.score(...)` after `eligibility.eligible` is
  already `True` (see `_process_one`). `ScoreBreakdown` has no eligibility
  field, so there is no mechanism for Gemini to accept, reject, or
  override the deterministic decision.
- **Gemini never sees raw resume text.** The `Scorer` Protocol passes
  `clean_text` to every scorer, but `GeminiScorer.score()` deliberately
  ignores it. The only data sent is
  `scoring/gemini.py::_build_evidence_payload(candidate)` -- the
  already-extracted `Candidate.name` / `skills` / `projects`
  (name, description, technologies, evidence snippets). Since `Candidate`
  is itself built from `clean_text` (the integrity-filtered text --
  suspicious/hidden PDF spans are already stripped before extraction, see
  `extraction/integrity.py`), hidden text can never reach Gemini either.
- **GitHub is never scored by Gemini.** `score_github_activity()` (the same
  deterministic 0-10 calculation `DeterministicScorer` uses) is reused
  unchanged, imported directly from `scoring/deterministic.py`.
- **Gemini only scores 4 of the 5 components** -- `ai_agentic_rag_depth`
  (0-40), `python_backend_engineering` (0-30), `cloud_deployment_fullstack`
  (0-15), `engineering_depth` (0-5). `github_activity` (0-10) comes from the
  deterministic calculation above. The final `ScoreBreakdown.total` is
  still capped at 100 the same way for both scorers.
- **Every returned evidence quote is checked against what was actually
  sent.** `_filter_grounded_evidence()` drops any string in Gemini's
  response that isn't a real substring of the JSON payload -- a defense
  against a fabricated quote slipping through even when the prompt
  explicitly forbids it.
- **The prompt (`_SYSTEM_INSTRUCTION` in `scoring/gemini.py`) explicitly
  instructs the model** not to infer implied technologies (e.g. don't
  assume a vector database just because "RAG" is mentioned), not to invent
  implementation/metrics/architecture detail, not to reward a bare
  skills-list mention as if it were demonstrated project depth, to treat
  "AI chatbot" / "used OpenAI API" with no further detail as shallow rather
  than assuming RAG/agents/tools/orchestration, to credit a named framework
  (LangChain, LangGraph, LlamaIndex, Google ADK, ...) without inventing how
  it was used, and not to let unrelated backend/cloud strength rescue a
  thin AI project's score or penalty.
- **Any failure is explicit, never silent.** An API error, timeout,
  malformed JSON, a missing field, or an out-of-range/positive-penalty
  value all raise `GeminiScoringError`. `pipeline.py` catches this per
  candidate, leaves `score=None`, and sets the new
  `ScreeningResult.scoring_error` field to the failure message -- the
  candidate stays in the output (eligibility and extracted data are
  unaffected), the batch continues, and no fallback score is fabricated.
  `--scorer deterministic` remains a fully separate, always-available mode
  if Gemini scoring isn't wanted or available.

**What is NOT verified beyond mocks:** the Gemini prompt and JSON-schema
contract are exercised by 13 mocked tests in
[`tests/test_gemini_scorer.py`](tests/test_gemini_scorer.py) (valid
response, invalid JSON, missing field, out-of-range/positive-penalty
scores, an API exception, a thin-wrapper case, a strong-evidence case, and
the evidence-grounding filter) -- no test in the suite makes a real network
call. Whether Gemini reliably returns well-calibrated *scores* in practice
(as opposed to a well-formed response) can only be judged from an actual
run with a real API key, which is a separate, manual verification step,
not something pytest asserts.

## Eligibility rules

Both must hold, evaluated only against `clean_text` (see Integrity below):

1. **Genuine Python evidence** -- the literal word "python" appearing
   anywhere (skills list, a project's tech stack, work/internship
   experience, or stated implementation language -- any of these count, per
   spec) **or** a Python-specific framework/library (Django, FastAPI,
   pandas, PyTorch, pytest, SQLAlchemy, ...). A single mention in any
   context is sufficient -- we deliberately do **not** require corroboration
   across two different resume sections.
2. **Meaningful AI/LLM/RAG/agentic evidence** -- a specific term (`LLM`,
   `LangChain`, `RAG pipeline`, `vector database`, `fine-tuning`,
   `OpenAI API`, `function calling`, ...) or an ambiguous acronym/word
   (`RAG`, `agent`, `chatbot`) that only counts when an AI-context word
   appears on the *same line* (guards against "RAG status report" or
   "customer service agent"). Bare, generic words like "AI" or "machine
   learning" alone do **not** satisfy this -- they carry no evidence of an
   actual implementation.

JavaScript, Java, React, Next.js, etc. never disqualify a candidate --
they simply don't count toward either requirement above. See
[`keywords.py`](src/resume_screener/keywords.py) for the exact vocabulary.

## Scoring (0-100, eligible candidates only)

| Component | Max | Signal |
|---|---|---|
| AI / Agentic / RAG depth | 40 | Count of strong/contextual/generic AI terms in the resume; small bonus when an AI technology is named inside an actual Projects entry |
| Python & backend engineering | 30 | Count of Python evidence + backend engineering terms (REST/GraphQL, Postgres, ORM, auth, ...) |
| Cloud / deployment / full-stack | 15 | Count of cloud/deployment terms (AWS, Docker, Kubernetes, ...) + frontend full-stack terms (React, Next.js, ...) |
| GitHub activity | 10 | Public repo count tier + a small bonus for any starred repo |
| Engineering depth | 5 | Count of rigor signals (unit tests, CI/CD, system design, Docker, ...) |

### Quality penalties

- **Thin LLM-wrapper** (-8 to -15): applied when a resume has at most one
  meaningful AI term *and* little-to-no supporting engineering signal
  (no mention of an API integration, backend, pipeline, evaluation, dataset,
  deployment, etc. anywhere). This catches "used ChatGPT to answer
  questions" style projects.
- **Tutorial-style project** (-5 to -10, scales with hit count): applied
  when the resume text matches tutorial/bootcamp/clone/course-project
  language (e.g. "Udemy", "clone of", "todo app").

Every added or subtracted point is recorded as a plain-English line in
`ScoreBreakdown.evidence` / `ScoreBreakdown.penalties[].reason`, so the
final score is fully explainable without re-reading the resume.

## PDF integrity analysis (hidden-text detection)

The system inspects the PDF's raw text spans (via PyMuPDF) for signs that
text is not actually visible to a human reader:

- **White or near-background text** -- fill color with all RGB channels ≥ 235
- **Near-zero-opacity / invisible-render-mode text** -- opacity ≤ 0.05, or
  PDF text render mode 3 (neither fill nor stroke -- the spec's "invisible" mode)
- **Text outside the page's visible bounds**
- **Abnormally tiny font** (< 1.5pt)

**A flag never causes rejection or a scoring penalty by itself.** Flagged
text is:

1. Always surfaced in `IntegrityReport` (`flags`, `suspicious_span_count`,
   `details`) for a human reviewer.
2. Excluded from `clean_text` -- the only text handed to eligibility and
   scoring -- so a resume can't manufacture Python/AI evidence, or inflate
   its score, by stuffing invisible keywords into the PDF.

A candidate is judged solely on their *visible* content; the flag exists to
tell a reviewer "this PDF also contains text a human wouldn't see," not to
accuse anyone of intent.

### Heuristic limitations (please read before trusting this as a security control)

This is pattern-matching, not a general hidden-content detector. It will
**not** catch every method of hiding text, and it **can** produce false
positives. Known gaps:

- **Assumes a white page background.** Near-white text is only suspicious
  on a white/light page; a colored resume template could either hide
  legitimate text that gets wrongly flagged, or let genuinely hidden text
  slip through if it matches a non-white background exactly.
- **Text hidden behind an image or shape is not detected** -- the check
  only looks at the text layer's own color/opacity/render mode, not what's
  drawn on top of it.
- **Legitimate invisible text exists.** OCR'd/searchable scanned PDFs
  routinely place an invisible text layer (render mode 3) over a scanned
  image on purpose -- this is normal, not malicious, and will still be
  flagged. That's why flags are informational only, never a rejection.
- **`get_texttrace()` (used for opacity/render-mode) is version-sensitive**
  in PyMuPDF; on older builds it may be unavailable, in which case those two
  checks silently degrade to "unknown" and only color/position/font-size
  checks run (see `extraction/document.py::_extract_render_modes`).
- **Off-page detection needs a widened extraction clip.** PyMuPDF's
  `get_text()` clips to the page rectangle by default, which would make
  genuinely off-page text invisible to the extractor too, not just to a
  human. We widen the clip by 5000pt in every direction
  (`OFF_PAGE_CLIP_MARGIN_PT` in `extraction/document.py`) specifically so
  this technique doesn't defeat detection -- but a resume author could
  still place hidden content just far enough to exceed that margin.
- **No cross-page or vector/rendered-glyph analysis** -- this only reasons
  about the PDF's text object stream, not a rasterized comparison against
  what actually renders on screen.

Given the 2-3 hour scope of this assignment, these tradeoffs are
intentional: the heuristics catch the common, low-effort keyword-stuffing
case demonstrated in `scripts/make_sample_resumes.py`
(`08_hidden_white_text.pdf`) while staying simple and fully unit-tested
(see `tests/test_integrity.py`).

## GitHub enrichment

If a candidate's resume contains a `github.com/<username>` URL, the
pipeline calls the public GitHub REST API (`/users/{username}` and
`/users/{username}/repos`) to pull public repo count, follower count, and
top starred repos. All failure modes are caught and mapped to a `status`
on `GitHubEnrichment` -- they never crash the batch:

| Status | Meaning |
|---|---|
| `ok` | Enrichment succeeded |
| `no_url` | No GitHub URL found in the resume |
| `not_found` | GitHub returned 404 for that username |
| `rate_limited` | GitHub API rate limit was hit |
| `disabled` | Enrichment turned off (`--no-github` or `GITHUB_ENRICHMENT_ENABLED=false`) |
| `error` | Any other network/HTTP/parsing failure (message in `error_message`) |

## Error isolation

`pipeline.py` processes each resume inside its own `try/except`. A
malformed PDF, an empty file, or an unsupported encoding is recorded as a
`ProcessingFailure` (source file, stage, error message) and the batch
continues -- exercised end-to-end by `scripts/make_sample_resumes.py`
(`09_corrupt.pdf`, `10_empty.pdf`).

A *scoring* failure (e.g. Gemini erroring out for one eligible candidate)
is isolated separately, inside `_process_one`'s own `try/except` around
`scorer.score(...)`: the candidate is still returned with its extracted
data and eligibility intact, `score` stays `None`, and
`ScreeningResult.scoring_error` carries the failure message -- it is not
recorded as a `ProcessingFailure` and does not remove the candidate from
`ranked`/`ineligible`.

## Output shape

The CLI writes one `BatchReport` JSON object:

```
{
  "generated_at": "...",
  "input_dir": "...",
  "total_files_discovered": 10,
  "eligible_count": 4,
  "ineligible_count": 4,
  "failed_count": 2,
  "ranked": [ { "rank": 1, "source_file": ..., "candidate": {...}, "score": {...}, "eligibility": {...}, "integrity": {...}, "github": {...} }, ... ],
  "ineligible": [ { "source_file": ..., "candidate": {...}, "eligibility": { "rejection_reasons": [...] }, ... } ],
  "failures": [ { "source_file": ..., "stage": "pipeline", "error": "..." } ]
}
```

## Testing

```bash
pytest -v
```

- `tests/test_eligibility.py` -- hard-gate rules, including contextual
  Python evidence, ambiguous-term gating (including context split across
  wrapped lines), and generic-word/bare-provider-API rejection
- `tests/test_scoring.py` -- determinism, score bounds, penalty triggers,
  including the thin-AI-project-with-unrelated-backend-elsewhere case
- `tests/test_info.py` -- name/email/GitHub/skills/project extraction,
  including wrapped-bullet-line project parsing
- `tests/test_integrity.py` -- hidden/off-page text detection against real
  PDFs built with PyMuPDF, and the end-to-end guarantee that hidden AI
  keyword-stuffing does not grant eligibility
- `tests/test_gemini_scorer.py` -- the Gemini scorer with the network call
  mocked out (no real API access, no API key needed): a valid response,
  invalid JSON, a missing field, out-of-range/positive-penalty scores, an
  API exception, insufficient-evidence/thin-wrapper/strong-evidence
  candidates, the evidence-grounding filter, and a pipeline-level check
  that a scoring failure never crashes the batch or drops the candidate
- `tests/test_api.py` -- the FastAPI layer: file count/type validation, a
  malformed PDF recorded as a failure (not a crash), requirements-match
  computation, a Gemini-unavailable 400, and a direct assertion that
  whatever real `GITHUB_TOKEN`/`GEMINI_API_KEY` are configured never
  appear in a response body

## Known scope limitations

- Name/section/project parsing are regex/heuristic-based, not a full NLP
  resume parser -- unusual resume layouts may extract partial or missing
  fields. This is intentional: correctness and explainability were
  prioritized over handling every possible resume format in a 2-3 hour scope.
- No database, no frontend, no queue/worker infra -- a single CLI run over
  a folder, by design.
