# Backend Specification

## 1. Purpose and Architecture Overview

### 1.1 Purpose

The backend provides the core application services for the Multimodal AI Healthcare Decision-Support System. It manages user health data, medical documents, medication records, health observations, checkup/follow-up tracking, safety alerts, and communication with AI processing components.

It must store health information securely, keep it linked to its source, restrict it to authorized users, and coordinate AI processing without letting AI output silently overwrite original records or verified user data.

### 1.2 Architecture Principles

- **Modular design:** Independent modules so features can change with minimal impact on others.
- **API-first:** Functionality exposed through documented, versioned APIs.
- **Separation of concerns:** API handling, business logic, data access, document processing, AI orchestration, and background tasks kept separate.
- **Data integrity:** Original documents preserved; source data, extracted information, user corrections, and AI interpretations kept distinct (Section 5).
- **Security by design:** Authentication, authorization, data isolation, encryption, and auditability throughout (Section 8).
- **Asynchronous processing:** Background jobs introduced when processing needs justify them (Section 4.1).
- **Failure resilience:** Dependency, processing, database, and notification failures never silently lose data (Section 9).
- **Clinical safety:** Safety-critical workflows enforced by validated application rules, not solely AI (Section 1.4).
- **Testability:** Modules and interfaces testable independently and in integration (Section 10).
- **Extensibility:** New roles, integrations, and data sources added without full redesign (Section 12.3).

### 1.3 Backend Responsibilities

1. Manage user profiles and health-history records.
2. Upload, store, retrieve, and manage medical documents.
3. Coordinate document extraction and multimodal AI processing.
4. Store structured health observations with values, units, dates, and source references.
5. Manage prescriptions, medication records, and medication history.
6. Support health timelines and source-grounded summaries. Historical comparison and trend analysis are deferred (`goal_spec.md` Section 6).
7. Track checkup and follow-up dates and their upcoming/overdue status.
8. Apply configured safety rules, record resulting alerts, and manage their acknowledgement and resolution.
9. Provide secure APIs to the frontend and authorized integrations.
10. Manage authentication, authorization, audit records, and error handling.
11. Send account emails (e.g., password reset) and own notification channels.
12. Generate user data exports.
13. Support background processing, recovery, and operational monitoring.

### 1.4 Backend Boundaries

This is the single reference for clinical and data boundaries in this spec. The backend must not:

- Treat AI-generated information as verified medical fact without appropriate validation.
- Allow AI to diagnose diseases, prescribe, change dosages, discontinue medication, issue replacement prescriptions, or resolve conflicting prescriptions.
- Declare a user medically fit or disease-free based solely on records or AI analysis.
- Depend solely on an LLM or other probabilistic AI component to detect or handle medical emergencies.
- Imply that the absence of an alert means a user is safe or that an emergency has been ruled out.
- Expose one user's health records to another user without authorization.
- Replace or discard original medical documents when extracting or correcting information.
- Invent clinical thresholds, reference ranges, escalation rules, or medical recommendations. These must come from appropriate, reviewed sources and must not be changed by an AI component.
- Implement medication-taking reminders or prescription-renewal reminders (out of scope per `goal_spec.md` Section 7).

## 2. Technology Stack and Backend Structure

### 2.1 Technology Decisions

- **Backend framework:** FastAPI with Python.
- **Request and data validation:** Pydantic.
- **Database:** PostgreSQL.
- **Database access:** SQLAlchemy.
- **Database migrations:** Alembic.
- **Authentication:** JWT-based authentication with explicit authorization checks.
- **Background processing:** Begin without a dedicated job-processing infrastructure. Introduce a suitable background-job system when processing needs justify it.
- **Document storage:** Protected local storage in development; object storage in deployed environments (Section 6.3).
- **Email delivery:** Through a replaceable email-service interface. Provider (decided): Amazon SES in deployed environments; a local stub that logs a redacted notice in development. Emails never contain medical information.
- **Architecture:** Begin with a modular monolith, keeping database access, authentication, background processing, and document storage behind clear interfaces where appropriate.
- **API documentation:** OpenAPI, generated by FastAPI.
- **Async:** Used where it gives a clear benefit, particularly for I/O-bound operations.
- **Dependencies:** Reproducible dependency management with explicitly declared dependencies and versions.

Code must favor readability and maintainability to support learning, debugging, and future development.

### 2.2 Data Persistence

PostgreSQL stores structured data (profiles, observations, medication records, follow-ups, alerts, document metadata); see Section 5.6. Original documents are stored outside the database through the document-storage interface (Section 6.3).

### 2.3 Application Structure

Organize by business responsibility, not in a single file. Logical modules:

- **API layer:** Routes, request validation, response formatting.
- **Authentication and authorization:** Identity, access policies, user-level isolation.
- **User and health-history module:** Profiles and personal health records.
- **Document module:** Upload, storage references, extraction status, document lifecycle.
- **Health-observation module:** Measurements, units, dates, provenance, comparisons.
- **Medication module:** Prescription records, recorded medication schedules, medication history.
- **Follow-up and alert module:** Checkup/follow-up tracking, safety alerts and their lifecycle.
- **Notification module:** Email delivery for account workflows; future reminder channels.
- **Export module:** PDF summary and CSV/JSON data exports.
- **AI orchestration module:** Interfaces to document processing, multimodal AI, retrieval, summarization.
- **Data-access layer:** Database operations and transactions.
- **Background processing module:** Long-running jobs, retries, scheduled tasks.
- **Shared infrastructure:** Configuration, logging, error handling, security utilities, common validation.
- **Testing module:** Unit, integration, API contract, security, and safety tests.

These are logical modules, not separate deployments. The modular monolith is kept unless measured requirements justify otherwise.

### 2.4 Configuration, Secrets, and Environments

- Separate development, testing, and production environments, with isolated configuration, credentials, databases, and storage.
- Development settings must never be used implicitly in production.
- Environment-specific settings stay outside source code.
- Required configuration is validated at startup; the app fails clearly when it is missing or invalid, without exposing secrets.
- Secrets (passwords, tokens, API keys, signing keys, AI-provider and email-provider keys) are never hardcoded, committed, exposed to the frontend, or printed in logs, exceptions, or diagnostics.
- Deployed environments use secrets management where appropriate; access to secrets is restricted per component; rotation is supported without redesign.
- Database, AI-provider, storage, and operational settings are independently configurable.
- Authentication settings: `JWT_SECRET` (required, at least 32 characters), `JWT_ISSUER`, `COOKIE_SECURE`, `FRONTEND_BASE_URL` (for links in emails), `PASSWORD_RESET_MINUTES`, `LOGIN_MAX_FAILURES`, `LOCKOUT_MINUTES`, and `EMAIL_BACKEND` (`file` in development writes emails to a local, git-ignored folder; `ses` in deployment).
- AI settings: `EXTRACTION_ENABLED` (default `false`), `GROQ_API_KEY` (secret; never committed), `AI_MODEL` (default `qwen/qwen3.8-27b`), `EXTRACTION_MAX_ATTEMPTS` (default 3), `WORKER_POLL_SECONDS`.
- Document settings: `DOCUMENT_STORAGE_DIR` (local storage folder for development, git-ignored; default `storage/documents`) and `UPLOAD_RATE_LIMIT_PER_HOUR` (per user; default 30).
- Initial development and testing use synthetic or de-identified data only. Real patient data requires authorization, privacy controls, and review first.

## 3. API Design

### 3.1 API Principles

The backend exposes a consistent, versioned REST API for the frontend and authorized integrations. It must:

- Use resource-oriented endpoints and appropriate HTTP methods.
- Use `/api/v1` as the initial version prefix.
- Validate requests with Pydantic schemas.
- Return predictable response structures and meaningful status codes.
- Paginate potentially large collections.
- Keep API contracts independent of database models and AI-provider response formats.
- Document endpoints, parameters, schemas, and errors through OpenAPI.

Security requirements for the API are in Section 8.

### 3.2 Request Lifecycle and Layering

Requests follow the applicable stages:

1. Receive the HTTP request.
2. Validate parameters, payload, types, and required fields.
3. Authenticate when required.
4. Authorize access to the resource or operation.
5. Execute the application service.
6. Access or update data through the data-access layer.
7. Validate business rules and data integrity.
8. Return a documented response with an appropriate status code.
9. Record execution status, timing, and errors (Section 9.3).

Not every request needs every stage, but personal health records must always remain protected.

Layer responsibilities:

- **Routes:** HTTP requests and responses only.
- **Schemas:** Input validation and output structures.
- **Services:** Application and business logic.
- **Repositories/data access:** Database operations.
- **AI orchestration:** AI and document-processing coordination.
- **Background workers:** Long-running or scheduled tasks.

Business logic must be testable without starting the full web application.

### 3.3 Responses and Errors

Responses must distinguish:

- Invalid requests and validation failures.
- Unauthenticated requests.
- Forbidden operations on the user's own resources.
- Missing resources, including other users' resources (reported as not found so existence is not revealed).
- Conflicts with current resource state.
- Rate limiting.
- Temporary dependency failures.
- Unexpected internal errors.

Status codes and the error response format are defined in `api_contract_spec.md` Sections 4.3 and 8.

Error responses must not reveal secrets, raw database exceptions, stack traces, internal implementation details, or unnecessary medical information.

### 3.4 API Contract Ownership

Endpoint definitions, request/response schemas, and error formats are maintained in `api_contract_spec.md`. Changes to endpoints, fields, validation, responses, or errors must be reflected there and in relevant tests.

Preserve backward compatibility where practical. Breaking changes must be documented and introduced through controlled versioning or migration.

## 4. Background Jobs, Retries, and Idempotency

### 4.1 When to Use Background Jobs

- Initially, suitable short-running operations are handled within the API request lifecycle.
- Dedicated background processing is introduced when task duration, workload, reliability, or concurrency requirements make it necessary.
- Queue, worker, and scheduler technologies are chosen by actual requirements, not introduced unnecessarily.
- **Decided (extraction):** a PostgreSQL-backed queue in `processing_jobs` and a separate worker process (`python -m app.worker`). Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED`; transient failures retry with backoff (30 s, 2 min, 10 min) up to `EXTRACTION_MAX_ATTEMPTS`; permanent failures stop immediately; stale running jobs (no heartbeat for 10 minutes) are returned to the queue when a worker starts.

Candidates for background jobs include:

- Document extraction and AI analysis.
- Retries of eligible transient failures.
- Email delivery (and reminder delivery, once introduced).
- Data export generation.
- Supported batch operations.

When an operation runs as a background job, the API returns `202 Accepted` with a job identifier and provides an endpoint to retrieve status and results. Background jobs expose status, record failures, and retry safely (Sections 4.2–4.4).

### 4.2 Job Lifecycle

Each job has a unique identifier and a controlled lifecycle:

- Pending.
- Running.
- Completed.
- Completed with warnings or partial results.
- Failed.
- Cancelled, where supported.

The backend records timestamps, processing stages, and failure details. Job status and results are accessible only to authorized users.

The backend must distinguish three states: request accepted, processing completed, and resulting information reviewed or validated.

### 4.3 Retries and Timeouts

- External calls and background operations use suitable timeouts.
- Retries are bounded, use backoff, and apply only to eligible (transient) failures.
- Permanent failures are surfaced for corrective action, not retried indefinitely.
- Successful intermediate results are preserved where safe and practical.
- Terminal failures are recorded with a recoverable status where possible.
- A failure must never delete or corrupt an original document.

### 4.4 Idempotency and Duplicate Prevention

Retried operations must not create duplicate side effects. Use idempotency keys, unique constraints, stable job identifiers, or equivalent mechanisms, especially for:

- Document uploads.
- Creation of extracted health observations.
- Medication-record creation and updates.
- Follow-up entry creation and email delivery.
- Retried AI-processing jobs.

Repeated requests must not silently overwrite original records or create duplicate clinical-history entries.

## 5. Data Management

### 5.1 Data Principles

The data layer must:

- Maintain clear relationships between users and their records.
- Preserve integrity through constraints and transactions.
- Retain provenance of medical information.
- Keep original documents, extracted facts, user corrections, and AI interpretations distinct.
- Support chronological retrieval and comparison.
- Prevent unauthorized access, accidental deletion, and unintended overwriting.
- Minimize duplication of sensitive information.

### 5.2 Core Data Domains

1. **User and profile:** Identity references, profile values, preferences, account status. Each profile value records its origin (user-entered, or accepted/corrected suggestion with a link to that suggestion) and keeps a change history.
2. **Medical documents:** Metadata, storage references, categories, provider (when known), upload timestamps, processing status, ownership.
3. **Extracted medical information:** Observations, values, units, dates, reference ranges when available, source references.
4. **Health history:** Conditions and history recorded or confirmed by the user or extracted from documented sources.
5. **Medication records:** Details, recorded instructions, effective dates when known, history.
6. **Appointments and follow-ups:** Checkups, follow-up schedules, due dates, completion status, and whether the entry is user-entered or a confirmed document suggestion.
7. **Notifications:** Email delivery status, retry information, event references. Reminder schedules once reminder delivery is introduced.
8. **AI processing records:** Jobs, model/provider metadata where appropriate, status, errors, output references.
9. **AI-generated insights:** Summaries, interpretations, source references, timestamps, review status where applicable.
10. **Safety alerts:** Triggering rule, input references, severity, creation time, acknowledgement/resolution status.
11. **Audit records:** Security-relevant and data-access events, per privacy and retention requirements.
12. **Suggestions awaiting confirmation:** Profile values and follow-up dates proposed from documents (Section 5.3).
13. **Search index:** User-scoped index over document metadata and extracted content (Section 7.1).

These are logical domains, not necessarily separate tables. Entities, fields, relationships, and constraints are defined in `data_model_spec.md`.

### 5.3 Document Provenance and Corrections

Each document's metadata includes:

- Unique document identifier.
- Owning user or authorized account.
- Original storage reference.
- Document type/category, when known.
- Healthcare provider (hospital, lab, clinic, or clinician), when known.
- Upload and document dates, when available.
- Processing status and errors.
- References to extracted information and processing results.

Extracted information keeps a traceable link to its source document and, where feasible, the page, section, or text location.

**Suggestions awaiting confirmation.** Profile values and follow-up dates proposed from documents are stored as suggestions, separate from confirmed data. Each suggestion records:

- Unique identifier and owning user.
- Target: suggestion type (profile value or follow-up date) and target field (e.g., allergy, condition, blood group, follow-up due date).
- Suggested value, unit where applicable, and the original text as written in the document.
- Source document reference and page/text location.
- Extraction confidence and validation findings (Section 6.5); confidence is not proof of correctness.
- Status: `pending`, `accepted`, `corrected`, `rejected`, or `superseded` (a newer suggestion or user edit replaced it).
- Reviewer action: who reviewed it, when, and the corrected value if the user changed it.
- Reference to the profile value or follow-up entry created or updated on acceptance.
- Creation timestamp and the AI processing record that produced it.

Rules:

- A suggestion never changes confirmed data until the user accepts or corrects it.
- Accepting a suggestion that conflicts with an existing confirmed value requires an explicit choice by the user; the existing value is kept in history.
- Rejected suggestions are retained for traceability and are not re-proposed from the same source location.
- Status transitions are validated (Section 7.6).

Corrections by a user or reviewer preserve the distinction between original extraction and correction through versioning or audit history.

### 5.4 Transactions and Consistency

- Related records that must change together use transactions; partial updates must be prevented.
- Database transactions do not cover AI services, file storage, or notification providers. Workflows involving these use state tracking, retries, and recovery.
- A multi-step operation must not be reported as complete when required steps failed.

### 5.5 Data Lifecycle, Retention, Export, and Deletion

The backend must support:

- Creating and updating records through authorized workflows.
- Preserving historical records required for traceability.
- Document replacement, correction, and deletion requests.
- User data export and deletion requests, subject to retention obligations. Exports provide a readable PDF health summary, structured CSV/JSON data, and separate download of original documents, limited to the requesting user's authorized records.
- Configured retention and backup policies.
- Recording changes to sensitive records.

Deletion and retention must account for legal requirements, backups, and audit integrity. User-requested deletion must be distinguished from archival, deactivation, and retention-required data.

### 5.6 Database Technology

- PostgreSQL is the primary relational database, accessed through SQLAlchemy (Section 2.1).
- Define appropriate relationships, constraints, indexes, and transaction boundaries.
- Database credentials follow Section 2.4. Migration rules are in Section 11.1.

## 6. Medical Document Ingestion and Processing

### 6.1 Purpose

A secure, traceable workflow for receiving documents, storing originals, extracting supported information, and making validated results available. OCR engines, parsers, and AI providers must be replaceable without redesigning the core backend.

### 6.2 Supported Inputs

Initial support, subject to configurable validation:

- PDFs, text-based and scanned.
- Common images (JPEG, PNG).
- Digital reports with selectable text.
- Scanned prescriptions, lab reports, discharge summaries, and similar documents.

Additional formats, including DICOM, are added only when explicitly designed, implemented, and tested.

### 6.3 Upload and Storage

1. Authenticate and authorize the user.
2. Validate the file against configured restrictions (Section 8.4).
3. Generate a unique document identifier.
4. Store the original through the document-storage interface.
5. Record metadata and ownership in the database.
6. Start processing when requested, in the request or as a background job (Section 4.1).
7. Return the document identifier and processing status.

Storage rules:

- Original documents are kept separate from their relational metadata.
- A replaceable document-storage interface is used: protected local storage during development, object storage in deployment (Section 11.4).
- Local filesystem paths must not be assumed to remain valid in deployed environments.
- Internal storage paths and unrestricted storage URLs must not be exposed.
- Original files, provenance, processing status, and error information are preserved. Originals remain unchanged during extraction and analysis; replacement or correction follows a controlled workflow that preserves history.
- Deployed object storage enforces access restrictions, encryption, and backup or retention policies.

### 6.4 Processing Pipeline

Independently testable stages:

1. **File validation:** Integrity, format, size, security restrictions.
2. **Content extraction:** Embedded text and metadata when available.
3. **OCR:** When text extraction is insufficient.
4. **Classification:** Document category when supported; uncertain/unknown allowed.
5. **Information extraction:** Dates, test names, values, units, medication details, other supported fields.
6. **Normalization:** Convert to application structures without discarding the original representation.
7. **Validation:** Required fields, types, unit consistency, date plausibility, applicable rules.
8. **Provenance association:** Link to the original document and page/text locations.
9. **Persistence:** Save results and metadata with consistency controls.
10. **Completion reporting:** Update status and make results available to the authorized user.

Stages are selected according to document type and content.

### 6.5 Extraction Accuracy and Uncertainty

Stage completion does not mean extracted information is correct. Supported outcomes:

- Extracted and validated.
- Requires user or reviewer confirmation.
- Partially extracted.
- Unreadable or unsupported.
- Conflicting or ambiguous.
- Failed.

Results include confidence information, source locations, and validation findings where feasible. Missing values, unclear handwriting, ambiguous dates, uncertain units, and conflicts are flagged, not silently resolved. Confidence scores are not proof of clinical correctness.

### 6.6 Human Review and Corrections

Where review is required:

- Identify the information needing review.
- Preserve the original document and extraction output.
- Record corrected/confirmed values and their provenance.
- Keep a history of material corrections.
- Never present unreviewed information as verified.

Review requirements depend on information type and intended use. Safety-critical information must not bypass validation because a model reports high confidence.

### 6.7 AI Component Integration

The backend interacts with OCR, extraction, multimodal analysis, and language models through separate, replaceable interfaces. AI responsibilities coordinated by the backend:

- Extracting supported information from documents.
- Coordinating OCR, parsing, and multimodal processing.
- Converting extracted information into validated structured data.
- Generating summaries grounded in authorized records (Health Q&A is deferred).
- Suggesting profile values and follow-up dates from documents, for user confirmation.
- Explaining triggered safety alerts.
- Recording status, errors, source references, and uncertainty.
- Supporting different providers/models without coupling business logic to one.

The pipeline must not live inside API route handlers or depend on a single provider.

The backend owns orchestration, authorization, validation, persistence, job management, and safe exposure of results. Model selection, prompts, extraction schemas, and evaluation belong in `DL_AI_spec.md`.

## 7. Health Domain Services

### 7.1 Health History

The backend must:

- Maintain medical history and conditions recorded by the user or documented in records.
- Organize observations chronologically.
- Link history and observations to their sources.
- Search and filter records by document type, date or date range, condition, provider, and extracted content (text search). Search uses a user-scoped index and returns only the user's authorized records; results link to the matching source record. Search technology is chosen during implementation design (PostgreSQL full-text search is the default starting point).
- Flag missing, incomplete, outdated, or conflicting information where applicable.
- Preserve historical entries when new information arrives.
- Record authorized corrections without silently overwriting history.

Documented, user-entered, and AI-generated information remain distinguishable, and extracted information keeps its extraction and validation status.

### 7.2 Health Observations and Comparisons

Observations preserve:

- Observation type/name.
- Reported value and unit.
- Date/timestamp, including uncertainty where applicable.
- Reference range, if from an appropriate source and applicable.
- Source document or other authorized source.
- Extraction, validation, and review status.
- Context needed to interpret the measurement.

Rules:

- Historical observations are never overwritten because a newer result exists.
- Missing dates, units, or context are represented as missing or uncertain, not invented.
- Original values and units are preserved.
- A reference range is not a complete assessment of an individual's health.

Cross-date comparison and trend analysis are deferred (`goal_spec.md` Section 6). When introduced:

- Comparisons consider names, units, dates, and context; incompatible measurements are not compared, and similarly named measurements are not assumed comparable.
- Missing context that prevents comparison is identified.
- Comparison results reference supporting source records.
- Changes are presented as observations or trends, not diagnoses or proof of disease progression.

### 7.3 Medication and Prescription Management

Medication and prescription tracking is in scope. The backend must:

- Let users create and edit medication records, and record medication information and its source.
- Maintain names, recorded dosage instructions, frequency, start/end dates, and status when available.
- Associate records with supporting prescriptions or other authorized sources.
- Track application-level record status.
- Maintain changes and corrections without erasing prior history.
- Flag conflicting or incomplete medication information for review.

The backend must distinguish:

- A prescription recorded in a document.
- Information entered by the user.
- A user's confirmation that a medication is currently being taken.

A medication must not be inferred as currently active solely because it appears in an older prescription.

### 7.4 Checkup and Follow-Up Tracking

The initial release tracks checkups, investigations, and follow-up appointments in the app:

- Creating, updating, completing, and cancelling authorized follow-up entries.
- Dates, times, recurrence rules, and time zones.
- Calculating upcoming and overdue status.
- Accepting document-derived date suggestions only after user confirmation.

Automated reminder delivery (email, push, or other channels) is deferred (`goal_spec.md` Section 6). When introduced, it must track status (scheduled, sent, delivered when confirmed, failed, cancelled), retry eligible failures without duplicates (Section 4), support user notification preferences, and never show a reminder as delivered when delivery status is unknown. A sent reminder is not proof the medical action happened.

### 7.5 Safety Rules, Alerts, and Urgent Scenarios

Configurable safety rules use explicitly defined, validated criteria and the relevant source data, context, and validation status. Rules decide whether an alert is raised; AI may only explain a triggered alert (`DL_AI_spec.md` Section 9.1). Flagging results outside the reference range stated in the source report is a rule, and such flags are presented as items for review, not diagnoses. The system must:

- Record the triggering rule or criterion.
- Link the alert to the relevant observations or records.
- Record creation time, status, and acknowledgement/resolution history; let users acknowledge and resolve their alerts through the API.
- Explain the basis for the alert in understandable language.
- Identify uncertainty or missing information affecting interpretation.
- Support testing for missed alerts, false alarms, and conflicting inputs.
- Allow rule updates only through controlled change management.

Urgent workflows follow explicitly defined, validated safety requirements. When immediate medical attention may be needed, the application gives guidance to seek professional or emergency care without waiting for AI analysis.

External emergency services must not be contacted automatically unless a separately authorized, validated, and legally appropriate workflow has been designed and approved.

### 7.6 Follow-Up, Notification, and Alert Lifecycle

Follow-ups, notifications, alerts, and suggestions have defined lifecycle states and transitions, distinguishing as applicable:

- Creation and scheduling.
- Evaluation or processing.
- Notification attempts and outcomes.
- User acknowledgement.
- Completion, cancellation, or resolution.
- Failure requiring retry or investigation.

State transitions are validated so invalid updates cannot corrupt history. State changes are observable and traceable.

### 7.7 Separation of Responsibilities

Health history, medication management, follow-up tracking, notification delivery, exports, and safety-rule evaluation have clearly defined interfaces. They may share one FastAPI application but must remain modular.

AI may assist with extraction and explaining source-backed observations. Deterministic application logic remains responsible for authorization, state-change validation, approved safety rules, and follow-up workflows.

## 8. Security and Privacy

### 8.1 Authentication

- Use JWT-based authentication for API access; no custom cryptography.
- Token transport: a short-lived access token sent in the `Authorization: Bearer` header, and a refresh token in a `Secure`, `HttpOnly`, `SameSite` cookie scoped to the refresh endpoint (`api_contract_spec.md` Section 5).
- Token lifetimes and rotation follow `api_contract_spec.md` Section 5.1 (access 15 minutes, refresh 7 days, rotated on use).
- Support email-and-password registration, login, logout, and password reset via email (Section 2.1, email delivery).
- Validate tokens on protected requests; reject unauthenticated requests.
- Handle expired, invalid, and revoked tokens.
- Protect credentials and signing secrets (Section 2.4).
- Keep authentication decoupled from business logic to allow provider changes.

### 8.2 Authorization and Data Isolation

Authentication identifies the user; authorization determines which resources and actions that user may access.

- Possession of a valid JWT is not permission to access another user's data.
- Enforce user-level data isolation on every applicable endpoint, through ownership or explicit authorization checks on every protected resource: documents, observations, medications, appointments, AI results, alerts, and jobs.
- Protect uploaded medical documents in storage with access controls equivalent to the API's.
- Prevent access through manipulated resource identifiers.
- Deny by default when authorization cannot be established.
- Do not rely on frontend controls as a security boundary.
- Database-level controls supplement, not replace, application-level checks.

Future caregiver or clinician access requires an explicitly designed authorization model, consent, and role-specific permissions. It must not be enabled merely because the architecture supports more roles.

### 8.3 Sensitive Data Protection

- Secure transport (encryption in transit) in deployed environments.
- Encryption at rest for databases, document storage, and backups.
- Least-privilege access to data, including least-privilege database credentials restricted to authorized components.
- No medical content in URLs or error messages.
- Protected storage references and download links.
- Protected backups and recovery copies.
- No collection or retention of data not needed for intended functions.
- No exposure to unauthorized third parties.

### 8.4 Input, File, and Untrusted Content Security

All incoming data, uploaded documents, extracted text, and AI-generated content are untrusted until validated.

- Validate payloads, parameters, and files; apply configurable request-size limits, file-size limits, and allowed formats.
- File extensions alone are not proof a file is safe or valid.
- Apply controls against malicious or malformed documents; never execute uploaded content.
- Prevent unsafe file paths and unauthorized file retrieval.
- Use parameterized queries or safe ORM mechanisms to prevent injection.
- Apply rate limits.
- Restrict cross-origin requests to configured frontend origins in every environment.
- Instructions embedded in documents must not override application policies, access controls, tool permissions, or safety rules during AI processing.

Input validation supplements, not replaces, authorization and business-rule enforcement.

### 8.5 External AI and Service Security

Before sending medical data to an external provider, confirm the integration is approved for that data and configured for applicable privacy and security requirements. The backend must:

- Send only the information required for the operation, without unnecessary identifiers or unrelated history.
- Protect provider credentials and service-to-service communication.
- Handle provider failures without exposing sensitive data.
- Prevent external AI outputs from bypassing authorization, validation, or safety rules.
- Keep integrations configurable so providers can be replaced or disabled.

### 8.6 Audit and Security Events

Record:

- Authentication failures and significant authentication events.
- Authorization failures on protected resources.
- Sensitive record changes and corrections.
- Document access or deletion where required.
- Changes to permissions and security configuration.
- Relevant administrative actions.

Audit records have controlled access and retention protections and must not duplicate complete documents, credentials, or other sensitive content.

### 8.7 Privacy and Consent

- Privacy requirements fit the intended deployment and jurisdiction.
- Any future sharing with caregivers, clinicians, or external organizations requires an explicitly authorized workflow with consent and access controls.
- Privacy, consent, and data-lifecycle rules must be reviewed before real patient data enters the system.

Security failures are handled safely, giving enough operational detail for investigation without disclosing sensitive details to unauthorized users.

## 9. Reliability, Observability, and Recovery

### 9.1 Reliability Principles

The backend must remain predictable when dependencies fail, requests repeat, or jobs are interrupted:

- No silent data loss.
- Transient and permanent errors handled differently (Section 4.3).
- Consistent processing and notification states.
- No duplicate side effects (Section 4.4).
- Actionable error information without sensitive data.

### 9.2 Health Checks

Defined in `observability_and_reliability_spec.md` Section 6.

### 9.3 Logging and Metrics

Logging rules, the sensitive-data rule, and metrics are defined in `observability_and_reliability_spec.md` Sections 4 and 5. The backend implements them.

### 9.4 Job Recovery

- Persist job state where recovery requires it.
- Identify interrupted or stale jobs and resume or retry eligible work safely.
- Protect original documents and committed records.
- Document recovery limitations.

Backups, restoration, and recovery objectives are defined in `observability_and_reliability_spec.md` Section 8.

## 10. Testing and Quality Assurance

### 10.1 Principles

Testing is automated and repeatable, covers success and failure cases, and uses synthetic or de-identified data (Section 2.4). External dependencies are mocked where appropriate, but not where real database behavior matters for correctness.

### 10.2 Unit Tests

- Request and domain validation.
- Observation normalization and compatibility checks.
- Medication-record management.
- Follow-up upcoming/overdue calculation and lifecycle transitions.
- Safety-rule evaluation and alert acknowledgement/resolution transitions.
- Export generation (PDF, CSV/JSON) limited to the user's records.
- Email delivery handling, including failures.
- Document-processing state transitions.
- Authorization and data-access policies.
- Error handling and retry decisions.

### 10.3 API Integration Tests

- Valid and invalid requests.
- Authentication and authorization.
- Status codes and response schemas.
- Persistence and transactional behavior.
- Pagination and filtering.
- Search by each supported criterion, and that search never returns another user's records.
- Suggestion accept, correct, and reject flows, including conflicts with existing values.
- Async job creation and status retrieval.
- Consistent error responses.
- Prevention of cross-user access.

### 10.4 Database Tests

- Relationships and constraints.
- Migration correctness.
- Transaction behavior.
- Historical-record preservation.
- Duplicate prevention.
- Data isolation.
- Recovery from applicable database failures.

### 10.5 Document-Processing Tests

- Supported and unsupported formats.
- Corrupt, malformed, empty, or oversized files.
- Text-based and scanned documents.
- Extraction failures and partial results.
- Ambiguous values and missing units.
- Source-reference preservation.
- Duplicate processing attempts.
- OCR or AI-provider failures, retries, and recovery.

Use a controlled synthetic or de-identified evaluation dataset with expected results where possible.

### 10.6 AI Integration Tests

Verify the backend:

- Handles valid and malformed model outputs.
- Validates structured outputs before persistence.
- Preserves source references.
- Handles unavailable providers and timeouts.
- Prevents untrusted document content from bypassing controls.
- Does not treat confidence scores as proof of correctness.
- Does not convert uncertain outputs into verified facts.
- Labels general-knowledge explanations and includes the doctor's-advice note.

Model quality and clinical evaluation methodology are in `DL_AI_spec.md`.

### 10.7 Security and Safety Tests

Security:

- Authentication and authorization enforcement.
- Cross-user data isolation.
- Invalid and expired credentials.
- Unsafe uploads and unauthorized document access.
- Input validation and database-access security.
- Secrets handling and sensitive-data exposure.
- External-service failures and access-control boundaries.

Safety:

- Approved alert criteria and boundary conditions.
- Missing, conflicting, and invalid inputs.
- False-positive and false-negative evaluation where reference data exists.
- Prohibited autonomous medical actions (Section 1.4) cannot be triggered.
- Absence of an alert is not represented as proof of safety.

Clinical thresholds and safety rules are reviewed against appropriate sources before production use.

### 10.8 Regression Tests

Rerun existing tests when changes could affect them. Changes to API contracts, data models, authorization, document processing, or safety rules require regression coverage. Proportionate verification (decided):

- **Minor changes** (small code tweaks, text or UI adjustments, minor bug fixes that do not touch the areas below): run the tests for the affected module plus a focused manual check; the full suite is not required.
- **All other changes**, including any change to API contracts, data models, authentication/authorization, document processing, or safety rules: run the full test suite and relevant manual verification.

### 10.9 Completion and Release Gates

- A feature is not complete just because code exists; completion requires tests and verification evidence.
- Failed, skipped, or unexecuted tests are reported accurately.
- Release readiness covers correctness, security, data integrity, failure handling, and safety.

## 11. Deployment and Environment Management

### 11.1 Migrations

- Schema changes use version-controlled, testable Alembic migrations; storage changes use documented, version-controlled procedures. Both account for existing data, compatibility, and recovery.
- Migrations run through a controlled process, not unpredictably on every startup.
- Destructive changes require review and safeguards.

### 11.2 Dependencies

Dependencies are updated through controlled, tested changes. Known security issues in important dependencies are assessed and addressed.

### 11.3 Deployment Security

- Secure configuration, restricted service permissions, protected secrets, secure network communication, access-controlled storage.
- No debug mode or development-only endpoints in production.
- Support safe configuration changes, updates, and rollback from failed releases.

Hosting, infrastructure, and deployment automation will be defined during implementation design.

### 11.4 Environments, Storage, and Database Provisioning

- Use environment-specific configuration for local development, testing, and deployment (Section 2.4).
- Document storage per environment follows Section 6.3.
- PostgreSQL is provisioned per environment, with credentials managed through secure configuration or a secrets manager.
- Production secrets and sensitive medical records must never be committed to version control.

## 12. Constraints, Assumptions, and Extensibility

### 12.1 Constraints

Product-level constraints are defined in `goal_spec.md` Section 9.1. Backend-specific boundaries are in Section 1.4 of this spec.

### 12.2 Assumptions

Product-level assumptions are defined in `goal_spec.md` Section 9.2.

### 12.3 Extensibility

New capabilities must not require unnecessary changes to unrelated modules. Potential extensions:

- Authorized caregiver access.
- Healthcare-provider and health-record integrations.
- Additional document formats and processing engines.
- Additional AI models and providers.
- Wearable and health-device integrations.
- New reminder and notification channels.
- Additional validated safety rules and monitoring.

Extensions follow the same security, privacy, data-integrity, and clinical-safety principles. Extensibility does not justify adding services, dependencies, or infrastructure before a demonstrated need.

## 13. Backend Acceptance Criteria

| # | Area | Criterion | Goal ref |
|---|------|-----------|----------|
| BAC-01 | API | Endpoints follow documented contracts with appropriate status codes and response structures. | AC-10 |
| BAC-02 | Authentication | Protected endpoints validate JWTs; missing, expired, invalid, or revoked tokens are rejected. Registration, login, logout, and password reset via email work as specified. | F-11 |
| BAC-03 | Data isolation | User-level isolation is enforced on every applicable endpoint; a valid JWT alone does not grant access to another user's data. Verified by cross-user access tests. | F-11, AC-08 |
| BAC-04 | Document integrity | Originals remain preserved during extraction, correction, and processing failures. | F-2, AC-01 |
| BAC-05 | Extraction provenance | Extracted information retains source references and validation status. | F-3, AC-02 |
| BAC-06 | Data integrity | Observations, medication records, and history maintain required relationships and history. | F-4, F-5, AC-03 |
| BAC-07 | Health timeline | Observations are retrievable chronologically; records from different dates are not merged; missing context is represented as missing. | F-6, AC-04 |
| BAC-08 | Background processing | When background jobs are used, they expose accurate status, record failures, and retry without duplicate or inconsistent updates. | AC-09 |
| BAC-09 | Follow-ups | Checkup/follow-up entries meet lifecycle requirements and show correct upcoming/overdue status. Medication-taking reminders and prescription-renewal reminders are not implemented. | F-7, AC-05 |
| BAC-10 | Safety alerts | Validated rules produce traceable alerts that pass boundary and failure tests; users can acknowledge and resolve them; AI only explains triggered alerts. | F-9, AC-07 |
| BAC-11 | AI integration | AI outputs are validated before persistence and do not bypass authorization or safety controls. | F-8, AC-06 |
| BAC-12 | Error handling | Expected failures produce controlled responses without exposing secrets or unnecessary medical information. | AC-09 |
| BAC-13 | Security and data protection | Sensitive records and credentials are not exposed through logs, source control, or unauthorized API responses. Uploads and database operations meet Section 8. | F-11, AC-08 |
| BAC-14 | Observability | The backend implements the logging, metrics, and health-check rules of `observability_and_reliability_spec.md`. | AC-09 |
| BAC-15 | Recovery | Job recovery and retry procedures are documented and tested. | AC-09 |
| BAC-16 | Testing | Required unit, integration, security, document-processing, and safety tests pass or have documented exceptions. | AC-10, AC-12 |
| BAC-17 | Maintainability | Responsibilities are separated into testable modules with controlled interfaces. | AC-10 |
| BAC-18 | Scope boundaries | The backend does none of the prohibited actions in Section 1.4. | AC-11 |
| BAC-19 | Document storage and access | Documents are stored per Section 6.3 and reachable only by authorized users, with access controls equivalent to the API's; storage paths and unrestricted URLs are not exposed. | F-2, F-11 |
| BAC-20 | Database | PostgreSQL is configured; schema changes follow Section 11.1. | AC-10 |
| BAC-21 | Email delivery | Account emails are sent through the replaceable email interface; failures are recorded and never reported as delivered. | F-11, AC-09 |
| BAC-22 | Export and deletion | Users can export a PDF summary, CSV/JSON data, and original documents limited to their own records, and request deletion per Section 5.5. | F-12, AC-13 |
| BAC-23 | Search | Records can be searched by document type, date, condition, provider, and extracted content; results include only the user's authorized records. | F-2 |
| BAC-24 | Suggestions | Document-derived profile values and follow-up dates are stored as suggestions per Section 5.3 and change confirmed data only after user acceptance or correction, with history preserved. | F-1, F-7, AC-02 |

Criteria are verified against implementation and test evidence. Unimplemented or unverified requirements must not be marked complete.

## 14. Specification Ownership and Change Management

### 14.1 Related Specifications

This file defines backend architecture, responsibilities, and implementation constraints. Authoritative references for other concerns:

- `goal_spec.md` — Product purpose, scope, high-level requirements, and traceability/change-management rules.
- `frontend_spec.md` — Frontend responsibilities and UI behavior.
- `DL_AI_spec.md` — AI models, techniques, prompts, evaluation.
- `observability_and_reliability_spec.md` — Logging, monitoring, reliability, recovery.
- `api_contract_spec.md` — Endpoints, schemas, status codes, error contracts.
- `data_model_spec.md` — Entities, fields, relationships, constraints.

Requirement traceability and change management follow `goal_spec.md` Section 10.

### 14.2 Implementation Readiness

Before implementing a major backend capability:

- Confirm scope and acceptance criteria.
- Identify affected modules and dependencies.
- Confirm relevant API and data-model contracts.
- Identify security and clinical-safety constraints.
- Define the tests needed to verify it.

Implementation status distinguishes specified, implemented, tested, and verified capabilities.