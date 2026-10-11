# Multimodal AI Healthcare Decision-Support System

A personal health-records platform that stores medical documents, extracts and organizes their information, tracks medications and follow-ups, and provides cautious, source-backed AI summaries. It offers informational decision support only and does not replace professional medical care.

> **Status:** user accounts and medical document storage are in place (upload, preview, download, edit details, delete). AI extraction and the other health-record features are being built step by step against the specifications below.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 16 (Docker Compose for local development) |
| Frontend | React, Vite, TypeScript, React Router |
| Testing | pytest (backend), Vitest + Testing Library (frontend) |
| Tooling | uv (Python), npm, ruff, oxlint |

## Project Structure

```
├── backend/                 FastAPI application
│   ├── app/
│   │   ├── api/v1/          Versioned API routes (/api/v1)
│   │   ├── core/            Config, logging, errors, middleware, security
│   │   ├── db/              Database engine, sessions, ORM base
│   │   ├── models/          SQLAlchemy models
│   │   ├── repositories/    Database access
│   │   ├── schemas/         Request/response models
│   │   └── services/        Business logic (auth, email)
│   ├── alembic/             Database migrations
│   └── tests/               Unit and integration tests
├── frontend/                React + Vite single-page app
│   └── src/
│       ├── api/             Central API client
│       ├── auth/            Session state, route protection
│       ├── components/      App shell and shared components
│       ├── pages/           Page components
│       └── styles/          Design tokens
├── docker/                  Database init scripts
├── docker-compose.yml       Local PostgreSQL
└── *_spec.md                Product, backend, API, AI, frontend, and observability specifications
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- [uv](https://docs.astral.sh/uv/) — installs Python 3.12 for the backend automatically
- Node.js 20+ and npm

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
| `EMAIL_BACKEND` / `DEV_MAIL_DIR` | `file` writes emails to a local folder in development | `file` / `.dev_mail` |
| `DOCUMENT_STORAGE_DIR` | Where uploaded documents are stored in development (git-ignored) | `storage/documents` |
| `UPLOAD_RATE_LIMIT_PER_HOUR` | Uploads allowed per user per hour | `30` |

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
| GET | `/api/v1/documents` | List your documents (newest first, paginated, filter by type) |
| GET | `/api/v1/documents/{id}` | Document details |
| GET | `/api/v1/documents/{id}/file` | The original file (inline, or `?download=true`) |
| PATCH | `/api/v1/documents/{id}` | Edit type, date, or provider |
| DELETE | `/api/v1/documents/{id}` | Delete the document and its file |

Full request/response details: `api_contract_spec.md` Sections 5.1 and 6.1.

### Security highlights

- Passwords hashed with Argon2id; refresh and reset tokens stored only as hashes.
- Short-lived access token kept in browser memory; refresh token in a `Secure`, `HttpOnly`, `SameSite=Strict` cookie, rotated on every use with theft detection.
- Generic login errors, account lockout, and per-IP rate limits.
- Audit events for security-relevant actions, without passwords, tokens, or medical content.
- Uploaded files are identified by their content (not their name), size-limited before the upload is read, stored under opaque IDs, and only reachable through the authenticated API. Every document query is scoped to its owner.

All errors use one format:

```json
{ "error": { "code": "NOT_FOUND", "message": "...", "details": [], "request_id": "..." } }
```

Every response carries an `X-Request-ID` header for troubleshooting.

## Testing

```bash
# Backend (integration tests need the database running)
cd backend
uv run ruff check .
uv run pytest                    # all tests
uv run pytest -m "not integration"   # without the database

# Frontend
cd frontend
npm run lint
npm run test
npm run build
```

## Specifications

The system is defined by these specs: `goal_spec.md` (product scope), `backend_spec.md`, `api_contract_spec.md`, `data_model_spec.md`, `DL_AI_spec.md`, `frontend_spec.md`, and `observability_and_reliability_spec.md`.

## Future Improvements

AI extraction from documents, medication and follow-up tracking, safety alerts, AI summaries, search, and export — delivered incrementally as their data model and API contracts are defined.
