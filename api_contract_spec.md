# API Contract Specification
## Multimodal AI Healthcare Decision-Support System

## 1. Purpose and Ownership

This document defines the REST API contract between the frontend and backend: endpoint conventions, request and response formats, status codes, authentication requirements, error format, document-processing workflows, and versioning.

It is the source of truth for API endpoint definitions, request/response schemas, HTTP status codes, and API-level error formats. Other specifications own their own areas:

- Product goals and scope: `goal_spec.md`
- User interface and interactions: `frontend_spec.md`
- Backend implementation, data management, and security controls: `backend_spec.md`
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

Authentication endpoints and token schemas: not yet defined. They must be documented before implementation.

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

The contract must define (not yet defined):

- Upload request format.
- Accepted media types and validation behavior.
- Metadata returned after upload.
- Processing status and user-safe error details.
- Authorized retrieval or download.
- Deletion and its effect on associated extracted information.
- Processing retries, if supported.
- Pagination and filtering for document lists.

Rules:

- The original document stays distinguishable from OCR output, extracted facts, user corrections, and AI interpretations.
- Uploaded files are never publicly accessible; access is authorized independently of whether a user knows a document identifier.
- The API never exposes storage paths or requires the frontend to know whether a file is in local or object storage.

## 7. Asynchronous Processing and AI APIs

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

Exact parameter names and response schema: not yet defined.

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