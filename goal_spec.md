# Goal Specification — Multimodal AI Healthcare Decision-Support System

## 1. Project Overview

A centralized platform for individuals to store, organize, and understand their own medical history. It manages medical records, reports, prescriptions, medications, checkups, and follow-ups, and uses AI to extract information from documents, summarize history, track checkups and follow-ups, and raise rule-based safety alerts.

It provides informational decision support only and does not replace professional diagnosis, treatment, or emergency care.

## 2. Problem Statement

- Medical records are scattered across hospitals, labs, and clinics, in mixed formats (paper, PDFs, scans, images, digital prescriptions).
- Tracking health changes requires manually comparing multiple reports across dates.
- Historical information, result changes, and pending follow-ups get overlooked.
- People with chronic or complex conditions must manage ongoing medications, investigations, and appointments.
- Existing methods give no unified view and don't flag missing records, measurement changes, or when medical review is needed.

## 3. Target Users

**Primary:** Individuals managing their own health records, including those:
- Doing routine annual checkups.
- Managing chronic conditions (e.g., diabetes, heart disease).
- Needing long-term monitoring after major procedures (e.g., kidney transplant).
- Handling multiple prescriptions, investigations, and specialists.

**Future:** Authorized caregivers and healthcare professionals (see Section 6).

## 4. Core Use Cases

| # | Use Case | Description |
|---|----------|-------------|
| UC-1 | Record management | Upload a report, prescription, or discharge summary; the system stores the original, categorizes it, and extracts supported data. |
| UC-2 | History review | View reports, prescriptions, diagnoses, and investigations chronologically across years. |
| UC-3 | Trend comparison | *Deferred (Section 6).* Compare current vs. past lab values, preserving units and dates, with significance explained within available evidence. |
| UC-4 | Medication tracking | Record and edit a medicine and instructions; keep a history of changes. |
| UC-5 | Preventive care | Record a follow-up/checkup schedule; see upcoming and overdue items in the app. Automated reminder delivery is deferred (Section 6). |
| UC-6 | Chronic-care monitoring | Consolidated history with missing information and items needing review highlighted. |
| UC-7 | Health Q&A | *Deferred (Section 6).* Ask about documented history; get a source-backed answer that states uncertainty. |
| UC-8 | Urgent situations | A validated safety rule triggers guidance, directing to urgent/emergency care when warranted. |

Use-case IDs are stable; deferred use cases keep their IDs for traceability.

## 5. Feature Implementation

### F-1: Health Profile
Demographics, conditions, allergies, medical history, and other user-provided health information. Values suggested from documents become profile data only after the user accepts or corrects them.

### F-2: Medical Record Management
- Upload, categorize, view, search, and retrieve documents.
- Originals are preserved and never silently overwritten.
- Search by document type, date, condition, provider, and extracted content.
- Failed uploads are clearly reported.

### F-3: Multimodal Document Processing
- Supports PDFs, scanned documents, and images.
- Extracted data keeps source reference, date, and unit where available.
- Incomplete or uncertain extraction is explicitly flagged.

### F-4: Structured Health Observations
Stores values, units, dates, reference ranges, and source documents, whether extracted or user-entered.

### F-5: Medication and Prescription Management
- Records name, dosage, frequency, treatment period, prescriber, and status.
- Maintains full medication change history.

### F-6: Longitudinal Tracking
- Chronological view of observations.
- Records from different dates are never silently merged or mixed across incompatible units, reference ranges, or contexts.
- Cross-date comparison and trend analysis are deferred (Section 6).

### F-7: Follow-up and Checkup Tracking
- Records checkups, investigations, and appointments.
- Upcoming and overdue items are shown in the app.
- Automated reminder delivery (email, push, or other channels) is deferred (Section 6).

### F-8: AI Summaries
- Summaries grounded only in the user's authorized records.
- Cite source records where possible.
- Distinguish recorded facts from AI interpretation.
- Disclose uncertainty and missing information.
- Explanations of medical terms may use general medical knowledge, labelled as general information (not from the user's records) and accompanied by a note that a doctor's advice is needed.
- Health Q&A is deferred (Section 6).

### F-9: Safety Alerts
- Based on predefined rules and validated criteria; AI may explain a triggered alert but does not decide it.
- Includes flagging results outside the reference ranges stated in the source report, as items for review.
- Each alert documents trigger criteria, severity, next steps, and escalation path.
- Users can view, acknowledge, and resolve alerts.
- Urgent guidance does not depend solely on generative AI or on external AI availability, and is shown without waiting for AI analysis.

### F-10: Data Completeness
Flags missing, outdated, unreadable, or conflicting information where determinable from data and configured rules.

### F-11: Privacy, Security, and Access Control
- Users access only their own authorized data.
- Authentication, authorization, encryption in transit and at rest, secure secret management.
- Sensitive access and significant changes are controlled and auditable.
- Minimal data collection; no unauthorized use of records for AI processing.
- Sensitive data not unnecessarily exposed in logs, AI requests, or storage.

### F-12: Data Export and Deletion
Users can export data and request deletion, subject to retention requirements and documented policies. Export formats: a readable PDF health summary, structured CSV/JSON data, and separate download of original documents.

### Cross-Cutting Quality Requirements
- **Data integrity:** Original records, extracted information, and AI interpretations remain distinct, with traceability between originals, extracted data, corrections, and processing history.
- **Reliability:** Failures in processing, AI, external services, jobs, or notifications are handled gracefully and never silently lose records or mark incomplete work as successful.
- **Recoverability:** Defined backup, recovery, and retry procedures.
- **Usability/accessibility:** Clear presentation; alerts, uncertainty, and required actions visually distinct from general info.
- **Scalability:** Supports growth in users, documents, and AI workload without redesign.
- **Maintainability:** Modular components, documented interfaces/API contracts, automated tests, version-controlled specs.
- **Interoperability:** Consistent, documented data structures for future healthcare-standard integration.
- **Configurability:** Reminder schedules, document types, and alert rules configurable without touching unrelated components.

## 6. Future Expansion

Not part of the initial version:

- Cross-date measurement comparison and trend analysis (UC-3).
- Health Q&A over the user's records (UC-7).
- Automated checkup/follow-up reminder delivery through email, push, or other channels.
- Dedicated operational alerting.
- Caregiver and healthcare-professional access and portals (with access controls and consent).
- Integration with hospital information systems / EHR platforms.
- Wearable and continuous-monitoring device data.
- Additional medical conditions, document types, and AI capabilities.

Additions must not compromise data integrity, privacy, security, or clinical safety, and must not require full redesign.

## 7. Out of Scope

- Medication-taking reminders and prescription-renewal reminders.
- Autonomous diagnosis, prescription generation, or treatment changes.
- Independent interpretation of raw medical imaging without validation; image analysis is limited to supported modalities and validated use cases.
- Automatic emergency-service dispatch without a separately validated, authorized workflow.

## 8. Success Metrics

Numerical targets for these metrics will be set after initial requirements analysis and baseline testing.

### 8.1 Metrics

| Area | Metrics |
|------|---------|
| Record management | Upload/retrieval success rate by document type; metadata completeness and correctness; processing-failure and data-loss rate. |
| AI extraction | Accuracy of values, units, dates, and medication details; rate of incorrect/unsupported extractions; % of uncertain extractions correctly flagged. |
| Health analysis | Accuracy of source references in summaries; rate of unsupported clinical statements; performance on independently reviewed evaluation datasets; correctness of longitudinal comparisons (once introduced). |
| Follow-ups and alerts | Accuracy of upcoming/overdue follow-up status; detection rate for configured alert scenarios; false-positive and false-negative rates; notification delivery rate (once reminder delivery is introduced). |
| Security and reliability | Access-control and data-isolation test results; count/severity of unresolved security defects; availability and recovery vs. service targets; successful backup restores in controlled tests. |
| User experience | Ease of uploading and retrieving records; understanding of summaries and alert instructions; ability to identify upcoming and overdue activities. |

Clinical AI capabilities, alerts, and AI health interpretations require separate evaluation against reference data and qualified clinical review before justifying real-world clinical reliance.

### 8.2 Acceptance Criteria

Release readiness is determined by these acceptance criteria:

| # | Criterion |
|---|-----------|
| AC-01 | Documents upload, retrieve, and show metadata; failures reported; originals not overwritten. |
| AC-02 | Extracted data retains available source, date, and unit; uncertainty flagged. |
| AC-03 | Medications can be recorded, edited, and reviewed, with change history. |
| AC-04 | Timeline shows observations chronologically without merging or mixing incompatible units/contexts. |
| AC-05 | Checkups and follow-ups can be recorded; upcoming and overdue items are shown correctly. |
| AC-06 | Summaries cite sources where possible, separate fact from interpretation, and disclose uncertainty; general-knowledge explanations are labelled and advise consulting a doctor. |
| AC-07 | Test scenarios trigger expected alerts; urgent flows don't depend solely on generative AI; tested for missed alerts and false alarms; users can acknowledge and resolve alerts. |
| AC-08 | Automated tests confirm no cross-user data access or modification; sensitive data not unnecessarily exposed in logs. |
| AC-09 | Failures in AI, storage, jobs, and email delivery are observable and handled per recovery policy. |
| AC-10 | Core requirements have tests; API contracts documented; changes don't break unrelated components. |
| AC-11 | System does not autonomously diagnose, modify treatment, or declare a person medically fit based solely on its analysis. |
| AC-12 | All mandatory requirements implemented and verified; limitations, defects, evaluation results, and operational needs documented. |
| AC-13 | Users can export a PDF summary, CSV/JSON data, and original documents, and request deletion per policy. |

## 9. Constraints and Assumptions

### 9.1 Constraints

- AI observations must not be presented as confirmed diagnoses or treated as verified clinical facts without validation.
- Must not declare a person fit or disease-free based solely on records or AI analysis.
- Users are advised to seek professional or emergency care when indicated.
- Clinical thresholds, condition-specific rules, and recommendations must come from validated sources and be reviewed for intended use. The application must not invent them.
- Deployment and data handling must comply with applicable legal, privacy, and security requirements.

### 9.2 Assumptions

- Users are responsible for providing accurate information and reviewing extracted data when requested.
- Documents vary in quality, structure, language, completeness, and readability; some will need manual correction after extraction.
- Availability of reference ranges, historical measurements, and clinical context varies.
- AI models and external services may err, become unavailable, or change over time.
- Medical histories may be incomplete. The absence of a recorded condition or alert is not proof of no health risk.

## 10. Planning and Observability

**Observability:**
- Logging, metrics, health monitoring, and error reporting. Dedicated operational alerting is deferred (Section 6).
- Long-running document/AI processing shows status to the user.
- Details are owned by `observability_and_reliability_spec.md`.

**Planning:**
- Measurable performance targets to be defined during technical design.
- Requirements must be verifiable via automated, integration, and security tests and controlled evaluations.
- Timeline, milestones, and resourcing: Needs to be added later.

**Traceability and change management:**
- Each major requirement has a unique ID. Frontend, backend, AI, observability, and API specs reference these IDs.
- Requirements are linked to acceptance criteria and tests.
- Changes are documented before implementation and reviewed for impact on specs, interfaces, data models, security controls, and tests.
- Conflicts between specs are resolved explicitly, not left to individual components.
- Each topic has one owning spec; other specs reference it instead of restating it.
- Component acceptance-criteria tables include a "Goal ref" column linking each criterion to the F-, UC-, or AC- IDs it supports.
- Unimplemented or unverified requirements are not reported as complete.
- This document is the product-level reference. Component-level details live in their own spec files.