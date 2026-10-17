# AI Resume Screening & Ranking System

## Overview

Screens a folder of resumes (PDF required, DOCX/TXT optional) for genuine Python + AI/LLM/RAG/agentic experience, scores eligible candidates out of 100, and ranks them.

Eligibility is **always** decided deterministically, before any scoring happens. Scoring itself supports two interchangeable modes:

- **Deterministic** (default) -- reproducible, rule-based scoring over extracted evidence. No API key required.
- **Gemini** (optional) -- a semantic scorer that judges the depth of the same extracted evidence for candidates who already passed eligibility.

A CLI is the primary interface; a FastAPI backend + React frontend provide an optional browser UI on top of the same pipeline.

## Features

- PDF resume ingestion via PyMuPDF (mandatory); optional DOCX/TXT support
- Candidate extraction: name, email, GitHub URL, skills, projects
- Hard eligibility gate: genuine Python evidence **and** meaningful AI/LLM/RAG/agentic evidence
- 100-point weighted, explainable ranking with quality penalties
- Public GitHub enrichment (repos, followers, top starred repos)
- PDF integrity analysis -- detects hidden/off-page/invisible text and excludes it from evidence
- Optional Gemini semantic scorer, fully interchangeable with the deterministic scorer
- FastAPI backend + React (Vite) frontend for browser-based screening
- Per-resume and per-scoring-call error isolation -- one bad file or one scorer failure never crashes the batch

## Architecture

```
ingestion → extraction → integrity → information extraction
   → eligibility → scoring → GitHub enrichment → ranking → output
```

| Stage | Module | What it does |
|---|---|---|
| Ingestion | `ingestion.py` | Discovers resume files in the input folder, skips unsupported types |
| Extraction | `extraction/document.py` | Extracts raw text and PDF layout spans (PyMuPDF) |
| Integrity | `extraction/integrity.py` | Flags hidden/off-page text, produces the filtered `clean_text` |
| Info extraction | `extraction/info.py` | Extracts name, email, GitHub URL, skills, and projects from `clean_text` |
| Eligibility | `eligibility.py` | Deterministic hard gate (Python + AI evidence) |
| Scoring | `scoring/deterministic.py`, `scoring/gemini.py` | Weighted 100-point score, either backend |
| GitHub enrichment | `github_enrich.py` | Public GitHub API lookup, fault-tolerant |
| Ranking | `ranking.py` | Sorts eligible candidates by score |
| Output | `cli.py` / `api/main.py` | JSON file (CLI) or HTTP response (API) |

`pipeline.py` wires these stages together and isolates per-resume errors. The FastAPI layer (`api/main.py`) calls this same pipeline unchanged -- it adds a display-only requirements-match annotation but no new screening logic.

## Setup

Requires Python 3.11+.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Only needed for Gemini scoring:

```bash
pip install -e ".[gemini]"
# set GEMINI_API_KEY in .env
```

Frontend (optional, requires Node 18+):

```bash
cd frontend
npm install
cp .env.example .env   # optional; defaults to http://localhost:8000
```

## Usage

CLI, deterministic scoring (default, no API key needed):

```bash
python -m resume_screener --input ./resumes --output result.json
```

CLI, Gemini scoring:

```bash
python -m resume_screener --input ./resumes --output result.json --scorer gemini
```

Web UI (two terminals):

```bash
pip install -e ".[api]"
uvicorn resume_screener.api.main:app --reload --port 8000
```
```bash
cd frontend && npm run dev   # http://localhost:5173
```

Main CLI options:

| Flag | Purpose |
|---|---|
| `--input` | Folder of resumes (required) |
| `--output` | Output JSON path (default `result.json`) |
| `--scorer` | `deterministic` (default) or `gemini` |
| `--no-github` | Skip GitHub enrichment for this run |

## Eligibility

A candidate is eligible only if **both** hold:

1. **Genuine Python evidence** -- Python named as a skill, project technology, or work/internship technology, or a Python-specific framework/library (Django, FastAPI, pandas, ...).
2. **Meaningful AI/LLM/RAG/agentic evidence** -- a specific technology (LLM, LangChain, RAG pipeline, vector database, fine-tuning, LangGraph, Google ADK, ...) or a context-qualified term (RAG, agent, chatbot, or a provider API/model name like "OpenAI API" paired with real implementation detail). Generic words like "AI" or "machine learning" alone do not qualify.

JavaScript, Java, React, Next.js, etc. never disqualify a candidate -- they simply don't count toward either requirement above. Eligibility is fully deterministic, runs before scoring, and is never influenced by Gemini.

## Scoring (0-100, eligible candidates only)

| Component | Max points |
|---|---|
| AI / Agentic / RAG depth | 40 |
| Python & Backend engineering | 30 |
| Cloud / Deployment / Full Stack | 15 |
| GitHub activity | 10 |
| Engineering depth | 5 |

Quality penalties:

- **Thin LLM-wrapper** (-8 to -15) -- minimal AI evidence with no supporting engineering signal nearby (e.g. "used the OpenAI API" with no further detail).
- **Tutorial-style project** (-5 to -10) -- resume text matches tutorial/bootcamp/clone-style language.

Every point and penalty is recorded with a plain-English evidence line, so the final score is explainable without re-reading the resume.

## PDF Integrity

Each PDF's text spans are checked for signs that text isn't actually visible to a human reader:

- White or near-background colored text
- Near-zero-opacity or invisible-render-mode text
- Text positioned outside the visible page area
- Abnormally tiny font size

A flag is **informational only** -- it never causes automatic rejection or a scoring penalty. Flagged text is excluded from the evidence used for eligibility and scoring, so hidden keyword-stuffing can't manufacture evidence, but the candidate is judged solely on their visible content. This is a heuristic, not a complete security system (see Limitations).

## Gemini Scoring

Gemini is an **optional** scoring backend (`--scorer gemini`). It only evaluates candidates who have already passed deterministic eligibility -- it cannot grant, deny, or override eligibility. It receives only the already-extracted candidate data (skills, projects, evidence snippets), never raw resume text or hidden/suspicious PDF content. It scores AI depth, Python/backend, cloud/deployment, and engineering depth; GitHub activity is always scored deterministically. Every evidence quote it returns is checked against what was actually sent and dropped if it isn't a real match. If the Gemini API fails, times out, or returns malformed/out-of-range data, the failure is recorded on that candidate without crashing the batch or fabricating a score.

## Performance

| 10 sample resumes | Before | After |
|---|---|---|
| Parsing + GitHub lookups | 2.1 s | 0.2 s |
| With Gemini scoring (4 eligible, simulated 4 s per call) | 16.4 s | 4.0 s |

- **Concurrent network calls** -- GitHub and Gemini run for up to `MAX_WORKERS` candidates at once instead of one after another.
- **Gemini thinking off** -- `gemini-2.5-flash` reasons before answering by default, adding seconds per candidate; rubric scoring of structured evidence doesn't need it (`GEMINI_THINKING_BUDGET=0`; set `-1` for the model default).
- **One reused Gemini client**, with automatic retries when rate-limited (429/503).
- **GitHub profiles cached** per username for an hour.
- **Non-blocking API** -- `/api/screen` runs the pipeline in a worker thread, so the server keeps responding during a batch, and reuses already-extracted text instead of parsing every PDF twice.

## GitHub Enrichment

If a resume contains a `github.com/<username>` URL, the pipeline calls the public GitHub API for public repo count, followers, and top starred repos. Failures (404, rate limit, network error, disabled) are caught and recorded as a status rather than crashing the batch.

## Testing

```bash
pytest -q
```

79 tests currently pass, covering:

- Eligibility rules (Python/AI evidence, generic-word rejection, context matching)
- Deterministic scoring (bounds, determinism, penalties)
- Candidate info extraction
- PDF integrity detection, run against real PDFs
- The Gemini scorer with the network call mocked (valid/invalid responses, API failures)
- The FastAPI layer (validation, error isolation, no credential leakage)
- Concurrency (parallel scoring, same results as a sequential run), Gemini retries, GitHub caching

## Limitations

- Resume parsing (name, sections, projects) is regex/heuristic-based, not a full NLP parser -- unusual layouts may extract partial data.
- PDF integrity detection is a heuristic, not a complete security system; it does not catch every method of hiding text.
- No database or persistent storage -- results are returned as JSON per run.
- Scoped for a 2-3 hour assignment: no auth, no queues, no infrastructure beyond the CLI, API, and frontend.

## Design Decisions

- **Eligibility is deterministic and runs before scoring** because it is a hard pass/fail gate, not a matter of degree. A rule-based check is fully reproducible and auditable, and keeping it outside any LLM means the decision can never vary between runs or be affected by a model failure or hallucination.
- **Python AND meaningful AI/agentic evidence are both required** because the role needs both -- accepting either alone would let a Python-only or an AI-in-another-language-only profile pass, which doesn't match the target. Genuine evidence is accepted from any resume section (skills, projects, experience) rather than requiring corroboration across sections, since the goal is filtering out irrelevant profiles, not penalizing normal resume phrasing.
- **Deterministic scoring is the default** so the system is fully explainable, reproducible, and testable with no external dependency or API cost -- every point traces to a specific keyword match, and the same resume always produces the same score.
- **Gemini is optional and sits behind the `Scorer` interface** so a semantic scorer can be swapped in without touching ingestion, extraction, eligibility, GitHub enrichment, or ranking. This keeps the LLM adapter small and replaceable, and the deterministic scorer stays available if Gemini is unavailable or undesired.
- **GitHub enrichment is optional and fails gracefully** because a GitHub profile is a secondary signal, not part of hard eligibility -- a missing/private profile, rate limit, or network failure should never stop the batch or reject an otherwise-eligible candidate.
- **PDF integrity/hidden-text detection is a separate stage** so suspicious content (white text, off-page text, etc.) can be flagged for a human reviewer without ever being silently trusted as evidence -- this keeps "what was flagged" and "what was actually scored" cleanly separated.

**Main trade-offs:** deterministic scoring is keyword/heuristic-based, so it can miss well-described projects that avoid the exact vocabulary it looks for, and can't judge implementation quality the way a human or LLM reader could. Resume extraction is regex-based rather than a full NLP parser, so unusual layouts may extract partial data. PDF parsing runs sequentially (PyMuPDF is not thread-safe, and it takes milliseconds), while the network-bound stages -- GitHub lookups and Gemini scoring -- run concurrently, up to `MAX_WORKERS` (default 4) candidates at a time. Results are identical to a sequential run.

## If I Had More Time

- Improve resume/PDF extraction with a more robust section/project parser -- the current regex-based approach can misparse unusual layouts.
- Add recency-aware GitHub signals (recent commits/events, last-updated repos) instead of relying mainly on repo count.
- Cache Gemini results by resume content to avoid re-scoring an identical resume. (GitHub profiles are already cached for an hour.)
- Detect duplicate resumes (same candidate submitted twice, or identical file content) before scoring.
- Strengthen semantic evaluation with a small hand-labeled test set to validate Gemini's scoring calibration over time, not just its output schema.
