# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Healthfolio: an AI healthcare support system. Users upload medical documents (lab reports, prescriptions, discharge summaries, consultation notes, imaging and test reports); a worker reads them into structured records; the app shows summaries, a timeline, alerts, and a health profile. Not multimodal yet: scan images are not interpreted (planned).

## Commands

Database first (PostgreSQL 16 in Docker; creates `healthcare_dev` and `healthcare_test`): `docker compose up -d`

Backend (`backend/`, Python 3.12 via uv). If another virtualenv is active, unset `VIRTUAL_ENV` first.
```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000     # API at /api/v1, docs at /api/v1/docs (dev only)
uv run python -m app.worker                          # extraction worker (--once: drain queue and exit)
uv run alembic upgrade head
uv run ruff check . && uv run ruff format .
uv run pytest                                        # integration tests need the DB running
uv run pytest -m "not integration"
uv run pytest tests/test_source_and_dates.py::test_matching_helpers   # single test
RUN_LIVE_AI=1 uv run pytest -m live                  # real Groq call (costs quota)
uv run python -m evaluation run --quick --tag <name> # accuracy evaluation, real AI calls
uv run python -m evaluation report --tag <name> --baseline <older-tag>
```

Frontend (`frontend/`, React + Vite + TypeScript):
```bash
npm run dev            # http://localhost:5173
npm run lint           # oxlint (do NOT run Prettier; it reformats the codebase)
npm run test           # vitest; one file: npx vitest run src/documents/extraction.test.tsx
npm run build          # tsc -b + vite build
```
Vitest tests can time out (5 s) when the machine is busy; rerun the file before treating it as a failure.

## Architecture

**Backend layers** (`backend/app`): `api/v1` (FastAPI routers) → `services` (business rules) → `repositories`/`models` (SQLAlchemy 2, Alembic migrations in `alembic/versions`, numbered `00NN_*.py`). `core/config.py` holds all settings (pydantic-settings from `.env`) with production safety checks (CORS, secure cookies, no file email, S3 bucket when `STORAGE_BACKEND=s3`). Document files go through the `DocumentStorage` interface (`services/storage.py`: local disk or S3).

**Extraction pipeline** (upload → `processing_jobs` row → `app/worker.py` → `services/extraction_service.py`):
1. `ai/reading.py` gets text: PyMuPDF for digital PDFs, Tesseract OCR for scans; pages under `OCR_MIN_CONFIDENCE` go to the AI as images ("vision").
2. `ai/extractor.py` calls Groq (`qwen/qwen3.8-27b`) with a strict JSON schema per document kind (`ai/schema.py`). Prompt versions (`PROMPT_VERSION`, etc.) are recorded on each job; bump them when a prompt changes. Empty answers for pages with content are re-read, then fail as `ai_empty_output`.
3. Deterministic validation decides everything the AI must not: `ai/validation.py` (labs), `prescription_validation.py`, `discharge_validation.py`, `report_validation.py`. Supporting rules:
   - `ai/readability.py`: "Not mentioned" (not printed) vs "Not identified" (printed but unreadable; never a guess, never compared with a range).
   - `ai/source_check.py`: each value must be on its own test's line in the document text; values from another row become Not identified; results from image pages are never compared.
   - `ai/dates.py`: dates are shown exactly as printed; a day/month-ambiguous date ("02/09/26") keeps no calendar date, and no due date is calculated from it.
4. Summaries are rule-based, never AI: `services/lab_summary.py` (above/below/normal/invalid against the range printed on the report), `discharge_summary.py`, `prescription_summary.py`, `report_summaries.py`. Alerts (`alert_service.py`) use the same rules.

AI summaries (`services/summary_service.py`) work only from already-extracted records given as numbered facts; code removes sentences whose numbers or sources don't match.

**Frontend** (`frontend/src`): feature folders (`documents`, `timeline`, `profile`, `medications`, …), each with its own API module and tests. `api/client.ts` wraps fetch with the base URL from `config.ts` (`VITE_API_BASE_URL`, required in production builds).

**Specs** in `spec/` are the source of truth for decisions (e.g. `AI_spec.md` §4.5 records the validation decisions with dates). Update the relevant spec section when changing a decided behaviour.

**Evaluation** (`backend/evaluation`): seeded fictional cases rendered as digital and damaged scans, run through the real pipeline, scored (misleading fields/groups, Not identified, dates as printed). Output in `backend/evaluation/out/` (git-ignored).

## Testing conventions

- Backend tests use a fake Groq client (`tests/ai_fakes.py`: `FakeGroq`, `payload`, `result`, `prescription`, …). Because of the source-line check, an uploaded test PDF must print what the fake AI returns: use `printed_lines(...)` (`ai_fakes.py`, `test_discharge.py`) with `upload_report(..., lines=...)`.
- `conftest.py` points `DATABASE_URL` at `healthcare_test`.

## Deployment

- `backend/Dockerfile` runs migrations, the worker, and the API in one container (`start.sh`); it includes Tesseract.
- AWS (ap-south-1) is defined in `infra/` (Terraform; state in S3 bucket `healthfolio-tfstate-<account>`): CloudFront serves the site from S3 and forwards `/api/*` to a Lightsail container service; RDS PostgreSQL (private, via Lightsail VPC peering); documents in S3 (`STORAGE_BACKEND=s3`). Steps in `infra/README.md`. The user runs `terraform apply`; secrets (DB password in Secrets Manager, Groq key, JWT secret, the app's access key) never go into Terraform or the repo.
- The account has no CodeBuild capacity and local Docker cannot reach Docker Hub, so images are built locally from a `public.ecr.aws` base image and pushed to ECR.

## Repository rules

- Commit only as `snimadolma95@gmail.com`; commit/push only when asked. Stage by explicit path.
- Never commit `sample medical reports/` or `groud truths/` (untracked on purpose; they were removed from history before the repo went public).
- When a change alters decided behaviour, configuration (env vars), the data model, or deployment, update the matching `spec/` section, `backend/.env.example`, and the README in the same change.
- Execution reports go in `project_reports/` (git-ignored).
- Secrets (`GROQ_API_KEY`, `JWT_SECRET`, DB passwords, AWS keys) live only in `backend/.env` or the hosting console; the user enters them.
