# Healthfolio

**Your medical history, organised and explained.** An AI healthcare support system.

A personal health-records platform that stores medical documents, extracts and organizes their information, tracks medications and follow-ups, and provides cautious, source-backed AI summaries. It offers informational decision support only and does not replace professional medical care.

**Live demo:** https://65-0-63-32.sslip.io (use synthetic documents only; uploaded text is sent to the AI provider).

> **Status:** all the features below are in place and deployed on AWS.

> [!IMPORTANT]
> **AI accuracy has not been rigorously validated.** The built-in evaluation uses fictional reports only; it is not clinical validation, and the target of 98% accuracy on critical fields is not met yet. Rigorous validation, on a de-identified real-document set with repeated runs, is planned for the future. Use synthetic documents only, and always check results against the original document.

## Screenshots

Screens from a demo account with fictional sample reports.

| Upload (digital or scanned) | Check what was read |
|---|---|
| ![Upload form](frontend/public/welcome/upload.webp) | ![Original beside extracted results](frontend/public/welcome/document.webp) |
| **Dashboard** | **AI summary with sources** |
| ![Dashboard](frontend/public/welcome/dashboard.webp) | ![AI summary](frontend/public/welcome/summary.webp) |

## Architecture

![Healthfolio end-to-end architecture](docs/architecture/healthfolio-architecture.png)

1. The browser talks only to **Caddy**, over HTTPS. Caddy serves the React site and passes `/api/*` to the **FastAPI API**.
2. The API stores records and queues reading jobs in **PostgreSQL**, and keeps uploads in **S3**.
3. The **extraction worker**:
   - reads each upload (PyMuPDF or Tesseract OCR);
   - asks **Groq** for structured fields;
   - applies the validation rules before anything is shown.
4. Secrets and the API image come from AWS (Secrets Manager / SSM, ECR).

Diagram source: [`docs/architecture/healthfolio-architecture.json`](docs/architecture/healthfolio-architecture.json). Full walkthrough: [docs/END_TO_END.md](docs/END_TO_END.md).

## How a Document Is Read

> [!IMPORTANT]
> **AI accuracy has not been rigorously validated.** The built-in evaluation uses fictional reports only; it is not clinical validation, and the target of 98% accuracy on critical fields is not met yet. Rigorous validation, on a de-identified real-document set with repeated runs, is planned for the future. Use synthetic documents only, and always check results against the original document.

![How a document is read: upload, queue, get text, Groq AI, check rules, summary](docs/architecture/extraction-pipeline.png)

**The AI only reads; fixed rules in code decide what you see.**

| Step | What happens |
|---|---|
| **1. Upload** | You choose the report type (and optional sub-type), and whether it is a **digital PDF** or a **scanned copy**. Blurry, dark, blank, or tiny scans are sent back for a clearer copy. |
| **2. Queue** | The upload is saved and a reading job is queued. The worker picks it up within seconds. |
| **3. Get text** | Digital PDF: **PyMuPDF** reads the text layer. Scan: **Tesseract OCR** at 300 DPI, cleaned up, table rows kept together. A page under 85% OCR confidence goes to the AI as an **image** instead. |
| **4. Groq AI** | Returns the fields in a **strict JSON schema** for that document type, copying values exactly as written. An empty answer for a page with text is read again, up to 3 times. |
| **5. Check rules** | Code, not AI, checks every value (see the table below). Anything doubtful is marked for review. |
| **6. Summary** | A plain-language summary built by rules, with each value linked to its source. **Refresh analysis** reads the document again. |

### What each report type gives you

| Document | Summary on the document page |
|---|---|
| 🧪 **Laboratory reports** | Values **above**, **below**, and **within** the range printed on the report, plus **invalid records** (no range, not a single number, or unclear), shown as written and never judged |
| 💊 **Prescription** | Date and doctor; each medicine with instructions and duration, with dosing notation explained ("1-0-1" → morning and night); follow-ups by date ("after 4 weeks" is calculated by code and labelled); "only if needed" follow-ups ("review if not better / SOS") are shown but never dated |
| 🏥 **Discharge summary** (one page) | Hospital, stay and number of days, diagnoses as written, key results (first → last), discharge medicines, follow-ups, when to return to the emergency department |
| 🩺 **Consultation note** | Symptoms, observations, assessment, plan, follow-ups |
| 🩻 **Text-based imaging reports** | Findings, impression, and the report's own uncertainty statements (written reports only; scan images are not read yet) |
| 🔬 **Pathology reports** | Specimen, clinical history, gross and microscopic description, diagnosis, tumour details, special tests, and comments, exactly as written; the diagnosis is suggested for your Health Profile |
| 📈 **Specialist reports** (ECG, echo, spirometry, ...) | Measurements against their printed ranges; findings; machine and physician conclusions kept apart; recommendations and follow-ups to add |

### The rules that keep results honest

| On the document | What Healthfolio shows | Rule |
|---|---|---|
| A unit that is not printed | **Not mentioned** | Nothing is guessed |
| `Albumin 2.7 g/dL`, which OCR misreads as `2,` | **Not identified** – check the original | Printed but unreadable: never guessed, never compared |
| AST and Ferritin values swapped between rows | **Not identified** for both | Each value must be on its own test's line |
| `Date: 02/09/26` | `02/09/26`, exactly as printed | Day and month could be swapped, so no date is calculated from it |
| `Total Protein 162 g/dL (6.4 – 8.3)` | Above range, with *"Unusually far outside the range: check the original"* | More than 10× outside a printed range suggests a misread |
| `CRP 5.0 (< 5.0)` | Above range | Printed ranges are applied exactly; the AI never decides |
| A medicine on a prescription | *Not confirmed* | Never marked as "taking" until you confirm it |
| A scanned medicines table where OCR lost the Frequency and Duration columns | `1-0-1 (twice daily, after food)`, `5 days` | The page is read again as an image; only a field still unreadable is **Not identified** |

## Features

| Feature | What it does |
|---|---|
| **Diagnoses and Conditions** | Health issues written in your documents (discharge and pathology diagnoses, consultation assessments, imaging impressions), exactly as written, tracked across documents with first and last date; one click adds one to Health Profile. The app does not diagnose. |
| **Health Profile** | Your name; body measurements (height, weight, calculated BMI with its adult category); medical history (conditions, surgeries, hospital stays, including stays from discharge summaries); vital signs as dated readings (blood pressure and heart rate, never labelled high or low); medications (prescription, over-the-counter, supplements); allergies with type and reaction (shown first); family history. Every change is kept in a history. Diagnoses read from discharge summaries and pathology reports join the profile only when you accept or correct them. |
| **Dashboard** | One page with open and urgent alerts, items to review, overdue and upcoming follow-ups, recent documents and their reading status, profile completeness, allergies, BMI, latest vital signs, and recent activity. |
| **Health Timeline** | All records in date order, with lab results grouped per report date. Each entry shows its source and whether you confirmed or changed it. Results from different dates are never combined. It can be filtered by category and date. |
| **Search** | Finds any word across tests, medicines, diagnoses, report text, allergies, and history, with the matching field highlighted. It can be narrowed by type, hospital, condition, and dates. The search text is never put in the address or the logs. |
| **Medical Documents** | Listed by report type (with report sub-type) by default; filter by type, date range, and hospital; group by type, month, or hospital, or not at all, with counts. The choices are kept in the page address. |
| **Medications** | Grouped as taking now, not confirmed, or stopped. You can edit, mark taking or stopped, or remove a medicine, and each keeps a full change history. Medicines you changed are kept when a document is read again. |
| **Checkups and Follow-ups** | Follow-ups from prescriptions and reports, added when you choose; each can be marked done or cancelled, or deleted permanently after a confirmation. |
| **Alerts** | Fixed, documented rules, never AI. A result outside its printed range is flagged as something to review with a doctor, not a diagnosis. Each alert explains why it was raised, what to do next, and its source. Alerts can be acknowledged and resolved, and keep their history. Emergency guidance is always shown. |
| **AI Summaries and Insights** | Only when you ask. The AI works from the details read from your documents and what you entered in Health Profile, Medications, Follow-ups, and Vitals, given as numbered facts it must cite; code removes any sentence whose numbers, months, or sources do not match. Interpretations and general information are labelled. Your name, email, and date of birth are never sent. |
| **Account and Privacy** | Change your password (other devices are signed out). Export a PDF health summary, JSON or CSV records, or a ZIP of your originals; each is prepared on request and never stored. Deleting your account needs your password and the word DELETE, and removes everything at once. |
| **Welcome page** | A public introduction (`/welcome`) with a screenshot tour of each step. |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 (Docker Compose for local development) |
| Frontend | React, Vite, TypeScript, React Router |
| Text reading | PyMuPDF (digital-PDF text), Tesseract OCR via pytesseract (scanned copies and photos), Pillow (image clean-up) |
| AI | Qwen3.8-27B on Groq (official Groq SDK): organises the text into structured fields; reads page images only when OCR cannot |
| Exports | fpdf2 (PDF health summary), standard-library CSV, JSON, and ZIP |
| Background jobs | PostgreSQL job queue + worker process |
| Testing | pytest (backend), Vitest + Testing Library (frontend) |
| Tooling | uv (Python), npm, ruff, oxlint |

## Project Structure

```
├── .github/workflows/       CI (tests on every push and pull request) and deploy to AWS
├── backend/                 FastAPI application
│   ├── app/
│   │   ├── ai/              Reading (PyMuPDF, OCR), Groq extraction, validation rules
│   │   ├── api/v1/          Versioned API routes (/api/v1)
│   │   ├── core/            Config, logging, errors, middleware, security
│   │   ├── db/              Database engine, sessions, ORM base
│   │   ├── models/          SQLAlchemy models
│   │   ├── repositories/    Database access
│   │   ├── schemas/         Request/response models
│   │   ├── services/        Business rules: summaries, alerts, timeline, storage, email
│   │   └── worker.py        Extraction worker
│   ├── alembic/             Database migrations
│   ├── evaluation/          AI accuracy evaluation (fictional documents, scoring, report)
│   ├── tests/               Unit and integration tests
│   └── Dockerfile           API + worker image (includes Tesseract)
├── frontend/                React + Vite single-page app
│   └── src/                 Feature folders (documents, timeline, profile, medications, …), API client, styles
├── infra/                   Terraform for AWS (EC2 + Caddy, RDS, S3, ECR, SES, budget) and server setup
├── docs/                    End-to-end guide: implementation, testing, AI evaluation, deployment
├── docker/                  Database init scripts
├── docker-compose.yml       Local PostgreSQL
└── spec/                    Product, data model, backend, API, AI, frontend, and observability specifications
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- [uv](https://docs.astral.sh/uv/) — installs Python 3.12 for the backend automatically
- Node.js 20+ and npm
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) 5, for scanned copies (on Windows: `winget install --id UB-Mannheim.TesseractOCR`). Without it, scanned pages are read by the AI from their images.

## Setup and Run

### 1. Start the database

```bash
docker compose up -d
```

Creates `healthcare_dev` and `healthcare_test` databases on `localhost:5432`.

### 2. Backend

```bash
cd backend
cp .env.example .env        # local settings; never commit .env
uv sync                     # creates .venv with Python 3.12 and dependencies
uv run uvicorn app.main:app --reload --port 8000
```

- API base: `http://localhost:8000/api/v1`
- Interactive docs (development only): `http://localhost:8000/api/v1/docs`

> If another virtual environment is active in your shell, `uv` warns that `VIRTUAL_ENV` does not match. Run `deactivate` first (or ignore the warning — uv uses `backend/.venv`).

### 3. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173` and create an account. The **System Status** page shows whether the backend and database are reachable.

### 4. AI extraction worker (optional)

Extraction is **off by default**, because documents are sent to an external AI provider. Use only synthetic test documents.

1. Add your own Groq key to `backend/.env` (never commit it): `GROQ_API_KEY=...`
2. Set `EXTRACTION_ENABLED=true` in `backend/.env` and restart the backend.
3. In a separate terminal:

```bash
cd backend
uv run python -m app.worker          # keeps running; add --once to process the queue and exit
```

How the worker reads a document is shown in [How a Document Is Read](#how-a-document-is-read).

### Database migrations

```bash
cd backend
uv run alembic upgrade head
```

### Password-reset emails in development

With `EMAIL_BACKEND=file`, emails are written to `backend/.dev_mail/` (git-ignored) instead of being sent. Open the newest `.eml` file to find the reset link.

## Configuration

Backend settings come from environment variables (`backend/.env` in development). See `backend/.env.example`.

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `development`, `test`, or `production` | `development` |
| `DATABASE_URL` | PostgreSQL connection string (required) | — |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | — |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` (DEBUG refused in production) | `INFO` |
| `MAX_UPLOAD_MB` | Maximum document upload size | `20` |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | Token lifetimes | `15` / `7` |
| `JWT_SECRET` | Signing key for access tokens (required, 32+ characters) | — |
| `COOKIE_SECURE` | Refresh cookie sent over HTTPS only (must be `true` in production) | `true` |
| `FRONTEND_BASE_URL` | Used to build password-reset links | `http://localhost:5173` |
| `LOGIN_MAX_FAILURES` / `LOCKOUT_MINUTES` | Account lockout after repeated failed logins | `5` / `15` |
| `PASSWORD_RESET_MINUTES` | Reset-link lifetime | `30` |
| `EMAIL_BACKEND` / `DEV_MAIL_DIR` | `file` writes emails to a local folder in development; `ses` sends through Amazon SES; `disabled` sends nothing (password reset unavailable) | `file` / `.dev_mail` |
| `EMAIL_FROM` | Sender for `ses`, an address verified in SES (e.g. `Healthfolio <you@example.com>`) | — |
| `DOCUMENT_STORAGE_DIR` | Where uploaded documents are stored in development (git-ignored) | `storage/documents` |
| `STORAGE_BACKEND` / `S3_BUCKET` | `local` disk, or `s3` with a private, encrypted bucket | `local` / — |
| `UPLOAD_RATE_LIMIT_PER_HOUR` | Uploads allowed per user per hour | `30` |
| `SUMMARY_RATE_LIMIT_PER_HOUR` | AI summaries a user can request per hour | `20` |
| `EXTRACTION_ENABLED` | Turn on AI extraction (external provider; synthetic data only) | `false` |
| `GROQ_API_KEY` | Your Groq API key (secret; never committed) | — |
| `AI_MODEL` | Model used for extraction | `qwen/qwen3.8-27b` |
| `EXTRACTION_MAX_ATTEMPTS` | Retries for temporary AI failures | `3` |
| `TESSERACT_CMD` | Path to `tesseract` when it is not on `PATH` or in `C:\Program Files\Tesseract-OCR` | auto-detected |
| `OCR_MIN_CONFIDENCE` | Scanned pages read with less average OCR confidence go to the AI as images | `85` |

Frontend: `VITE_API_BASE_URL` (public; never put secrets in `VITE_` variables).

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health/live` | Liveness: the process is running |
| GET | `/api/v1/health/ready` | Readiness: the database is reachable (`503` if not) |
| POST | `/api/v1/auth/register` | Create an account and log in |
| POST | `/api/v1/auth/login` | Log in (returns an access token; sets an HttpOnly refresh cookie) |
| POST | `/api/v1/auth/refresh` | Renew the access token (rotates the refresh cookie) |
| POST | `/api/v1/auth/logout` | End the session |
| POST | `/api/v1/auth/password/forgot` | Email a password-reset link |
| POST | `/api/v1/auth/password/reset` | Set a new password with a reset token |
| GET | `/api/v1/users/me` | The logged-in user |
| POST | `/api/v1/documents` | Upload a PDF, JPEG, or PNG (multipart; optional type, date, provider) |
| GET | `/api/v1/documents` | List your documents (newest first, paginated; filter by type, report date range, hospital or clinic) |
| GET | `/api/v1/documents/providers` | Your hospital and clinic names, for the filter |
| GET | `/api/v1/timeline` | Your records in date order (filter by category and date) |
| GET | `/api/v1/alerts` | Your safety alerts |
| PATCH | `/api/v1/alerts/{id}` | Acknowledge or resolve an alert |
| GET | `/api/v1/profile` | Your health profile and suggestions |
| PATCH | `/api/v1/profile/values` | Update personal details |
| GET, POST | `/api/v1/vitals` | Your blood pressure and heart rate readings; add one |
| GET | `/api/v1/dashboard` | One-page overview for the dashboard |
| POST | `/api/v1/search` | Search your records (query in the body, never in the URL) |
| GET, POST | `/api/v1/summaries/history` | Read or write the AI summary of your whole history |
| GET, POST | `/api/v1/documents/{id}/summary` | Read or write the AI summary of one document |
| GET | `/api/v1/account/export/{pdf,json,csv,documents}` | Download your data |
| POST | `/api/v1/auth/password/change` | Change your password |
| POST | `/api/v1/auth/account/delete` | Delete your account and all its data |
| POST | `/api/v1/profile/suggestions/{id}` | Accept, correct, or reject a suggested diagnosis |
| GET | `/api/v1/documents/{id}` | Document details |
| GET | `/api/v1/documents/{id}/file` | The original file (inline, or `?download=true`) |
| PATCH | `/api/v1/documents/{id}` | Edit type, date, or provider |
| DELETE | `/api/v1/documents/{id}` | Delete the document, its file, and every record linked to it (results, medicines, conditions, follow-ups, alerts) |
| GET | `/api/v1/documents/{id}/observations` | Extraction status and extracted lab results |
| POST | `/api/v1/documents/{id}/extract` | Queue extraction (first time, or retry after a failure) |
| POST | `/api/v1/documents/{id}/follow-ups` | Add a prescription's follow-ups to Checkups and Follow-ups |
| GET | `/api/v1/follow-ups` | List follow-ups (overdue computed) |
| PATCH | `/api/v1/follow-ups/{id}` | Mark a follow-up done, cancelled, or scheduled again |
| DELETE | `/api/v1/follow-ups/{id}` | Delete a follow-up permanently |
| GET, POST | `/api/v1/medications` | List medicines; add one |
| PATCH, DELETE | `/api/v1/medications/{id}` | Edit or change status; remove (history kept) |
| GET | `/api/v1/medications/{id}/history` | A medicine's change history |

Full request/response details: `spec/api_contract_spec.md` Sections 5.1, 6.1, and 6.2.

### Security highlights

- Passwords hashed with Argon2id; refresh and reset tokens stored only as hashes.
- Short-lived access token kept in browser memory; refresh token in a `Secure`, `HttpOnly`, `SameSite=Strict` cookie, rotated on every use with theft detection.
- Generic login errors, account lockout, and per-IP rate limits.
- Audit events for security-relevant actions, without passwords, tokens, or medical content.
- AI extraction: the document is passed as data, never as instructions; output must match a strict schema and is re-validated by deterministic checks; uncertain values are flagged for review; logs record IDs, timings, and token counts only.
- Uploaded files are identified by their content (not their name), size-limited before the upload is read, stored under opaque IDs, and only reachable through the authenticated API. Every document query is scoped to its owner.

All errors use one format:

```json
{ "error": { "code": "NOT_FOUND", "message": "...", "details": [], "request_id": "..." } }
```

Every response carries an `X-Request-ID` header for troubleshooting.

## Testing

623 backend tests (unit and integration, with a fake AI client) and 166 frontend tests. GitHub Actions runs them, with lint and the build, on every push and pull request (`.github/workflows/ci.yml`).

```bash
# Backend (integration tests need the database running)
cd backend
uv run ruff check .
uv run pytest                    # all tests
uv run pytest -m "not integration"   # without the database
RUN_LIVE_AI=1 uv run pytest -m live # one real AI call on a synthetic report (costs a little)

# Frontend
cd frontend
npm run lint
npm run test
npm run build
```

### Accuracy evaluation

> [!IMPORTANT]
> **AI accuracy has not been rigorously validated.** The built-in evaluation uses fictional reports only; it is not clinical validation, and the target of 98% accuracy on critical fields is not met yet. Rigorous validation, on a de-identified real-document set with repeated runs, is planned for the future. Use synthetic documents only, and always check results against the original document.

Fictional reports with known answers are generated, saved as digital PDFs and as scans at three damage levels, read by the real pipeline, and scored (items found, field accuracy, invented items, review flags, OCR error rate, consistency). It calls the AI provider, so it is run on demand, not in the test suite.

Latest quick-set results (10 documents, 106 items):
- **0 misleading groupings.**
- **Dates:** 16/16 right, and 10/10 shown exactly as printed.
- **Fields right:** 91.1%.
- **Items found:** 99/106.

The 98% critical-field release gate is not met yet. Details and the comparison across versions: [docs/END_TO_END.md §6](docs/END_TO_END.md#6-ai-evaluation).

```bash
cd backend
uv run python -m evaluation generate        # 60 test documents (no AI calls)
uv run python -m evaluation run --quick     # 10 documents; omit --quick for all, add --repeat 3 for consistency
uv run python -m evaluation report          # HTML report
```

## Deployment

Healthfolio runs on AWS (region `ap-south-1`). The infrastructure is defined with Terraform in `infra/`:

- **Server:** one small EC2 server with a fixed IP. Caddy serves the website, handles HTTPS (free Let's Encrypt certificate, renewed automatically) and forwards `/api/*` to the app, so the site and API share one address. The address is `https://<ip>.sslip.io`, which needs no domain.
- **API and worker:** one Docker image (`backend/Dockerfile`, includes Tesseract), stored in Amazon ECR. Database migrations run on start.
- **Database:** Amazon RDS for PostgreSQL, private, reachable only from the server. Its password is kept in AWS Secrets Manager.
- **Files:** uploaded documents go to a private, encrypted S3 bucket (`STORAGE_BACKEND=s3`), accessed through the server's IAM role (no access keys). The built website is also kept in S3.

- **Email:** password-reset emails can be sent through Amazon SES (`email_backend = "ses"` in Terraform). It is **off for now** (`disabled`): the account is in the SES sandbox, which delivers only to verified addresses. The Forgot password page says that reset is unavailable.

- **CI/CD:** GitHub Actions. Every push and pull request runs the tests, lint, and build (`ci.yml`). A merge to `main` runs them again and, after approval of the `production` environment, builds and pushes the API image, restarts the API, publishes the website, and restarts the web server (`deploy.yml`). GitHub signs in to AWS with OIDC as a deploy-only role, so no AWS keys are stored in GitHub.

See `infra/README.md` for the deployment steps.

## Specifications

For the full walkthrough, from implementation through testing and AI evaluation to deployment, see **[docs/END_TO_END.md](docs/END_TO_END.md)**.

The system is defined by these specs: `goal_spec.md` (product scope), `backend_spec.md`, `api_contract_spec.md`, `data_model_spec.md`, `AI_spec.md`, `frontend_spec.md`, and `observability_and_reliability_spec.md`.

## Future Improvements

- **Rigorous validation of AI accuracy:** a de-identified real-document evaluation set, repeated runs to measure consistency, and meeting the 98% critical-field target before any real use.
- **More complete extraction:** read long documents page by page, then check which printed result lines no extracted item covers, and re-read only those lines. This takes longer per document but misses fewer results and fields.
- **Image understanding:** reading scan images (X-rays, ECG traces) directly, not only their written reports.
- **CloudFront in front of the server** once the AWS account is verified, so the server is no longer reachable from the internet directly.
- **Operations:** 30-day backups with a tested restore, and monitoring alarms for the site, API, and worker.
- Reminder delivery, Unicode fonts in the PDF export, trends across dates, and Health Q&A.

## License notes

PyMuPDF is licensed under AGPL-3.0: suitable for this open project; a closed-source commercial deployment would need its commercial licence or a permissive alternative (for example pypdf). Tesseract OCR is Apache-2.0.
