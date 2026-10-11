# Frontend Specification — Multimodal AI Healthcare Decision-Support System

## 1. Purpose and Scope

Define the frontend architecture, user experience, application behavior, accessibility, and integration requirements for the healthcare decision-support system.

The frontend enables users to manage their personal health records, upload medical documents, review extracted information, track checkups and follow-ups, and access cautious AI-generated summaries.

The initial release focuses on a usable, secure core MVP. Features explicitly deferred must not be treated as initial-release requirements.

## 2. Product and UX Principles

- **User-centered:** Present health information in a clear, organized, approachable interface.
- **Privacy-first:** Show only information authorized for the authenticated user.
- **Evidence-aware:** Distinguish original medical records, extracted information, user corrections, and AI-generated interpretations.
- **Transparent AI:** Communicate processing status, uncertainty, source information, and limitations.
- **User control:** Require confirmation for uncertain or high-impact extracted information.
- **Accessible and responsive:** See Section 17.
- **Non-diagnostic:** Never present AI-generated information as a definitive medical diagnosis or substitute for professional care. Clinical boundaries are defined in `backend_spec.md` Section 1.4.

## 3. Technology and Frontend Architecture

**Framework (decided):** React single-page application built with Vite and written in TypeScript. Supporting libraries (routing, data fetching, forms, UI components) are documented when selected.

The frontend should use:

- A component-based UI architecture.
- TypeScript throughout.
- A centralized API client for backend communication.
- Shared UI components for consistent styling and behavior.
- A dedicated authentication and session-management layer.
- Structured client-side validation for forms and user input.
- Environment-based configuration for backend API URLs.
- Automated frontend testing and production-build verification.

Keep presentation, application state, API communication, and reusable business logic appropriately separated.

The frontend must not connect directly to the database or contain backend secrets, AI-provider credentials, or privileged service credentials.

## 4. Application Navigation and Layout

The authenticated application should provide the following primary sections:

1. **Dashboard**
2. **Health Timeline**
3. **Medical Documents**
4. **Medications and Prescriptions**
5. **Checkups and Follow-ups**
6. **AI Summaries and Insights**
7. **Alerts**
8. **Health Profile**
9. **Account and Privacy Settings**

Navigation should remain consistent across pages and adapt to smaller screens.

Only implement sections and actions supported by the current backend contract. If a feature is planned for a later release, clearly distinguish it from available functionality.

## 5. Authentication and Account Management

The frontend must support:

- Email and password registration, if registration is enabled.
- Email and password login.
- Logout.
- Password recovery through email.
- Password-reset workflows.
- Clear authentication and session-expiration feedback.
- Protected routes for authenticated users.
- Appropriate handling of expired or invalid sessions.

Session credentials follow `api_contract_spec.md` Section 5.1:

- Keep the access token in memory only (never `localStorage` or `sessionStorage`) and send it as `Authorization: Bearer <token>`.
- The refresh token lives in a `Secure`, `HttpOnly` cookie set by the backend; frontend code never reads it.
- On page reload or access-token expiry, obtain a new access token through the refresh endpoint; if refresh fails, return the user to login.

Do not expose passwords, tokens, or other secrets in URLs, logs, error messages, or browser-visible application configuration.

After logout or session expiration, protected health information must no longer remain accessible through the application's active authenticated state.

## 6. Dashboard

The dashboard provides a concise overview of the user's health-record activity.

It should include:

- Health profile completeness or availability.
- Recently uploaded medical reports.
- Document-processing status.
- Upcoming and overdue checkups and follow-ups.
- Open safety alerts, with urgent alerts shown prominently.
- Relevant health-record summaries, where available.
- Items requiring user review.
- Clear navigation to the corresponding detailed sections.

Dashboard information must be based on authorized backend data. Empty states should explain how users can get started.

The dashboard must not fabricate health metrics, imply that missing information indicates good health, or display unverified AI interpretations as confirmed facts.

## 7. Health Timeline and Record Organization

The primary health-record view must present records chronologically, with category filters and search.

Search (`api_contract_spec.md` Section 9.1) lets users find records by document type, date range, condition, provider, and free text in extracted content. Results show the record type, date, and source document, and open the matching record. Search text must not be placed in the page URL.

Supported record categories may include:

- Laboratory reports and results.
- Recorded vital signs.
- Medications and prescriptions.
- Checkups and follow-ups.
- Medical documents.
- Relevant user-confirmed health information.

Each record should display available information such as its date, category, source, and verification status.

Users must be able to open a record to inspect its details and source document where authorized.

The interface must distinguish:

- Information taken directly from an original document.
- AI-extracted information that has not been confirmed.
- User-confirmed information.
- User corrections.
- AI-generated summaries and interpretations.

Records from different dates must not be merged or treated as comparable without appropriate context.

## 8. Health Profile

Users must be able to enter and update their own health-profile information manually.

Where appropriate, the system may suggest profile information extracted from uploaded documents. Suggested information must be presented for user confirmation before being treated as confirmed profile data.

The interface must:

- Clearly identify suggested versus confirmed values.
- Allow users to accept, reject, or correct suggestions.
- Validate input and explain validation errors.
- Preserve source and correction provenance through backend-supported workflows.
- Avoid silently replacing existing values with extracted information.

Only the authenticated account holder's own health profile is in scope for the initial release.

## 9. Medical Document Management

The initial release must support uploading PDF, JPEG, and PNG medical documents, including scanned reports.

The document interface must support:

- File selection and upload.
- Clear upload progress and completion feedback.
- File type and size validation (20 MB limit, `api_contract_spec.md` Section 6.1), checked before upload.
- Duplicate or conflicting-document feedback where supported.
- Document lists with relevant metadata.
- Document details and authorized original-file viewing or downloading.
- Processing status and extraction results.
- User-initiated retry after eligible failures.
- Document deletion when authorized.

The frontend must not assume that a successful upload means extraction has completed successfully.

Document-processing states match `api_contract_spec.md` Section 7:

- `pending`
- `running`
- `completed`
- `completed_with_warnings` (partial results; show what needs review)
- `failed`
- `cancelled`, if supported

User-facing labels may be friendlier (e.g., "Processing" for `running`), but each label maps to exactly one state.

Failed processing must not cause the original uploaded document to disappear. Error messages should explain the issue without exposing internal paths, stack traces, secrets, or sensitive implementation details.

## 10. Extracted Information and Review

The frontend must provide a review workflow for information extracted from medical documents.

Each extracted item should display available source information, relevant dates, and its confirmation status.

The interface must:

- Clearly distinguish unconfirmed extraction results from user-confirmed records.
- Highlight uncertain or potentially high-impact information for review.
- Allow users to confirm, correct, or reject extracted values where supported.
- Display conflicting source values without silently choosing a winner.
- Preserve the original document and extraction history.
- Record user corrections separately with provenance.
- Explain when an item could not be extracted reliably.

Structurally valid routine extractions may be saved as unconfirmed. The frontend must not imply that structural validity proves medical correctness.

The user must be able to review and correct supported information without modifying the original uploaded document.

## 11. AI Summaries and Insights

The frontend may display AI-generated summaries of available personal health records.

Initial capabilities include:

- Plain-language summaries of uploaded records.
- Explanations of extracted medical information.
- Cautious, evidence-grounded insights based on available records.
- Explanations of results flagged as outside the reference range stated in the report. The flag itself comes from a validated rule; the AI only explains it (`DL_AI_spec.md` Section 9.1).
- Clear indications of missing, conflicting, or uncertain information.

Trend analysis and Health Q&A are deferred (Section 20).

AI-generated content must:

- Be visibly identified as AI-generated.
- Present supporting record references where available.
- Communicate uncertainty and relevant limitations.
- Distinguish reported facts from interpretations.
- Avoid definitive diagnoses or unsupported conclusions.
- Never recommend independently starting, stopping, or changing medication.
- Never replace professional medical evaluation or emergency services.

Statements about the user's health come only from the user's authorized records. Explanations of medical terms may use general medical knowledge (`DL_AI_spec.md` Section 6.1); the interface must label them as general information, not from the user's records, and show a note that a doctor's advice is needed.

If there is insufficient information, the interface should state that clearly rather than manufacture a conclusion.

## 12. Medications, Prescriptions, Checkups, and Follow-ups

### 12.1 Medications and Prescriptions

Users must be able to add, edit, and view medication and prescription records, including those derived from authorized documents, and see each record's change history.

The interface must distinguish prescribed information from AI interpretation and unconfirmed extraction results.

Medication reminders are out of scope (Section 20).

### 12.2 Checkups and Follow-ups

Users must be able to record checkup and follow-up dates manually.

Where supported, the system may suggest dates extracted from uploaded records. Suggested dates must be confirmed by the user before being treated as confirmed entries.

The interface should display upcoming, overdue, and past dates clearly. Automated reminder delivery is deferred (Section 20).

## 13. Notifications and Safety Messages

The frontend must display relevant status messages, processing failures, review requests, and supported safety alerts.

Potentially abnormal results must be presented as items for review, not automatic diagnoses.

Safety-related messaging must:

- Use clear, calm, non-alarmist language.
- Identify the relevant source record where available.
- Explain uncertainty and limitations.
- Avoid claiming that the absence of an alert means the user is healthy.
- Direct users to appropriate professional or emergency assistance when warranted.

The frontend must not rely on an AI-generated message as the sole mechanism for handling a medical emergency.

### 13.1 Alerts Section

The Alerts section lists the user's safety alerts from the backend. Each alert shows:

- Severity, creation date, and status (open, acknowledged, resolved).
- The rule-based reason and the related source records.
- Recommended next steps, and any AI explanation clearly labelled as such.

Users can acknowledge and resolve alerts. Urgent alerts are shown prominently (e.g., on the dashboard) without waiting for AI analysis. Resolving an alert must not be presented as confirmation that the user is healthy.

## 14. API Integration and State Management

All persisted health information must be retrieved from or submitted to the backend through the documented REST API contract.

The frontend must:

- Use the agreed `/api/v1` API base path.
- Follow documented request and response schemas.
- Handle authentication and authorization failures.
- Handle validation errors, missing resources, conflicts, rate limits, and server failures.
- Respect asynchronous processing responses, including HTTP `202 Accepted`.
- Poll or refresh processing status according to the agreed API design.
- Prevent accidental duplicate submissions where appropriate.
- Display loading, success, empty, and failure states.
- Avoid displaying stale data as newly processed information.

The frontend must not invent API endpoints or rely on undocumented response fields. API changes must be coordinated with `api_contract_spec.md` and `backend_spec.md`.

## 15. Privacy and Security

The frontend must enforce privacy-conscious interaction patterns while relying on the backend for authoritative access control.

Requirements include:

- Access only the authenticated user's authorized records.
- Avoid exposing sensitive information in URLs, analytics, logs, or client-side error reports (`observability_and_reliability_spec.md` Section 4.2).
- Avoid placing secrets or privileged credentials in frontend bundles.
- Validate user input and uploaded-file metadata.
- Render user-provided and AI-generated text safely.
- Avoid unsafe HTML rendering and cross-site scripting vulnerabilities.
- Use HTTPS in deployed environments.
- Apply appropriate browser security headers through the deployment configuration.
- Avoid unnecessary caching of sensitive health information.
- Clear sensitive client-side state on logout and account changes.
- Provide confirmation for destructive operations.
- Display clear outcomes for deletion and export requests.

The frontend must not treat hidden controls or client-side checks as substitutes for backend authorization.

## 16. Export and Deletion

### 16.1 Health Record Export

The initial release should support:

- A readable PDF health summary.
- Structured CSV and/or JSON exports as specified by the API contract.
- Separate downloading of original documents.

Exports must be limited to records authorized for the current user. The interface must explain the export scope and provide clear success or failure feedback.

The backend is responsible for generating and authorizing export content.

### 16.2 Record and Account Deletion

Users must be able to delete eligible records and documents where supported.

Account deletion must clearly explain its consequences and require deliberate confirmation.

The interface must communicate that eligible active data is deleted according to the system's deletion policy, while backup copies may persist until they expire under the documented retention policy, subject to applicable legal requirements.

The frontend must not claim that every backup copy is immediately erased unless the backend can verify that outcome.

## 17. Accessibility, Responsiveness, and Usability

The interface should follow recognized accessibility practices, including WCAG 2.2 AA as the target where practical.

Requirements include:

- Semantic page structure and accessible labels.
- Keyboard-accessible navigation and forms.
- Visible focus indicators.
- Sufficient text and interface contrast.
- Appropriate screen-reader announcements for status changes.
- Clear error descriptions and correction guidance.
- Responsive layouts for desktop, tablet, and mobile.
- Readable date, number, and measurement presentation.
- Consistent terminology for processing and confirmation states.

Color must not be the only indicator of a health status or processing outcome.

The initial user interface language is English. The architecture should avoid unnecessary assumptions that would prevent future localization.

## 18. Testing and Quality Assurance

Frontend verification must cover:

- Component and unit tests for important UI logic.
- Authentication, logout, and session-expiration behavior.
- Form validation and accessible error handling.
- Document upload and processing-state transitions.
- Extraction review, confirmation, and correction workflows.
- Health timeline filtering, search, and navigation.
- Profile and follow-up suggestion accept, correct, and reject flows.
- API error handling and authorization boundaries.
- Summary, export, and deletion workflows where implemented.
- Responsive layouts and accessibility-critical interactions.
- Regression testing for meaningful frontend changes.

Test data follows `backend_spec.md` Section 2.4 (synthetic or de-identified only). Tests must not depend on real patient information or expose sensitive records in test output.

## 19. Frontend Acceptance Criteria

| # | Criterion | Goal ref |
|---|-----------|----------|
| FE-AC-01 | Users can register, log in, log out, and reset a password via email; the access token is held in memory and the refresh token only in an `HttpOnly` cookie. | F-11 |
| FE-AC-02 | The dashboard displays authorized health overview information, recent reports, processing status, upcoming/overdue follow-ups, and urgent alerts where data exists. | UC-6 |
| FE-AC-03 | Users can browse a chronological health timeline, filter by category, and search by document type, date, condition, provider, and extracted content. | F-2, F-6, AC-04 |
| FE-AC-04 | Users can upload supported PDF, JPEG, and PNG documents and see upload and processing status using the contract's state values. | F-2, F-3, AC-01 |
| FE-AC-05 | Original documents remain available after extraction failures, subject to the applicable retention and deletion policy. | AC-01 |
| FE-AC-06 | Extracted information is visibly distinguished from confirmed information. | F-3, AC-02 |
| FE-AC-07 | Users can review, confirm, correct, or reject supported extracted information. | F-3, AC-02 |
| FE-AC-08 | Conflicting information and uncertain AI outputs are presented transparently. | F-10 |
| FE-AC-09 | AI summaries identify their AI-generated nature and communicate relevant evidence and uncertainty; general-knowledge explanations are labelled and show the doctor's-advice note. | F-8, AC-06 |
| FE-AC-10 | Users can add, edit, and view medication and prescription records with change history; no medication reminders are offered. | F-5, AC-03 |
| FE-AC-11 | Users can record checkup and follow-up dates manually, confirm document-derived suggestions, and see upcoming and overdue items. | F-7, AC-05 |
| FE-AC-12 | Users can export a PDF summary and CSV/JSON data, and download original documents separately. | F-12, AC-13 |
| FE-AC-13 | Eligible record and account deletion workflows provide clear confirmation and outcome feedback. | F-12, AC-13 |
| FE-AC-14 | Protected health information is not exposed through unauthorized frontend access or unsafe rendering. | F-11, AC-08 |
| FE-AC-15 | Core frontend workflows are covered by automated tests and pass the agreed build and verification checks. | AC-10 |
| FE-AC-16 | The interface is usable across supported screen sizes and meets agreed accessibility requirements. | Cross-cutting (usability) |
| FE-AC-17 | Users can view, acknowledge, and resolve safety alerts; each alert shows its rule-based reason and source records. | F-9, AC-07 |

## 20. Constraints and Deferred Features

The initial release does not include:

- Multiple patient profiles under one account.
- Caregiver or clinician access.
- Medication-taking reminders and prescription-renewal reminders (out of scope, `goal_spec.md` Section 7).
- Automated checkup/follow-up reminder delivery through email, push, or other channels.
- Lab-result and vital-sign trend analysis.
- Health Q&A over the user's records.
- Multilingual UI.
- Autonomous diagnosis, prescribing, or medication changes.
- AI-only emergency detection or response.

Future capabilities must be introduced through an explicit scope decision and coordinated changes to the relevant specifications.

## 21. Specification Ownership and Change Management

This specification defines frontend responsibilities and expected behavior.

- `goal_spec.md` defines the overall product goals and scope.
- `backend_spec.md` defines backend architecture and business services.
- `api_contract_spec.md` defines API resources, schemas, and interactions.
- `DL_AI_spec.md` defines AI processing and safety behavior.
- `observability_and_reliability_spec.md` defines monitoring, recovery, reliability, and the sensitive-data logging rule.

Requirement traceability and change management follow `goal_spec.md` Section 10. Conflicts between specifications are reconciled explicitly before implementation. Changes affecting shared workflows must be reviewed across the relevant specifications. Acceptance criteria and API dependencies must remain consistent as the system evolves.