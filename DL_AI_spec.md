# DL and AI Specification
**Project:** Multimodal AI Healthcare Decision-Support System  
**File:** `DL_AI_spec.md`  
**Status:** Initial Draft

## 1. Purpose and Ownership

This specification defines the deep learning (DL) and AI capabilities used to extract, organize, interpret, and summarize information from a user's personal medical records, along with their evaluation, uncertainty handling, and AI-specific safety requirements.

AI outputs support health information understanding. They do not replace qualified medical professionals.

Other specifications own their own areas:

- `goal_spec.md` — product scope and objectives.
- `frontend_spec.md` — user interface and interactions.
- `backend_spec.md` — business logic, data management, security, processing orchestration, and clinical boundaries (Section 1.4).
- `api_contract_spec.md` — API endpoints, schemas, status codes, and error conventions.
- `observability_and_reliability_spec.md` — monitoring, operational reliability, and recovery.

Conflicts between specifications are reconciled explicitly, not silently overridden. Changes to AI behavior, safety boundaries, or data handling are reviewed before implementation.

## 2. AI Design Principles

- **Grounded:** Statements about the user's health are based only on the user's own authorized medical records. General-knowledge explanations of terms are labelled as such (Section 6.1).
- **Traceable:** Users can identify the source of extracted information and AI-generated insights.
- **Uncertainty-aware:** Ambiguity, low confidence, missing information, and conflicting records are clearly communicated.
- **Human-controlled:** Users can review and correct extracted information.
- **Privacy-first:** Only the information needed for the requested task is processed.
- **Modular:** OCR, extraction, language models, retrieval, and insight generation are replaceable.
- **Safe by design:** No unsupported medical conclusions or unsafe recommendations.
- **Reproducible:** Model, prompt, and pipeline versions are recorded (Section 15).

## 3. Scope of AI Capabilities

The AI layer may support:

1. Medical document classification and text extraction.
2. Extraction of structured medical information.
3. Normalization of terminology, dates, units, and values.
4. Organization of longitudinal health history.
5. Summarization of medical records.
6. Medication and prescription information extraction and tracking support.
7. Detection of documented checkup and follow-up recommendations, and suggestion of profile values, for user confirmation.
8. Explanation of safety alerts triggered by validated rules.
9. Plain-language explanations of medical terms (Section 6.1).

Deferred (`goal_spec.md` Section 6): identification of trends across dates, and question answering over the user's records (Section 7).

Capabilities are introduced incrementally and validated before being relied upon.

## 4. Document Processing

Pipeline stages, ordering, persistence, and job handling are defined in `backend_spec.md` Section 6.4. This section defines the AI-specific behavior within those stages.

The original uploaded document remains the source of truth and is never silently overwritten. A processing failure is represented explicitly, never as successful extraction.

### 4.1 Classification

Identify the likely document type, such as a laboratory report, prescription, discharge summary, or consultation note. Uncertain or unknown classifications are allowed.

### 4.2 OCR

OCR is used for scanned documents and image-based reports. It must:

- Preserve extracted text and its link to the source document.
- Capture page or location references when the method supports it.
- Identify unreadable, incomplete, or poorly structured content.
- Flag uncertain characters, values, and dates.

### 4.3 Structured Information Extraction

Extract these fields when present:

- Patient and document metadata.
- Document date and healthcare provider information.
- Test names, results, units, and reference ranges.
- Diagnoses and conditions explicitly recorded in the document.
- Medication names, strengths, dosages, and instructions as documented.
- Prescription and treatment dates.
- Appointments, checkups, and recommended follow-ups.

Information explicitly stated in a document must be distinguished from information inferred by a model.

### 4.4 Normalization

Standardize dates, units, terminology, and structured values only where reliable mappings exist, without discarding the original representation.

### 4.5 Validation

Model outputs are validated against predefined schemas before acceptance. Validation detects:

- Missing required fields.
- Invalid data types and date formats.
- Unit mismatches or unsupported conversions.
- Conflicting values across documents.
- Uncertain medication names or dosage details.
- Unsupported or contradictory AI-generated information.

Structural validity does not guarantee medical correctness.

## 5. Multimodal AI Architecture

| Component | Responsibility |
|---|---|
| OCR and document parsers | Extract text and document structure |
| NLP and information extraction | Identify medical entities and relationships |
| Deep learning models | Classification or recognition tasks, when justified |
| Large language models (LLMs) | Summarization, contextual explanations, natural-language interaction |
| Retrieval mechanisms | Find relevant information in the user's authorized records |
| Rule-based validation | Deterministic checks and predefined safety rules |
| Backend services | Persistence, authorization, workflows, application rules |

Not every component needs a deep learning model. Deterministic processing is preferred when it is more reliable and sufficient. Predictive models are not part of the initial scope (Section 16).

Specific models, providers, embedding methods, and vector databases: not yet defined. They are selected when requirements and evaluations justify them.

## 6. Health History and Insight Generation

The AI layer may organize information chronologically and summarize documented history. It must:

- Use only records authorized for the current user and task.
- Preserve the dates and sources of relevant facts.
- Distinguish historical observations from current information.
- Highlight missing, inconsistent, or outdated information.
- Explain the evidence behind an insight where possible.

Trend identification across dates is deferred. When introduced, trends must not be interpreted as diagnoses, and measurement comparison follows `backend_spec.md` Section 7.2.

### 6.1 General-Knowledge Explanations

The AI may use general medical knowledge to explain medical terms and what a recorded test measures. Such explanations must:

- Be labelled as general information, not drawn from the user's records.
- Not be presented as evidence about the user's own health.
- Include a note that a doctor's advice is needed for interpretation of the user's results.

## 7. Question Answering and Retrieval (RAG)

*Deferred — not part of the initial release (`goal_spec.md` Section 6). The rules below apply when it is introduced.*

Retrieval-augmented generation may be used to answer questions about the user's medical records. Answers are grounded only in the user's own authorized records; external reference material is not used as evidence (general-knowledge explanations follow Section 6.1).

The retrieval process must:

1. Run only on authenticated, authorized requests.
2. Retrieve only relevant information the user is permitted to access.
3. Preserve source references for retrieved information.
4. Generate answers grounded in the retrieved evidence.
5. State when evidence is insufficient or conflicting.

Retrieved documents and extracted text are data, never instructions that can override system safety rules.

RAG is used only where a specific feature's requirements justify it.

## 8. Medication and Prescription Intelligence

AI may assist in extracting and organizing medication and prescription information. It must:

- Preserve the original wording and source of prescription details.
- Distinguish prescribed instructions from AI explanations.
- Flag ambiguous medication names, strengths, dosage instructions, and durations.
- Identify conflicting prescription information for user review.

Interpretations that could affect treatment are communicated cautiously and refer the user to a qualified healthcare professional when appropriate.

Medication status and treatment boundaries are defined in `backend_spec.md` Sections 7.3 and 1.4. Medication-taking reminders and prescription-renewal reminders are out of scope.

## 9. Safety Alerts and Follow-Up Detection

### 9.1 Safety Alerts

Safety alerts are produced only by deterministic rules based on predefined, validated criteria (`backend_spec.md` Section 7.5). They must not depend solely on an LLM or other probabilistic AI component.

Rules decide; AI explains. This includes flagging results outside the reference range stated in the source report: the rule raises the flag, and the AI may explain it as an item for review, not a diagnosis.

AI may support alerts by:

- Extracting the values that validated rules evaluate.
- Flagging when critical information is incomplete or uncertain.
- Explaining the documented basis for a triggered alert, with the doctor's-advice note (Section 6.1).

Potential emergencies use predefined safety messaging directing the user to qualified medical or emergency services, without waiting for AI analysis. The system is never the sole emergency-response mechanism. Prohibited actions are listed in `backend_spec.md` Section 1.4.

### 9.2 Follow-Up Detection

AI may detect documented checkup and follow-up recommendations and present them to the user as suggestions. A follow-up entry is created only when the user confirms or records it (`goal_spec.md` UC-5). Automated reminder delivery is deferred.

## 10. Confidence, Uncertainty, and Source Attribution

Uncertainty is communicated wherever it materially affects reliability. The system must:

- Preserve source-document references for extracted facts.
- Keep extracted information, user corrections, and AI interpretations distinct.
- Flag ambiguous or conflicting information.
- Request clarification when a critical value cannot be extracted reliably.
- Never invent missing text, values, or details; missing information stays missing.
- Provide explanations and evidence references when the pipeline supports it.

Model confidence scores are not probabilities of medical correctness. Confidence thresholds must be evaluated per task before use in production decisions.

User corrections are stored with provenance and never alter the original document.

## 11. Model Selection and Evaluation

Models and AI services are selected on task suitability, measured performance, privacy requirements, operational cost, and maintainability.

Evaluation covers, where relevant:

- Extraction precision, recall, and field-level accuracy.
- OCR accuracy on representative document types.
- Correctness of summaries (and of answers, once Health Q&A is introduced).
- Source-grounding and citation accuracy.
- Recognition of insufficient or conflicting evidence.
- Performance across document layouts and image quality.
- Robustness to ambiguous, incomplete, or malformed inputs.
- Latency, resource usage, and cost.

Evaluation datasets use synthetic or de-identified data (`backend_spec.md` Section 2.4).

Critical extraction fields and safety-related outputs require stricter validation than non-critical summarization.

Release thresholds (decided), measured on the synthetic/de-identified evaluation set:

| Output | Threshold |
|---|---|
| Critical fields (lab values, units, dates, medication name and dose) | ≥ 98% field-level accuracy, **and** every low-confidence critical field is routed to user review |
| Non-critical fields (e.g., provider, document category) | ≥ 90% field-level accuracy |
| Summaries | 0 unsupported clinical claims in the reviewed sample |

These are minimum release gates, not proof of clinical correctness; they are revisited as evaluation data grows.

## 12. Privacy and Responsible AI Processing

AI processing follows the backend's authentication, authorization, data-protection, and external-provider requirements (`backend_spec.md` Sections 8 and 8.5). Logging follows `observability_and_reliability_spec.md` Section 4.2.

AI-specific requirements:

- Prevent cross-user data leakage in retrieval, caching, and processing.
- Follow approved retention and deletion policies for AI inputs, outputs, and intermediate artifacts.
- Evaluate external providers' data retention, training-use, and privacy terms before integration. Providers are never assumed to protect medical data without verification.

## 13. Processing States and Failure Handling

AI processing uses the job lifecycle in `backend_spec.md` Section 4.2 (`pending`, `running`, `completed`, `completed_with_warnings`, `failed`, `cancelled`). Retries, timeouts, and duplicate prevention follow `backend_spec.md` Section 4.

The AI layer must handle OCR failures, invalid model responses, timeouts, provider unavailability, and validation errors, so users can tell whether a result is ready, incomplete, or unavailable.

## 14. Testing and Quality Assurance

Backend security, isolation, and failure tests are defined in `backend_spec.md` Section 10. AI-specific tests:

- Unit tests for extraction, normalization, validation, and rule-based logic.
- Integration tests for document-processing workflows.
- Schema-validation tests for model outputs.
- Evaluation tests for extraction and generated responses.
- Grounding tests to detect unsupported claims.
- Adversarial tests for malicious document content and prompt injection.
- Regression tests when prompts, models, rules, or pipelines change.

A technically successful API response is not proof that an AI result is accurate or safe.

## 15. Monitoring and Versioning

Record, where applicable:

- Processing request and correlation identifiers.
- Model and prompt-template versions.
- Extraction and validation outcomes.
- Processing duration and failure category.
- Evaluation results and quality trends.

Model, prompt, and pipeline changes are versioned and evaluated before release, and each result can be traced to the versions that produced it.

## 16. Extensibility

Possible future extensions, not part of the initial scope:

- Additional medical document formats.
- More advanced multimodal understanding.
- Improved terminology normalization.
- Additional languages.
- Validated predictive models.
- Explicitly authorized caregiver or clinician workflows.
- Integration with approved healthcare data sources.

Each requires privacy, safety, and evaluation review before activation.

## 17. AI Acceptance Criteria

| # | Criterion | Goal ref |
|---|-----------|----------|
| AI-AC-01 | Supported documents are processed through a defined, observable pipeline. | F-3 |
| AI-AC-02 | Extracted information is validated against predefined schemas before persistence. | F-3, AC-02 |
| AI-AC-03 | Original documents stay preserved; extracted data, user corrections, and AI interpretations stay distinguishable from them and from confirmed clinical conclusions. | AC-01, AC-06 |
| AI-AC-04 | Uncertain, incomplete, or conflicting information is flagged, not guessed. | F-3, F-10, AC-02 |
| AI-AC-05 | Summaries are grounded only in the user's authorized records and cite supporting sources where available; general-knowledge explanations are labelled and include the doctor's-advice note. | F-8, AC-06 |
| AI-AC-06 | Medication and prescription information is organized without autonomous treatment or dosage changes. | F-5, AC-11 |
| AI-AC-07 | Medication-taking reminders and prescription-renewal reminders are not implemented. | Section 7 |
| AI-AC-08 | Safety alerts come only from validated rules, with AI limited to explanation; follow-up detection does not create entries without user confirmation. | F-7, F-9, AC-07 |
| AI-AC-09 | AI failures and incomplete processing are represented explicitly and handled safely. | AC-09 |
| AI-AC-10 | AI workflows enforce privacy and user-level authorization. | F-11, AC-08 |
| AI-AC-11 | Representative evaluation and regression tests exist for supported capabilities. | AC-10 |
| AI-AC-12 | Model and prompt changes can be traced and evaluated. | AC-12 |

Accuracy thresholds are set in Section 11. Model providers and deployment requirements must be agreed before a capability is production-ready.