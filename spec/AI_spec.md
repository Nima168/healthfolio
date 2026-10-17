# AI Specification
**Project:** AI Healthcare Decision-Support System  
**File:** `AI_spec.md`  
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
- **Human-controlled:** Users can review and correct extracted information. Extracted lab results are shown as read, with no confirm/correct/reject step (decision 2026-10-11); uncertain values are still flagged.
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

**Decided (2026-10-14):** the user states at upload whether a PDF is a **digital PDF** or a **scanned copy** (photos are always scanned). Digital PDFs: PyMuPDF copies the text stored in the file, sorted top to bottom so each table row stays on one line; if a "digital" PDF has no text inside, it is read as a scan instead. Scanned copies: each page is rendered at 300 DPI, converted to grayscale with auto-contrast, and read by **Tesseract OCR** (English, LSTM engine, page mode 4, which keeps table rows together). Below `OCR_MIN_CONFIDENCE` (default 85, Tesseract's average word confidence) the page is read again after a light median filter (removes scanner speckle) and the better result kept; a page still below the limit, or with almost no text, is sent to the AI **as an image** instead (vision fallback), so a poor scan is never silently misread. The reading method (`digital`, `ocr`, `ocr+vision`, `vision`) and average OCR confidence are stored on the job and shown to the user. OCR pages are marked `source="ocr"` in the AI input, and the prompts say such text may contain recognition mistakes, which are copied and never corrected; a value containing an unrecognised character (U+FFFD) always needs review. Calibrated on the synthetic samples: printed scans read at 86–91% confidence; a handwriting-style prescription and a faint ECG fell back to vision. Without Tesseract installed, scanned pages go to the AI as images.

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

**Decided (2026-10-14): no misleading values.** A part that is not printed is shown as **"Not mentioned"**; a part that is printed but cannot be read reliably is shown as **"Not identified"** and never as a guess. A part is not identified when the model lists it as unreadable (each result and medicine carries an `unreadable` list; the part is returned empty), or when fixed rules (`app/ai/readability.py`) find it garbled: an unrecognised character (U+FFFD); letters where a number belongs, outside known qualitative results ("TENS" for a numeric test); letters glued to digits or a double decimal point ("O38", "5.7.H"); a range whose separator is lost or replaced ("0.3 1.2", "55:2"); stray symbols in a unit. The doubtful text is replaced everywhere it would appear (results, timeline, search, AI summaries, exports); the item is marked for review with a `*_not_identified` finding and is never compared with a range. Header lines read as results (report dates, patient details) are removed. Confidence describes how clearly an item reads; OCR as the source is not by itself a reason for low confidence.

**Decided (2026-10-14): values checked against their own line.** Digital PDFs and OCR give the page text line by line, with a table row on one line (`app/ai/source_check.py`). Each lab result, discharge result, and medicine strength is looked up on the line(s) that name it (names matched word by word, tolerating one misread letter). A value found only on another extracted test's line was taken from the wrong row (e.g. AST and Ferritin swapped): it is shown as "Not identified" (`value_in_other_row`). A value on no line with its name is kept but flagged and not compared (`value_not_matched`); so is a test whose name is on no line (`name_not_matched`). A unit or range missing from the test's line and the next (ranges may wrap) is flagged for review only. Results from a page read as an image have no text to check against: they are flagged `read_from_image` and never compared. When the test-name lines hold no numbers at all (a PDF that gives its text column by column), `value_not_matched` is not used.

**Decided (2026-10-14): dates exactly as printed.** Every date read from a document is shown as printed ("02/09/26", "12-Mar-2026 13:10"); the reformatted calendar date is only a fallback when no printed form was kept. The calendar date (used for sorting, the timeline, and calculated due dates) is kept only when the printed form has one meaning (`app/ai/dates.py`): "25/09/26", "02-Sep-2026", and "2026-09-02" are kept; "02/09/26" (day and month could be swapped) keeps none. A follow-up such as "after 4 weeks" counted from such a date gets no due date and is marked for review; a calculated due date is shown after the written timing and labelled "calculated". App-wide lists (timeline, dashboard, follow-ups) keep one date format. A lab result's own date is copied as printed too (`result_date_text`); an ambiguous one leaves the result undated rather than falling back to the report date.

**Decided (2026-10-14): values far outside their range are marked.** A value more than 10 times the upper limit of a two-sided printed range, or below a tenth of its lower limit, is unusual enough to suggest a misread ("162" for 7.2). Real critical values can be that far out, so the result is still grouped and alerted, with the note "Unusually far outside the range: check the original" (`app/services/lab_summary.py`). One-sided bounds ("< 5.0") are not used for this.

**Decided (2026-10-14): an empty answer is read again.** When the model returns nothing (no results, medicines, findings) for a request whose document text has at least 200 characters, or that holds page images, the request is sent up to two more times (one retry was not always enough in the evaluation). A third empty answer fails the reading with `ai_empty_output` ("Nothing could be read this time … Refresh analysis"), never "no results found".

**Decided (2026-10-17): a symbol misread beside a value is not dropped silently.** OCR may turn a printed symbol into a stray one ("≤ 3.5" read as "£35"), and the model may then return only "35". When the value, unit, or range sits directly beside an unrecognised character or a stray symbol (currency and similar signs, never `< ≤ = ± *`) on the test's line, that part is "Not identified" (`app/ai/source_check.py`, `beside_unreadable`).

**Decided (2026-10-17): tiered ranges are judged by their band.** A range printed as labelled bands ("Desirable < 200; Borderline 200-239; High >= 240") is judged by the band the value falls in: High or Borderline is above the range, Low is below, Normal/Desirable/Optimal (or similar) is within. Other bands, gaps between bands, and overlapping bands are not judged (rules in `api_contract_spec.md` Section 6.2, lab summary rule 5).

**Decided (2026-10-17): watermarks are not read.** A digital PDF's diagonal (rotated) text, such as a "SYNTHETIC TEST DATA" or "SAMPLE" watermark, is left out of the text given to the AI: read with the page it was glued onto the row it crosses ("DATA1.50 – 4.10"), which then had to be shown as Not identified. Pages without rotated text are read exactly as before (`app/ai/reading.py`, `page_text`). Scanned pages are unchanged.

**Decided (2026-10-17): instructions that only repeat the strength are not read.** When a medicine's instructions are just its strength again ("625 mg" for 625 mg, ignoring case and spaces), the how-to-take column was not read (e.g. whole-page OCR of a tilted, watermarked scan missed the table's Frequency and Duration columns). The instructions are shown as "Not identified" and the medicine is marked for review, never as if read. Known limitation: on such scans the frequency itself is not recovered.

**Decided (2026-10-17): conditional follow-ups.** A follow-up that depends on a condition ("Review after 5 days if not better/SOS") keeps the condition exactly as written (`condition`; prompts `prescription-v7-condition`, `discharge-v5-condition`, `consultation-v3-condition`, `specialist-v2-condition`). It is shown as "only if needed: <condition>", gets no calculated date, and is never added to Checkups and Follow-ups, so it can never show as overdue. The reason a follow-up is unclear is written out on the page, not only on hover.

**Decided (2026-10-17): pathology and specialist reports.** The upload types `pathology_report` and `specialist_report` decide the reading directly (no classification). Pathology (`pathology-v1`): specimen, clinical history, gross and microscopic description, diagnosis, tumour details (only when written), special tests, comments, each line exactly as written; never "benign", "malignant", "normal", or "abnormal" unless written. Specialist (`specialist-v1`; ECG, echo, spirometry, EEG, ...): reason, measurements (compared only with the range printed beside them), findings, conclusions with machine and physician kept apart, recommendations, follow-ups counted from the test date; specialty only when written. A line containing an unrecognised character is "Not identified" and a pathology diagnosis that is not identified is never suggested. Parts the report does not have are left out of the summary.

**Decided (2026-10-17): the duration is shown once.** A medicine's instructions hold dose, frequency, and timing; the duration is kept only in `duration_text`. When a table's columns are joined and the instructions end with the same text as the duration ("…, At night, 90 days" with "90 days"), code removes that ending (`app/ai/prescription_validation.py`, also used for discharge medicines); the prompt says so too (`prescription-v6-duration`). Medicines read earlier are shown without the repeat.

## 5. AI Architecture

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

**Decided for lab-result extraction:** Qwen3.8-27B (`qwen/qwen3.8-27b`) on Groq, called through the official Groq Python SDK, with strict JSON-schema output (`response_format` `json_schema`, `strict: true`) and the model's reasoning hidden from the response (`reasoning_format: "hidden"`). The AI organises **text** into structured fields: PyMuPDF text for digital PDFs and Tesseract OCR text for scanned copies (Section 4.2). Only pages OCR cannot read confidently are sent as images, downscaled to at most 2,048 px on the longer side, at most 3 per request (provider limit), each labelled by its real page number, with the results merged. Limits: 131K-token context, 16,384 output tokens, 30 scanned pages. There is no provider-side refusal fallback; a refusal fails the job with a clear message. Extraction is off unless `EXTRACTION_ENABLED=true` and runs on synthetic data only until the privacy review in Section 12 is complete (including Groq's data-retention terms).

Embedding methods and vector databases: not yet defined. They are selected when requirements and evaluations justify them.

## 6. Health History and Insight Generation

The AI layer may organize information chronologically and summarize documented history. It must:

- Use only records authorized for the current user and task.
- Preserve the dates and sources of relevant facts.
- Distinguish historical observations from current information.
- Highlight missing, inconsistent, or outdated information.
- Explain the evidence behind an insight where possible.

Sentences in an AI summary that cannot be matched to the user's records are removed and not shown; the number removed is stored (`dropped_count`) for monitoring but no longer shown to the user (decision 2026-10-17).

What a summary is given (decision 2026-10-17): cancelled follow-ups are not sent; each fact carries its status as the app shows it ("Overdue", "Done", "Taking", "2 outside range"). The facts are sent as compact JSON within a size budget so the request stays under the AI service's input-tokens-a-minute limit; when they would exceed it, the oldest timeline records are left out and the summary says how many ("8 older records were left out of this summary…"). A request the service refuses as too large is reported as such (`ai_request_too_large`), not as "busy".

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

Rules decide; AI explains. This includes flagging results outside the reference range stated in the source report: the rule raises the flag, and the AI may explain it as an item for review, not a diagnosis. For lab results this is implemented as the lab summary (`api_contract_spec.md` Section 6.2): the AI only reads the report; the above/below/normal/needs-review decision is deterministic code.

AI may support alerts by:

- Extracting the values that validated rules evaluate.
- Flagging when critical information is incomplete or uncertain.
- Explaining the documented basis for a triggered alert, with the doctor's-advice note (Section 6.1).

Potential emergencies use predefined safety messaging directing the user to qualified medical or emergency services, without waiting for AI analysis. The system is never the sole emergency-response mechanism. Prohibited actions are listed in `backend_spec.md` Section 1.4.

### 9.2 Follow-Up Detection

AI may detect documented checkup and follow-up recommendations and present them to the user as suggestions. A follow-up entry is created only when the user confirms or records it (`goal_spec.md` UC-5). Automated reminder delivery is deferred. Implemented for prescriptions (`api_contract_spec.md` Section 6.3): the AI copies the timing as written; dates are calculated by code; "Add as reminders" is the user's confirmation. Prompt versions: `prescription-v3-groq`, `discharge-v2-groq`, `consultation-v1-groq`, `imaging-v1-groq`, `test-report-v2-groq`, `classify-v3-groq`; later `pathology-v1` and `specialist-v1` (2026-10-17). Scan images (MRI, CT, X-ray pictures, ECG tracings) are not interpreted; only written reports are read (decision 2026-10-12).

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

**Evaluation harness (2026-10-14):** `backend/evaluation/` generates fictional documents from known data (lab reports, prescriptions, discharge summaries, consultation notes, imaging reports), renders each as a digital PDF and as scanned copies at three damage levels (clean, medium, hard), runs them through the real pipeline (upload check, PyMuPDF/Tesseract with vision fallback, Groq, validation rules), and reports items found, field accuracy, invented items, review-flag coverage of wrong values, grouping, dates, honest blanks, OCR character error rate, reading route, run-to-run consistency, and speed. Synthetic data cannot stand in for real reports: results show behaviour and failure points, and a de-identified real-document set remains needed before release.

**Latest results (2026-10-14, quick set: 10 documents, 106 items, single runs):**
- No misleading groupings: 0 results shown above, below, or normal in the wrong group.
- Dates: 16 of 16 right, and 10 of 10 shown exactly as printed.
- Fields right: 91.1%.
- Items found: 99 of 106.
- Wrong values: 10, of which 6 were flagged for review.

**AI accuracy has not been rigorously validated:** this is a small synthetic set with single runs, not clinical validation. Rigorous validation (a de-identified real-document set, repeated runs, all release gates met) is kept as a future plan. The critical-field gate (≥ 98%) is **not met**. The remaining errors are OCR misreads that the AI copies faithfully, and run-to-run variation in how completely a page is read. Full method and the comparison across versions: `docs/END_TO_END.md` §6.

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

Model, prompt, and pipeline changes are versioned and evaluated before release, and each result can be traced to the versions that produced it. Each extraction job records the model that answered (`model_version`, which shows a fallback model if one was used), the prompt version (`prompt_version`, currently `lab-results-v3-groq`), and token usage. Logs contain IDs, timings, and token counts only, never document text, prompts, or responses.

**Evaluation status:** the Section 11 thresholds have not yet been measured. Lab-result extraction is therefore unvalidated and not production-ready until an evaluation set of labelled synthetic reports has been run.

## 16. Extensibility

Possible future extensions, not part of the initial scope:

- Additional medical document formats.
- Image understanding (e.g. reading scan images directly).
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