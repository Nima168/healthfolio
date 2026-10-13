# API Contract Specification
## Multimodal AI Healthcare Decision-Support System

## 1. Purpose and Ownership

This document defines the REST API contract between the frontend and backend: endpoint conventions, request and response formats, status codes, authentication requirements, error format, document-processing workflows, and versioning.

It is the source of truth for API endpoint definitions, request/response schemas, HTTP status codes, and API-level error formats. Other specifications own their own areas:

- Product goals and scope: `goal_spec.md`
- User interface and interactions: `frontend_spec.md`
- Backend implementation, data management, and security controls: `backend_spec.md`
- Entities and relationships: `data_model_spec.md`
- AI behavior and evaluation: `DL_AI_spec.md`
- Logging, monitoring, and reliability: `observability_and_reliability_spec.md`

When a requirement spans several areas, the owning specification defines the rule and the others reference it.

## 2. API Design Principles

- RESTful HTTP APIs, with JSON for standard request and response bodies.
- Consistent naming, validation, pagination, and error conventions.
- Incoming requests and outgoing responses are validated.
- API contracts stay independent of internal database models.
- Internal filesystem paths, database details, credentials, stack traces, and other implementation details are never exposed.
- Extensions must not unnecessarily break existing API consumers.
- Transport security follows `backend_spec.md` Section 8.3.

## 3. Base URL and Versioning

- Base path: `/api/v1`.
- The full base URL depends on the environment (local development, testing, deployment) and is provided through frontend configuration.
- Breaking changes use an explicitly versioned API path and are documented with migration requirements (Section 12).
- Backward-compatible additions must not change the meaning of existing fields or responses.

## 4. Request and Response Conventions

### 4.1 Request Format

- JSON for requests that create or update structured resources.
- `multipart/form-data` for medical document uploads.
- Query parameters for filtering, pagination, and sorting.
- Required fields, data types, allowed values, and field lengths are validated.
- Malformed or unsupported requests are rejected with the standard error response (Section 8).

### 4.2 Success Responses

Each endpoint uses an appropriate status code and a documented response schema. A single-resource response may return the resource directly. Collection endpoints use the pagination structure in Section 9.

### 4.3 HTTP Status Codes

- `200 OK` — request completed successfully.
- `201 Created` — resource created.
- `202 Accepted` — request accepted for processing that has not completed.
- `204 No Content` — success without a response body.
- `400 Bad Request` — general request error.
- `401 Unauthorized` — authentication missing or invalid.
- `403 Forbidden` — authenticated user lacks permission for an operation on their own accessible resources.
- `404 Not Found` — resource does not exist, or belongs to another user and must not be disclosed.
- `409 Conflict` — request conflicts with current resource state.
- `413 Content Too Large` — uploaded file exceeds the configured size limit.
- `415 Unsupported Media Type` — unsupported content type.
- `422 Unprocessable Content` — request validation failed.
- `429 Too Many Requests` — rate limit exceeded.
- `500 Internal Server Error` — unexpected server failure.
- `503 Service Unavailable` — service or required dependency temporarily unavailable.

Requests for another user's private resources return `404`, not `403`, so existence is not revealed (Section 8). Each endpoint must document the status codes it can return.

## 5. Authentication and Authorization

### 5.1 Authentication Mechanism

JWT-based authentication is used for protected API access.

**Token transport (decided):**

- **Access token:** short-lived JWT returned in the login/refresh response body, held by the frontend in memory only (not `localStorage`/`sessionStorage`), and sent as `Authorization: Bearer <access_token>`.
- **Refresh token:** set by the backend in a `Secure`, `HttpOnly`, `SameSite=Strict` cookie scoped to the refresh endpoint. It is never readable by frontend code.
- Because the refresh cookie is sent automatically, the refresh endpoint must also be protected against cross-site request forgery (CSRF).
- **Lifetimes (decided):** access token 15 minutes; refresh token 7 days. Refresh tokens are rotated on every use, and the previous one is revoked. Values are configurable per environment.

The authentication flow must define:

- Email-and-password registration and login.
- Access-token issuance, validation, and expiry.
- Refresh and revocation behavior.
- Logout, including invalidation of the refresh token and clearing its cookie.
- Password recovery and reset via email (email delivery is owned by `backend_spec.md`).
- Password hashing and credential protection.

#### 5.1.1 Authentication Endpoints

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| POST | `/auth/register` | `{email, password, display_name?}` | `201` token response + refresh cookie | `409 EMAIL_ALREADY_REGISTERED`, `422`, `429` |
| POST | `/auth/login` | `{email, password}` | `200` token response + refresh cookie | `401 INVALID_CREDENTIALS`, `422`, `429` |
| POST | `/auth/refresh` | refresh cookie + `X-CSRF-Protection: 1` | `200` token response + rotated cookie | `401 UNAUTHENTICATED`, `403 CSRF_CHECK_FAILED`, `429` |
| POST | `/auth/logout` | refresh cookie + `X-CSRF-Protection: 1` | `204`, cookie cleared | `403 CSRF_CHECK_FAILED` |
| POST | `/auth/password/forgot` | `{email}` | `202` (always) | `422`, `429` |
| POST | `/auth/password/reset` | `{token, new_password}` | `204` | `400 INVALID_OR_EXPIRED_TOKEN`, `422`, `429` |
| GET | `/users/me` | Bearer access token | `200` user | `401 UNAUTHENTICATED` |

Registration logs the user in immediately; there is no email-verification step.

**Token response:**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900,
  "user": { "id": "<uuid>", "email": "user@example.com", "display_name": "Asha", "created_at": "2026-10-11T08:00:00Z" }
}
```

**Refresh cookie:** name `refresh_token`; attributes `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=` refresh lifetime.

#### 5.1.2 Rules

- **Passwords:** 12–128 characters and not equal to the email. No character-composition rules. Hashed with Argon2id.
- **Generic login failure:** wrong password, unknown email, and a locked account all return the same `401 INVALID_CREDENTIALS` message, so the response does not reveal whether an account exists.
- **Lockout:** after 5 consecutive failed logins the account is locked for 15 minutes; a successful login or password reset clears the counter.
- **Rate limits** (per client IP, `429 RATE_LIMITED`): login 10/minute, register 5/minute, forgot-password 5/hour, reset 10/hour, refresh 30/minute.
- **Registration and enumeration:** because there is no email verification, `register` returns `409` for an existing email. This is an accepted trade-off, mitigated by rate limits; login and forgot-password reveal nothing.
- **CSRF:** cookie-authenticated endpoints (`refresh`, `logout`) require the `X-CSRF-Protection: 1` header and, when an `Origin` header is present, an origin from the allowed CORS list.
- **Refresh rotation:** each refresh issues a new refresh token and revokes the old one. Presenting an already-revoked token revokes every token from that login (token family) and returns `401`.
- **Password reset:** `forgot` always returns `202` with the same body. If the account exists, an email is sent with a single-use link `{FRONTEND_BASE_URL}/reset-password#token=<token>`, valid for 30 minutes. The token is in the URL fragment so it is never sent to servers or logged. A successful reset revokes all of the user's refresh tokens.

Data structures for these endpoints are defined in `data_model_spec.md` Section 4.

### 5.2 Protected Requests

Protected requests use (see Section 5.1):

`Authorization: Bearer <access_token>`

The backend validates the token and identifies the authenticated user before allowing access.

### 5.3 Authorization Rules

User-level data isolation follows `backend_spec.md` Section 8.2. API-specific rules:

- The authenticated identity is derived from validated credentials, never from a user ID supplied by the client.
- Ownership and permissions are checked for every resource operation, including reads, updates, downloads, and deletions, to prevent insecure direct object references.
- Pagination and filtering must not bypass authorization or isolation.
- Caregiver or clinician access is not enabled. Any future sharing feature requires explicit authorization and scoped permissions.

## 6. API Resource Domains and Endpoints

The API may expose these resource domains, within the scope defined in `goal_spec.md`:

1. Authentication and user profile, including profile suggestions (list, accept, correct, reject).
2. Medical documents and document-processing status.
3. Extracted medical information and source references.
4. Health history and user-maintained records.
5. Medication and prescription tracking (create, edit, view, history).
6. Appointments, checkups, and follow-ups (including upcoming/overdue status and confirmation of document-derived suggestions).
7. AI summaries, results, and processing status.
8. Safety alerts, including acknowledgement and resolution.
9. User data export (PDF health summary, CSV/JSON data, original-document download) and deletion.
10. Record search across documents and extracted information (Section 9.1).

These are domains, not one endpoint each. Medication-taking reminders and prescription-renewal reminders are out of scope; medication tracking does not imply reminders. Automated reminder delivery and Health Q&A are deferred (`goal_spec.md` Section 6), so no endpoints are defined for them.

Detailed endpoint definitions: not yet defined. Endpoints are added only after the relevant functionality and data ownership are defined in the other specifications, and each must trace to an approved requirement (Section 12).

### 6.1 Medical Document APIs

Supported types initially: PDF, JPEG, and PNG.

Maximum file size (decided): 20 MB per document, configurable per environment. Larger files return `413`.

#### 6.1.1 Document Endpoints

All require a Bearer access token. Another user's document returns `404` on every endpoint.

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| POST | `/documents` | `multipart/form-data`: `file` and `title` (both required); optional `category`, `document_date` (`YYYY-MM-DD`), `document_date_precision`, `provider_name` | `201` document | `409 DUPLICATE_DOCUMENT`, `413`, `415`, `422`, `429` |
| GET | `/documents` | Query: `limit` (1–50, default 20), `cursor`, optional `category`, `date_from` and `date_to` (`YYYY-MM-DD`, on the report's own date; undated documents are left out when either is set), `provider` (matched ignoring case and extra spaces, never by similar spelling), `provider_missing=true` (documents with no hospital or clinic). Filters combine. | `200` page of documents, newest first | `422` (also when `date_to` is before `date_from`) |
| GET | `/documents/providers` | — | `200` `{ items: [{name, document_count}], without_provider }`: the user's hospital and clinic names (case and spacing variants counted together, shown with the most used spelling), A to Z | — |
| GET | `/documents/{id}` | — | `200` document | `404` |
| GET | `/documents/{id}/file` | Query: `download=true` for a download, otherwise inline | `200` original bytes | `404` |
| PATCH | `/documents/{id}` | JSON with any of `title`, `category`, `document_date`, `document_date_precision`, `provider_name` (`null` clears a field, except `title`) | `200` document | `404`, `422` |
| DELETE | `/documents/{id}` | — | `204` | `404` |

**Document response:**

```json
{
  "id": "<uuid>",
  "title": "Blood test – March 2026",
  "original_filename": "blood-test-2026-03.pdf",
  "media_type": "application/pdf",
  "size_bytes": 182344,
  "category": "lab_report",
  "document_date": "2026-03-14",
  "document_date_precision": "day",
  "provider_name": "City Diagnostics",
  "processing_status": "pending",
  "created_at": "2026-10-11T09:00:00Z",
  "updated_at": "2026-10-11T09:00:00Z"
}
```

- `title`: the user's name for the document. Required, trimmed, 1–200 characters. A missing or blank title returns `422` with `{"field": "title", "issue": "Enter a name for this document."}`. It can be changed but not removed.
- `original_filename`: the sanitised name of the uploaded file, kept for downloads.
- `category`: `lab_report`, `prescription`, `discharge_summary`, `consultation_note`, `imaging_report`, `other`, `unknown` (default `unknown`).
- `document_date_precision`: `day`, `month`, `year`, `unknown`. For `month`/`year`, the date is stored as the first day of the period.
- `processing_status` uses the job lifecycle (Section 7). New uploads are `pending` until extraction is introduced.
- The list response follows Section 9: `{ "items": [...], "pagination": { "limit": 20, "next_cursor": "<opaque>" | null } }`.

#### 6.1.2 Rules

- **Type check:** the file type is detected from its content (magic bytes), never from the file name or the browser's declared type. Content that is not PDF, JPEG, or PNG returns `415 UNSUPPORTED_MEDIA_TYPE`. Empty files return `422`.
- **Size:** requests above the limit are rejected with `413` before the body is read.
- **Readable quality** (decision 2026-10-13, `backend/app/services/upload_quality.py`): photos and PDF pages without a text layer (scans; first 10 such pages) are measured before saving. Too small (shorter side under 600 px), too dark, blank or washed out, or blurry (edge detail below a limit set against the sample reports) returns `422` with `{"field": "file", "issue": "<which page and what to do>"}`, asking for a clearer copy. Typed text is not measured. Files that cannot be opened are accepted and reported by reading.
- **Discharge summaries are one page** (decision 2026-10-13, AI reading limits): an upload typed `discharge_summary` with more than one page returns `422` (`field: file`). A document classified as a discharge summary, or retyped as one, with more than one page fails reading with `discharge_too_many_pages`.
- **Missing values:** nothing is assumed. A value a report does not state is stored as empty, and the app shows it as "Not mentioned".
- **Duplicates:** the same file content (SHA-256) already uploaded by the same user and not deleted returns `409 DUPLICATE_DOCUMENT`. The error details include `{"field": "existing_document_id", "issue": "<uuid>"}` so the client can link to it. Other users' files are never compared.
- **File name:** stored only as a sanitised display name (base name, no control characters, at most 255 characters).
- **Download headers:** the original `Content-Type`, `Content-Disposition` (`inline` or `attachment` with the sanitised name), `X-Content-Type-Options: nosniff`, and `Cache-Control: private, no-store`.
- **Deletion:** removes the stored file immediately. The record remains only as a tombstone (no title, file name, provider, date, or hash) for audit integrity and is excluded from all responses. Backup copies expire per `observability_and_reliability_spec.md` Section 8.2. Its extracted results are deleted with it, and any queued extraction is cancelled.
- **Rate limit:** uploads are limited per user (`UPLOAD_RATE_LIMIT_PER_HOUR`, default 30).
- **Extraction:** every upload queues an extraction job automatically (Section 6.2).

### 6.2 Extracted Results and Review

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/documents/{id}/observations` | — | `200` extraction state | `404` |
| POST | `/documents/{id}/extract` | — | `202` extraction state | `404`, `409 EXTRACTION_IN_PROGRESS` |

**Extraction state:** `{ "extraction_enabled": bool, "job": {status, attempts, error_category, updated_at} | null, "items": [observation, ...], "summary": lab summary | null }`. `job` is null for documents uploaded before extraction existed; `POST /extract` queues one. `POST /extract` is also how a failed or cancelled extraction is retried, and how a completed one is read again ("Read again", decision 2026-10-12: AI reading varies between runs). It is refused only while a job is pending/running. A new reading replaces the previous one: its rows are withdrawn (soft-deleted; follow-up suggestions not yet added are superseded) and only the latest reading is shown; follow-ups already added are kept and are never added twice.

**Observation:** `id, name, value_text, value_numeric, unit, reference_range_text, reference_low, reference_high, observed_at, observed_at_precision, page, source_snippet, confidence, needs_review, validation_findings, notes`. Numbers are exact decimal strings (e.g. `"13.8"`), never floats. `value_text` is always the value as written; `value_numeric` is set only when it contains exactly one number.

**Result rules:**

- Extracted lab results are shown as read, with no confirm/correct/reject step (decision 2026-10-11); uncertain values are still flagged.
- `needs_review` is true when confidence is not `high` or a validation finding needs attention.

**Lab summary** (decision 2026-10-11; present once extraction has completed): `{ report_date, above[], below[], normal[], invalid[] }`. Value lines are `{name, value_text, unit, reference_range_text}`; invalid lines add `reason`. `report_date` is the date exactly as printed (null when not printed, or for extractions made before it was captured). Rules (backend code, never the AI; `backend/app/services/lab_summary.py`):

1. Only the reference range printed next to each test is used; never outside or assumed ranges.
2. Values, units, and ranges are copied exactly as extracted; nothing is rounded.
3. No range, a value that is not a single number (e.g. `<150`, `Positive`), a range that cannot be read (e.g. split by sex), or an unclear value/unit/range (low or medium confidence, missing unit, possible misread) goes to `invalid` (shown as "Invalid Records") instead of being judged.
4. `< X`, `<= X`, `> X`, `>= X` are applied exactly as written; `a - b` includes both ends.
5. No diagnosis, causes, or advice.

The client shows it as plain text: `Report Date`, `Values Above Range`, `Values Below Range`, `Normal Values` (each `None` when empty), then `Invalid Records` only when there are any. Invalid records are shown as written (value, unit, range), never judged. No closing line (removed 2026-10-11).
- `error_category` values are safe codes (e.g. `ai_unavailable`, `ai_refused`, `image_too_large`, `unreadable_pdf`); clients map them to plain-language messages.

Rules:

- The original document stays distinguishable from OCR output, extracted facts, user corrections, and AI interpretations.
- Uploaded files are never publicly accessible; access is authorized independently of whether a user knows a document identifier.
- The API never exposes storage paths or requires the frontend to know whether a file is in local or object storage.

### 6.3 Prescriptions and Follow-ups

Decision 2026-10-11. Which reading a document gets: the upload's `category` (`lab_report` or `prescription`); for any other category the AI first classifies the document (`lab_report`, `prescription`, `other`). `GET /documents/{id}/observations` returns `document_kind` and, for prescriptions, `prescription`:

`{ prescribed_on, date_text, prescriber_name, medications[], follow_ups[], reminders }`. Medication lines are `{name, strength, instructions, duration_text, unclear, reason}` copied as written; follow-up lines are `{due_date, description, unclear, reason}`, clear same-day items joined by " + ", in date order with undated (unclear) items last; `reminders` is `available`, `added`, or `none`.

Rules (deterministic code, never the AI; `backend/app/ai/prescription_validation.py`, `backend/app/services/prescription_summary.py`):

1. The AI copies what is written and never calculates dates. A relative timing ("after 4 weeks", "in 3 months") is turned into a date by code from the printed prescription date (calendar months; a day past the month's end moves to its last day).
2. Flagged `unclear` (shown inline as "(unclear – check original)", the reason on hover) instead of guessing: low or medium confidence, missing instructions, a medicine listed twice, no timing, an unreadable date, a relative timing with no prescription date, a date before the prescription, or a timing beyond two years.
3. Medicines are never marked as currently taken (`status = unknown`).

The client shows it as plain text: `PRESCRIPTION SUMMARY — 07-Oct-2026 (Dr. Name)`, `Medications`, `Upcoming Follow-Ups` (past dates marked), and an "Add to Checkups and Follow-ups" button. Medicine names with strength and follow-up dates are bold. No Needs Review section (removed 2026-10-11).

| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| POST | `/documents/{id}/follow-ups` | — | `201` extraction state (`reminders: "added"`) | `404`, `409 NOTHING_TO_ADD` |
| GET | `/follow-ups` | — | `200 {items: [follow-up]}`; scheduled first by due date | — |
| PATCH | `/follow-ups/{id}` | `{"status": "scheduled" \| "completed" \| "cancelled"}` | `200` follow-up | `404`, `422` |

**Follow-up:** `id, title, kind (investigation | appointment | checkup), due_date, status, overdue (computed), completed_at, source_document_id, source_document_title`. "Add as reminders" adds only clear, dated follow-ups, once each. No reminder is sent yet (delivery is deferred). Deleting the document keeps follow-ups already added and withdraws ones not yet added.

### 6.4 Discharge Summaries

Decision 2026-10-12. Documents with category `discharge_summary` (or classified as one) get `discharge`:

`{ facility_name, admitted_on, admitted_text, discharged_on, discharged_text, stay_days, diagnoses[], key_results[], medications[], follow_ups[], reminders, warning_signs[] }`. Key-result lines are `{name, first_value, last_value, unit, reference_range_text, flag (high | low | null), still, last_tested, unclear}`; medications and follow-ups as in Section 6.3.

Rules (deterministic code; the AI only copies what is written; `backend/app/ai/discharge_validation.py`, `backend/app/services/discharge_summary.py`):

1. Diagnoses and warning signs exactly as written; never reworded.
2. `stay_days` counts calendar days with both the admission and the discharge day.
3. Results: one value per test per date; dates written without a year take the admission year (the next year past December). A value is numeric only if it is a plain number.
4. Key results: a test is listed when its last value is outside the reference range printed in the document (Section 6.2 range rules), or when its result is text. `still` = the first value was outside on the same side. `last_tested` = the last test was before the discharge date. No "slightly": the document gives no threshold.
5. Medicines: discharge medications only, not treatment given in hospital. Follow-ups written as relative timings count from the discharge date.

The client shows it as plain text: `DISCHARGE SUMMARY — <hospital>`, `Admitted … → Discharged … (N days)`, `Diagnosis`, `Key Results`, `Discharge Medications`, `Upcoming Follow-Ups` with "Add to Checkups and Follow-ups", `Return to Emergency If`.

### 6.5 Consultation Notes, Imaging Reports, and Other Test Reports

Decision 2026-10-12. Upload types `consultation_note` and `imaging_report` decide the reading directly; `other` and "not set" are classified first (`lab_report`, `prescription`, `discharge_summary`, `consultation_note`, `imaging_report`, `test_report`, or `other` = nothing extracted). `GET /documents/{id}/observations` returns, by kind:

- `consultation`: `{ visit_date, visit_text, clinician_name, symptoms[], observations[], assessment[], plan[], follow_ups[], reminders }`.
- `imaging`: `{ is_written_report, exam_name, report_id, facility_name, exam_date, exam_text, report_date, report_text, body_region, findings[], impression[], uncertainty[] }`.
- `test_report` (e.g. ECG): `{ test_type, test_name, report_id, facility_name, report_form, test_date, test_text, measurements[{name, value_text, unit, reference_range_text, flag, unclear}], interpretations[{source, confirmed, text}], visual_content[] }`.

Rules (deterministic code; the AI only copies; `backend/app/ai/report_validation.py`, `backend/app/services/report_summaries.py`):

1. All text exactly as written (line breaks from the page layout joined); nothing reworded.
2. Follow-ups (consultation): a deadline ("Tests by 10-Nov-2026: A, B") is one dated follow-up per test; an approximate timing ("mid-January 2027") is shown as written with "(no exact date)" and is never added to Checkups and Follow-ups; relative timings count from the consultation date.
3. Imaging: only the written report is read; scan images are never interpreted (planned later). Scan images without a report give `is_written_report: false`. Uncertainty lists only statements written in the report.
4. Test reports: a measurement is flagged high/low only against its printed range (Section 6.2 range rules) and only when the value is a plain number; "no range given" otherwise. Interpretations are kept apart by source (machine first, then physician); `confirmed` only when the report says so. Charts and tracings are listed as "not extracted (image only)".

The client shows them as plain text: `CONSULTATION SUMMARY — date (doctor)` with Symptoms, Observations, Assessment, Plan, Follow-Up; `IMAGING SUMMARY — exam` with Source, Examination Date (reported …), Body Region, Findings, Impression, Uncertainty; `<TYPE> SUMMARY — test` with Source, Date, Reported Measurements, Interpretation, Visual Content.

### 6.6 Medication Records

Decision 2026-10-12. The user's medicine list: read from prescriptions and discharge summaries, or added by the user (`backend/app/services/medication_service.py`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/medications` | The user's medicines: taking (`active`), not confirmed (`unknown`), then `stopped` |
| POST | `/api/v1/medications` | Add a medicine (`origin = user_entered`; status defaults to `active`) |
| PATCH | `/api/v1/medications/{id}` | Change details or status; only the fields sent change (`null` clears an optional one) |
| DELETE | `/api/v1/medications/{id}` | Remove from the list (soft delete; the row and its history are kept) |
| GET | `/api/v1/medications/{id}/history` | Change history, newest first: `{change, changed_at, changes {field: [before, after]}, snapshot}` |

A medicine is `{ id, name, strength, dosage_text, duration_text, prescriber_name, start_date, end_date, notes, status, kind (prescription, over_the_counter, supplement), origin, status_confirmed, edited, review_reason, source_document_id, source_document_title, source_document_date, source_document_deleted, updated_at }`.

Rules:

1. A document never sets a medicine as being taken: medicines read from documents are `unknown` until the user marks them `active` or `stopped` (`status_confirmed`).
2. Every change writes a history entry (`added`, `edited`, `status_changed`, `removed`) with the values before it. A change that alters nothing writes none. Editing details clears `review_reason`.
3. Medicines the user changed stay theirs: "Read again" and deleting the source document withdraw only medicines the user has not changed. A new reading re-links a kept medicine with the same name and strength instead of adding it twice.
4. Medicines are never merged across documents. No medication-taking or renewal reminders (out of scope).
5. Validation: name required (max 200 characters); the end date cannot be before the start date; unknown fields are rejected (422). Other users' medicines return 404.

### 6.7 Health Timeline

Decision 2026-10-12 (`backend/app/services/timeline_service.py`). `GET /api/v1/timeline` returns the user's records in date order, built from the existing records on each request (nothing new is stored).

Query: `category` (repeatable: `lab_results`, `imaging`, `test_reports`, `consultations`, `hospital_stays`, `prescriptions`, `medications`, `follow_ups`, `vitals`, `documents`), `date_from`, `date_to` (undated entries are left out when either is set; `422` when `date_to` is before `date_from`), `limit` (1–100, default 50), `cursor`.

Response: `{ items: [{ id, date, date_precision, category, title, lines[], trust, tag, source_document_id, source_document_title, link }], next_cursor }`. `trust` is `from_document` (read by AI, not checked by the user), `confirmed_by_you`, `edited_by_you`, or `added_by_you`.

Rules:

1. Newest first; entries without a date last (a missing date is never guessed).
2. Records from different dates are never merged: lab results are one entry per report and test date, with results outside the printed range listed first. No comparison or trends across dates (deferred).
3. Entries: lab results; imaging, test reports, consultations, and hospital stays (diagnoses as written) by their own date; prescriptions on the prescription date, listing their medicines and the user's confirmation; medicines with a start or end date, and medicines the user added; follow-ups by due date with status (Upcoming, Overdue, Done, Cancelled); documents not read (or not readable) as plain documents.
4. Only the user's own records from documents that are not deleted. Free-text search is not built yet (`search_vector` pending).

### 6.8 Safety Alerts

Decision 2026-10-12 (`backend/app/services/alert_service.py`, migration 0011). Rules decide, deterministically; no AI is used.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/alerts` | The user's alerts: open, then acknowledged, then resolved (the rules are applied to current records first) |
| PATCH | `/api/v1/alerts/{id}` | `{status: "acknowledged" \| "resolved", note?}`; `409 INVALID_TRANSITION` for anything else (open → acknowledged → resolved, or open → resolved; resolved is final for the user) |

An alert is `{ id, rule_code, rule_version, rule_description, severity, status, title, reason, uncertainty, next_steps, explanation_text, source_document_id, source_document_title, report_type (as read, else the upload type), report_date (the result's own date, else the report's), created_at, acknowledged_at, resolved_at, resolved_by, resolution_note, history[{event, actor, note, occurred_at}] }`.

Rule `RESULT_OUTSIDE_REPORT_RANGE` v1 (severity `warning`, "for review"): a plain-number result outside the reference range printed on the same report (Section 6.2 range rules). Inputs: lab results, discharge-summary results (each test's last value only), and test-report measurements. No alert for results without a printed range, non-numeric values, unreadable ranges, or unclear readings. No clinical thresholds, other reports' ranges, or trends are used. Urgent (critical-value) rules are not defined yet: they need clinical thresholds reviewed against validated sources.

Lifecycle: alerts are evaluated when a reading completes, when a document is deleted, and when alerts are listed. An alert is keyed by its result's content (document, test, value, date), so reading a document again keeps the same alert and the user's acknowledgement. When the result disappears, the system resolves it (`resolved_by: system`); if it returns, the system reopens it. Alerts the user resolved stay resolved. Every change is recorded in `alert_events`. Rules change only through migrations.

### 6.9 Health Profile

Decision 2026-10-12 (`backend/app/services/profile_service.py`, migration 0012).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/profile` | `{ values: {date_of_birth, sex, blood_group, height, weight} (each {value, unit, updated_at} or null), bmi, bmi_category, allergies[{name, category, reaction}], conditions[], suggestions[], surgeries[], hospitalizations[], document_stays[], family_history[], active_medications[] }` |
| PATCH | `/api/v1/profile/values` | Set, change, or clear (empty string) personal values; all sent fields are validated first, so one mistake saves nothing (`422` with field details) |
| GET | `/api/v1/profile/history` | Changes to personal values and allergies, newest first: `{field, change (added, changed, removed), previous_value, new_value, changed_at}` |
| POST, DELETE | `/api/v1/profile/allergies`, `/allergies/{id}` | Add (`409` when already recorded) or remove an allergy |
| POST, PATCH, DELETE | `/api/v1/profile/conditions`, `/conditions/{id}` | The user's conditions: name and status (`active`, `resolved`, `unknown`) |
| POST, DELETE | `/api/v1/profile/records`, `/records/{id}` | `{kind: surgery \| hospitalization \| family, name, occurred_on?, relation?, notes?}`: past surgeries, hospitalizations, family medical history |
| POST | `/api/v1/profile/suggestions/{id}` | `{action: accept \| correct \| reject, name?, status?}` for a diagnosis suggested from a document |

Rules:

1. Validation: date of birth `YYYY-MM-DD`, not in the future, after 1900; sex `female`, `male`, `other`, `prefer_not_to_say`; blood group A+/A-/B+/B-/AB+/AB-/O+/O-; height 30–272 cm; weight 1–500 kg. Each change is kept in `profile_value_history`; an unchanged value writes none.
2. Diagnoses read from documents (discharge summaries) are suggestions shown apart from the profile. They change nothing until the user accepts (as written) or corrects (with a new name) them; accepting creates a profile condition (`origin: suggestion_accepted`, status `unknown` unless chosen) linked to its document. Nothing is replaced silently: a suggestion that matches a condition already in the profile is not shown, and accepting one that matches links to the existing condition.
3. Reviewed suggestions stay reviewed: a rejected diagnosis is not suggested again after "Read again"; accepted conditions stay when the document is read again or deleted.
4. Allergies are entered by the user only (none are extracted from documents yet), with a type (`drug`, `food`, `environmental`, `other`) and an optional reaction. Other users' data returns 404.
5. BMI (2026-10-13) is calculated from the saved height and weight (kg/m², one decimal). `bmi_category` uses the adult categories on that value: underweight below 18.5; healthy 18.5–24.9; overweight 25.0–29.9; obesity class 1 30.0–34.9, class 2 35.0–39.9, class 3 40.0 or greater. It is null when the date of birth shows an age under 18. Blood pressure and heart rate are not profile values, because they change over time (removed 2026-10-13; the database still accepts the field names from migration 0013, unused).
6. Medical history: conditions, past surgeries and hospitalizations (dates optional, not in the future); `document_stays` lists hospital stays read from discharge summaries (as written, not editable here). Family history needs a relative (Mother, Father, Sister, Brother, Grandmother, Grandfather, Aunt, Uncle, Child, Other) and has no date.
7. Active medications are the medicines marked as taking (`status: active`) on the Medications page; a document never makes a medicine active. Medicines have a `kind`: `prescription` (default, and all medicines from documents), `over_the_counter`, or `supplement`.

### 6.10 Vital Sign Readings

Decision 2026-10-13 (`backend/app/services/vitals_service.py`, migration 0014). Blood pressure and heart rate change over time, so they are dated readings, not profile values.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/vitals` | The user's readings, newest first: `{id, measured_on, measured_time, systolic, diastolic, heart_rate, context}` |
| POST | `/api/v1/vitals` | Add a reading: `measured_on` (required, not in the future), optional `measured_time`, a blood pressure (both numbers) and/or a heart rate, optional `context` (e.g. "morning, at home") |
| DELETE | `/api/v1/vitals/{id}` | Remove a reading |

Rules: systolic 50–260 and diastolic 30–160 mmHg with systolic higher; heart rate 20–250 bpm (outside these is treated as a typing mistake, `422` with the field). Readings are shown as recorded: never labelled high or low, not compared or trended. `GET /profile` adds `latest_blood_pressure` and `latest_heart_rate` (`{value, unit, measured_on, measured_time}` or null), each from the latest reading that has it. Each reading is one Timeline entry (category `vitals`). Values printed in documents are not read into readings yet.

### 6.11 Dashboard

Decision 2026-10-13 (`backend/app/services/dashboard_service.py`). `GET /api/v1/dashboard` returns one overview built from the user's existing records; nothing new is calculated or stored.

Contents: document count, documents being read, the 5 most recent documents with their reading status; overdue follow-ups and those due within 30 days (5 each); open, acknowledged, and urgent alert counts with up to 3 open alerts (urgent first; the alert rules are applied first, as on the Alerts page); items to review (diagnosis suggestions, medicines read from documents not yet confirmed, follow-ups that can be added per document, documents that could not be read); profile completeness (5 personal fields, with the missing ones), allergies, number of conditions and active medicines, BMI and category, latest blood pressure and heart rate; the 5 most recent Timeline entries dated up to today.

The client never presents missing information as good health ("No open alerts" is followed by "This is not a health check"), shows urgent alerts first, and links every card to its page. No AI is used.

### 6.12 AI Summaries

Decision 2026-10-13 (`backend/app/services/summary_service.py`, `summary_facts.py`, `backend/app/ai/summary.py`). Rules decide; AI explains.

| Method | Path | Response |
|---|---|---|
| GET | `/summaries/history` | `{enabled, can_create, summary \| null, stale}` |
| POST | `/summaries/history` | `201` same; writes a new summary |
| GET | `/documents/{id}/summary` | same, for one document (`404` for another user's document) |
| POST | `/documents/{id}/summary` | `201` same; `409` while the document is not read |

- **On request only.** Nothing is sent to the AI provider until the user asks. Off unless `EXTRACTION_ENABLED=true` (`503`); `409` when there are no records; `429` above `SUMMARY_RATE_LIMIT_PER_HOUR` (default 20); `503` with a user-safe message when the provider is unavailable, rate-limited, or nothing could be checked. Written during the request (typically 5–40 s), not in the job queue: the queue is per document.
- **Facts.** The records are collected as numbered facts: Timeline entries (`F…`, newest first, at most 120) plus profile conditions, allergies, surgeries, hospitalizations, family history, BMI, sex and blood group; and gaps found by fixed rules (`C…`: open alerts, overdue follow-ups, unconfirmed medicines, diagnoses to review, follow-ups not added, unread or failed documents, no lab result in 12 months, missing profile details). Names, email, date of birth, and document titles are never sent.
- **Model output** (strict JSON schema, reasoning hidden): sections `overview`, `conditions`, `medicines`, `results`, `follow_ups`, `gaps`, each a list of sentences `{text, kind (record | interpretation), fact_ids}`; and `explanations` `{term, text, fact_ids}` of general medical knowledge.
- **Checking** (code): a sentence is kept only if it cites existing facts and every number (digits or number words) and month it states appears in the cited facts; at most 10 per section. An explanation is kept only if its term appears in a cited fact and it contains no numbers. Dropped items are counted and the user is told. A summary with nothing left fails.
- **Stored** in `ai_summaries` with sources, explanations, rule-based insights, `fingerprint` of the facts, `model_version`, `prompt_version`, and token counts. `stale` = the facts changed since. Deleting a document deletes its summary and every whole-history summary. Logs carry counts and timings only.
- **Client:** "AI-generated" badge; "AI interpretation" label on interpretation sentences; numbered citations to a Sources list (record, date, document, and whether the user checked it); general information in a separate box with the doctor's-advice note; rule-based "Things to check" labelled as not from the AI; "not medical advice".

## 7. Asynchronous Processing and AI APIs

Document extraction is the first asynchronous operation: the upload responds immediately, and progress is read from `GET /documents/{id}/observations` (clients poll every few seconds while the job is `pending` or `running`).

Long-running document processing or AI analysis may run asynchronously when needed. The contract must not depend on a particular background-processing technology.

When an operation runs asynchronously:

1. The API accepts a valid request and returns `202 Accepted`.
2. The response includes a stable processing identifier or resource URL.
3. The client can retrieve the current processing status.
4. The API reports completion or a safe, actionable failure status.
5. Results are available only to authorized users.

Processing status values match the job lifecycle in `backend_spec.md` Section 4.2:

`pending` → `running` → `completed` | `completed_with_warnings` | `failed` | `cancelled` (where supported)

The API must not report processing as complete before the result is ready.

AI results must distinguish extracted source information from AI-generated interpretation and identify uncertainty where applicable. Explanations based on general medical knowledge must be marked as such in the response and carry the doctor's-advice note (`DL_AI_spec.md` Section 6.1). Clinical boundaries for AI output are defined in `backend_spec.md` Section 1.4; the API must not expose any capability those boundaries prohibit.

## 8. Standard Error Response

All API errors use this structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "details": [
      {
        "field": "document_type",
        "issue": "Unsupported document type."
      }
    ],
    "request_id": "example-request-id"
  }
}
```

- `code` — stable, machine-readable identifier.
- `message` — understandable to the user or frontend developer.
- `details` — optional field-level validation information.
- `request_id` — correlates the request with backend logs and processing events.

Errors must not expose sensitive medical information, tokens, passwords, stack traces, or infrastructure details, and must not reveal whether another user's private resource exists.

## 9. Pagination, Filtering, and Sorting

Collection response structure (illustrative; each endpoint defines its exact schema):

```json
{
  "items": [],
  "pagination": {
    "limit": 20,
    "next_cursor": null
  }
}
```

- Use one consistent strategy, preferably cursor-based for collections that may grow significantly.
- Document default and maximum page sizes.
- Validate filter and sort fields against an explicit allowlist.
- Use deterministic ordering when paginating.
- Endpoints may omit pagination when results are naturally small and bounded.

### 9.1 Search

Record search supports these criteria, combinable in one request:

- Document type.
- Date or date range.
- Condition.
- Provider.
- Free-text query over extracted content.

Rules:

- Results are paginated (Section 9) and include only the authenticated user's records.
- Each result identifies the matching record type, its source document, and the matched field.
- Free-text queries are not placed in logs (`observability_and_reliability_spec.md` Section 4.2). Because a GET query string can appear in access logs, the endpoint design must keep the query text out of logged URLs (for example, by using a POST search request).

Implemented 2026-10-13 (`backend/app/services/search_service.py`): `POST /api/v1/search` with body `{query?, document_type?, date_from?, date_to?, condition?, provider?, limit (1–50, default 20), cursor?}`; at least one criterion is required (`422` otherwise, and when `date_to` is before `date_from`). Response `{items: [{record_type, id, title, date, matched_field, snippet, source_document_id, source_document_title, link}], total, next_cursor}`, newest first.

- Records searched: documents (name, hospital or clinic, file name), the text of read reports (consultation sections, imaging findings and impression, test interpretations, discharge facility and warning signs), lab results, medicines, diagnoses as written and profile conditions, follow-ups, allergies, surgeries, hospitalizations, and family history.
- Free text: every word must appear in the record (any field, ignoring case); partial words match. `matched_field` names the field and `snippet` shows the matching text.
- `document_type` matches the upload type or the type the document was read as (e.g. `test_report`); `provider` matches the document's hospital or clinic; `condition` keeps records from documents with a matching diagnosis, plus matching profile conditions; dates apply to each record's own date (undated records are left out).
- Searched in memory over the user's records; there is no `search_vector` index yet. The query is sent in the body, never logged or stored, and validation errors do not echo it.

## 10. API Security and Privacy

Security controls (input and file validation, upload-size and rate limits, CORS, audit events) are defined in `backend_spec.md` Section 8. Logging of sensitive data follows `observability_and_reliability_spec.md` Section 4.2. At the API level:

- Return only the minimum data required by the caller.
- Document each endpoint's upload limits, rate limits, and audited operations.

## 11. API Documentation and Contract Testing

- FastAPI's OpenAPI generation is the machine-readable API description.
- Document each endpoint's purpose, authentication requirements, parameters, request bodies, responses, status codes, and errors.
- Keep schemas aligned with the implementation.
- Test request validation, response schemas, authorization, user isolation, and error behavior.
- Test document upload and access permissions.
- Test asynchronous processing states, if implemented.
- Test that frontend expectations match the contract.

Detailed operational requirements for request correlation, logs, metrics, and health checks are in `observability_and_reliability_spec.md`.

## 12. Change Management

Traceability and change-management rules follow `goal_spec.md` Section 10. For API changes specifically:

1. Identify affected frontend and backend behavior.
2. Check compatibility with existing consumers.
3. Update this specification and related specifications.
4. Update schemas and contract tests.
5. Document any breaking change and its migration requirements.

New product features must not be introduced solely because an endpoint would be technically convenient.

## 13. API Contract Acceptance Criteria

| # | Criterion | Goal ref |
|---|-----------|----------|
| API-AC-01 | All endpoints use the `/api/v1` prefix. | AC-10 |
| API-AC-02 | Requests and responses follow documented schemas. | AC-10 |
| API-AC-03 | Protected endpoints validate Bearer access tokens and enforce authorization; the refresh token is only accepted from its `HttpOnly` cookie. | F-11 |
| API-AC-04 | Users cannot access another user's private records or documents without explicit authorization; such requests return `404`. | F-11, AC-08 |
| API-AC-05 | Errors follow the standard structure without exposing sensitive internal details. | AC-09 |
| API-AC-06 | Document upload, retrieval, and deletion follow the defined validation and authorization rules. | F-2, AC-01 |
| API-AC-07 | Asynchronous operations, when implemented, expose accurate status using the defined status values and return results only to authorized users. | AC-09 |
| API-AC-08 | AI-generated interpretations and general-knowledge explanations remain distinguishable from source medical information. | F-8, AC-06 |
| API-AC-09 | Request identifiers support troubleshooting without exposing sensitive information. | AC-09 |
| API-AC-10 | OpenAPI documentation and contract tests stay aligned with the implemented API. | AC-10 |
| API-AC-11 | API behavior stays within approved scope: no medication-taking or prescription-renewal reminders, and no endpoints for deferred features. | AC-11 |
| API-AC-12 | Safety alerts can be listed, acknowledged, and resolved by their owner. | F-9, AC-07 |
| API-AC-13 | Export endpoints return a PDF summary, CSV/JSON data, and original documents for the authenticated user only. | F-12, AC-13 |
| API-AC-14 | Search supports type, date, condition, provider, and extracted-content criteria and returns only the user's records. | F-2 |
| API-AC-15 | Suggestions can be listed and accepted, corrected, or rejected; confirmed data changes only on acceptance or correction. | F-1, F-7 |