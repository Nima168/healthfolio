"""The structured outputs the model must return (DL_AI_spec.md Section 4.3): lab results, prescriptions, type.

The JSON schema is sent with the request (structured outputs), and the Pydantic models
re-validate the response before anything is stored (DL_AI_spec.md Section 4.5).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


_RESULT_PROPERTIES: dict[str, dict] = {
    "test_name": {"type": "string", "description": "Test name exactly as written."},
    "value_text": {"type": "string", "description": "Result exactly as written, e.g. '5.4', '<0.5', 'Negative'."},
    "value_numeric": _nullable({"type": "number", "description": "The number in value_text, only if one is written."}),
    "unit": _nullable({"type": "string", "description": "Unit exactly as written."}),
    "reference_range_text": _nullable({"type": "string", "description": "Reference range exactly as written."}),
    "reference_low": _nullable({"type": "number"}),
    "reference_high": _nullable({"type": "number"}),
    "result_date": _nullable({"type": "string", "description": "YYYY-MM-DD, only if written for this result."}),
    "result_date_precision": _nullable({"type": "string", "enum": ["day", "month", "year"]}),
    "page": _nullable({"type": "integer", "description": "1-based page where the result appears."}),
    "source_text": {"type": "string", "description": "The exact line or table row the result was read from."},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "notes": _nullable({"type": "string", "description": "Anything unclear: illegible, ambiguous, uncertain."}),
}

EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "report_date_text": _nullable(
            {"type": "string", "description": "Collection/report date exactly as printed, e.g. '14-Mar-2026'."}
        ),
        "report_date": _nullable({"type": "string", "description": "Collection/report date, YYYY-MM-DD."}),
        "report_date_precision": _nullable({"type": "string", "enum": ["day", "month", "year"]}),
        "lab_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _RESULT_PROPERTIES,
                "required": list(_RESULT_PROPERTIES),
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["report_date_text", "report_date", "report_date_precision", "lab_results", "warnings"],
    "additionalProperties": False,
}


class ExtractedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str
    value_text: str
    value_numeric: float | None
    unit: str | None
    reference_range_text: str | None
    reference_low: float | None
    reference_high: float | None
    result_date: str | None
    result_date_precision: Literal["day", "month", "year"] | None
    page: int | None
    source_text: str
    confidence: Literal["high", "medium", "low"]
    notes: str | None


class ExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date_text: str | None = None
    report_date: str | None
    report_date_precision: Literal["day", "month", "year"] | None
    lab_results: list[ExtractedResult]
    warnings: list[str]


# ---------- prescriptions ----------

_MEDICATION_PROPERTIES: dict[str, dict] = {
    "name": {"type": "string", "description": "Medicine name exactly as written, without the strength."},
    "strength": _nullable({"type": "string", "description": "Strength exactly as written, e.g. '10 mg'."}),
    "instructions": _nullable(
        {"type": "string", "description": "Dose, frequency, and timing as written, e.g. '1 tablet daily, At night'."}
    ),
    "duration_text": _nullable({"type": "string", "description": "How long, exactly as written, e.g. '90 days'."}),
    "page": _nullable({"type": "integer", "description": "1-based page where the medicine appears."}),
    "source_text": {"type": "string", "description": "The exact line the medicine was read from."},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "notes": _nullable({"type": "string", "description": "Anything unclear: illegible, ambiguous, uncertain."}),
}

_FOLLOW_UP_PROPERTIES: dict[str, dict] = {
    "description": {
        "type": "string",
        "description": "What is to be done, as written, e.g. 'Kidney function test', 'Doctor visit'.",
    },
    "kind": {"type": "string", "enum": ["investigation", "appointment", "checkup"]},
    "date": _nullable({"type": "string", "description": "YYYY-MM-DD, only if a calendar date is written."}),
    "date_text": _nullable(
        {"type": "string", "description": "The date or timing exactly as written, e.g. 'after 4 weeks'."}
    ),
    "relative_amount": _nullable(
        {"type": "integer", "description": "Only for timing relative to the prescription, e.g. 4 for 'after 4 weeks'."}
    ),
    "relative_unit": _nullable({"type": "string", "enum": ["days", "weeks", "months"]}),
    "page": _nullable({"type": "integer", "description": "1-based page where the follow-up appears."}),
    "source_text": {"type": "string", "description": "The exact line the follow-up was read from."},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "notes": _nullable({"type": "string", "description": "Anything unclear: illegible, ambiguous, uncertain."}),
}


def _items(properties: dict[str, dict]) -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


PRESCRIPTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "prescription_date_text": _nullable(
            {"type": "string", "description": "Date the prescription was written, exactly as printed."}
        ),
        "prescription_date": _nullable({"type": "string", "description": "The same date as YYYY-MM-DD."}),
        "prescriber_name": _nullable(
            {"type": "string", "description": "Prescribing doctor's name exactly as written, including 'Dr.'."}
        ),
        "medications": _items(_MEDICATION_PROPERTIES),
        "follow_ups": _items(_FOLLOW_UP_PROPERTIES),
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "prescription_date_text",
        "prescription_date",
        "prescriber_name",
        "medications",
        "follow_ups",
        "warnings",
    ],
    "additionalProperties": False,
}


class ExtractedMedication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    strength: str | None
    instructions: str | None
    duration_text: str | None
    page: int | None
    source_text: str
    confidence: Literal["high", "medium", "low"]
    notes: str | None


class ExtractedFollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    kind: Literal["investigation", "appointment", "checkup"]
    date: str | None
    date_text: str | None
    relative_amount: int | None
    relative_unit: Literal["days", "weeks", "months"] | None
    page: int | None
    source_text: str
    confidence: Literal["high", "medium", "low"]
    notes: str | None


class PrescriptionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prescription_date_text: str | None
    prescription_date: str | None
    prescriber_name: str | None
    medications: list[ExtractedMedication]
    follow_ups: list[ExtractedFollowUp]
    warnings: list[str]


# ---------- document type (only when the user did not choose one) ----------

DOCUMENT_TYPES = (
    "lab_report",
    "prescription",
    "discharge_summary",
    "consultation_note",
    "imaging_report",
    "test_report",
    "other",
)

CLASSIFICATION_SCHEMA: dict = {
    "type": "object",
    "properties": {"document_type": {"type": "string", "enum": list(DOCUMENT_TYPES)}},
    "required": ["document_type"],
    "additionalProperties": False,
}


class ClassificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal[
        "lab_report", "prescription", "discharge_summary", "consultation_note", "imaging_report", "test_report", "other"
    ]


# ---------- discharge summaries ----------

_DISCHARGE_RESULT_PROPERTIES: dict[str, dict] = {
    "test_name": {"type": "string", "description": "Test or investigation name exactly as written."},
    "value_text": {"type": "string", "description": "One result exactly as written, e.g. '1.31', 'No pathogens'."},
    "unit": _nullable({"type": "string", "description": "Unit exactly as written."}),
    "reference_range_text": _nullable({"type": "string", "description": "Reference range exactly as written."}),
    "result_date_text": _nullable(
        {"type": "string", "description": "The date of this result exactly as written, e.g. '12-Aug'."}
    ),
    "page": _nullable({"type": "integer", "description": "1-based page where the result appears."}),
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
}

DISCHARGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "facility_name": _nullable({"type": "string", "description": "Hospital name exactly as written."}),
        "admission_date_text": _nullable({"type": "string", "description": "Admission date exactly as printed."}),
        "admission_date": _nullable({"type": "string", "description": "The admission date as YYYY-MM-DD."}),
        "discharge_date_text": _nullable({"type": "string", "description": "Discharge date exactly as printed."}),
        "discharge_date": _nullable({"type": "string", "description": "The discharge date as YYYY-MM-DD."}),
        "diagnoses": {"type": "array", "items": {"type": "string", "description": "One diagnosis exactly as written."}},
        "results": _items(_DISCHARGE_RESULT_PROPERTIES),
        "medications": _items(_MEDICATION_PROPERTIES),
        "follow_ups": _items(_FOLLOW_UP_PROPERTIES),
        "warning_signs": {
            "type": "array",
            "items": {"type": "string", "description": "One 'return to emergency if' instruction as written."},
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "facility_name",
        "admission_date_text",
        "admission_date",
        "discharge_date_text",
        "discharge_date",
        "diagnoses",
        "results",
        "medications",
        "follow_ups",
        "warning_signs",
        "warnings",
    ],
    "additionalProperties": False,
}


class ExtractedDischargeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None
    result_date_text: str | None
    page: int | None
    confidence: Literal["high", "medium", "low"]


class DischargePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facility_name: str | None
    admission_date_text: str | None
    admission_date: str | None
    discharge_date_text: str | None
    discharge_date: str | None
    diagnoses: list[str]
    results: list[ExtractedDischargeResult]
    medications: list[ExtractedMedication]
    follow_ups: list[ExtractedFollowUp]
    warning_signs: list[str]
    warnings: list[str]


# ---------- consultation notes, imaging reports, other test reports (e.g. ECG) ----------


def _texts(description: str) -> dict:
    return {"type": "array", "items": {"type": "string", "description": description}}


CONSULTATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "visit_date_text": _nullable({"type": "string", "description": "Consultation date exactly as printed."}),
        "visit_date": _nullable({"type": "string", "description": "The same date as YYYY-MM-DD."}),
        "clinician_name": _nullable({"type": "string", "description": "Consulting doctor's name as written."}),
        "symptoms": _texts("One symptom or complaint statement exactly as written."),
        "observations": _texts("One examination finding or result line exactly as written."),
        "assessment": _texts("One assessment or impression statement exactly as written."),
        "plan": _texts("One plan or advice item exactly as written."),
        "follow_ups": _items(_FOLLOW_UP_PROPERTIES),
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "visit_date_text",
        "visit_date",
        "clinician_name",
        "symptoms",
        "observations",
        "assessment",
        "plan",
        "follow_ups",
        "warnings",
    ],
    "additionalProperties": False,
}


class ConsultationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date_text: str | None
    visit_date: str | None
    clinician_name: str | None
    symptoms: list[str]
    observations: list[str]
    assessment: list[str]
    plan: list[str]
    follow_ups: list[ExtractedFollowUp]
    warnings: list[str]


IMAGING_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_written_report": {
            "type": "boolean",
            "description": "True if the document contains a written report; false if it is only scan images.",
        },
        "exam_name": _nullable({"type": "string", "description": "Examination name as written."}),
        "report_id": _nullable({"type": "string", "description": "Report or accession number as written."}),
        "facility_name": _nullable({"type": "string", "description": "Imaging centre or hospital as written."}),
        "exam_date_text": _nullable({"type": "string", "description": "Examination date exactly as printed."}),
        "exam_date": _nullable({"type": "string", "description": "The examination date as YYYY-MM-DD."}),
        "report_date_text": _nullable({"type": "string", "description": "Report date exactly as printed."}),
        "report_date": _nullable({"type": "string", "description": "The report date as YYYY-MM-DD."}),
        "body_region": _nullable({"type": "string", "description": "Body region examined, as written."}),
        "findings": _texts("One finding exactly as written."),
        "impression": _texts("One impression or conclusion statement exactly as written."),
        "uncertainty": _texts("A statement from the report expressing uncertainty, a limitation, or a condition."),
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "is_written_report",
        "exam_name",
        "report_id",
        "facility_name",
        "exam_date_text",
        "exam_date",
        "report_date_text",
        "report_date",
        "body_region",
        "findings",
        "impression",
        "uncertainty",
        "warnings",
    ],
    "additionalProperties": False,
}


class ImagingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_written_report: bool
    exam_name: str | None
    report_id: str | None
    facility_name: str | None
    exam_date_text: str | None
    exam_date: str | None
    report_date_text: str | None
    report_date: str | None
    body_region: str | None
    findings: list[str]
    impression: list[str]
    uncertainty: list[str]
    warnings: list[str]


_MEASUREMENT_PROPERTIES: dict[str, dict] = {
    "name": {"type": "string", "description": "Measurement name exactly as written, e.g. 'PR', 'Heart Rate'."},
    "value_text": {"type": "string", "description": "The value exactly as written, without the unit."},
    "unit": _nullable({"type": "string", "description": "Unit exactly as written."}),
    "reference_range_text": _nullable({"type": "string", "description": "Printed normal range, as written."}),
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
}

_INTERPRETATION_PROPERTIES: dict[str, dict] = {
    "source": {"type": "string", "enum": ["machine", "physician", "other"]},
    "confirmed": {"type": "boolean", "description": "True only if the report says it was confirmed or verified."},
    "text": {"type": "string", "description": "The interpretation exactly as written."},
}

TEST_REPORT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "test_type": _nullable({"type": "string", "description": "Short test type as written, e.g. 'ECG'."}),
        "test_name": _nullable({"type": "string", "description": "Full test name as written."}),
        "report_id": _nullable({"type": "string", "description": "Report number as written."}),
        "facility_name": _nullable({"type": "string", "description": "Clinic, lab, or hospital as written."}),
        "report_form": {"type": "string", "enum": ["typed", "handwritten", "machine printout", "unknown"]},
        "test_date_text": _nullable({"type": "string", "description": "Test date (and time) exactly as printed."}),
        "test_date": _nullable({"type": "string", "description": "The test date as YYYY-MM-DD."}),
        "measurements": _items(_MEASUREMENT_PROPERTIES),
        "interpretations": _items(_INTERPRETATION_PROPERTIES),
        "visual_content": _texts("A chart, tracing, or image in the document, named as written."),
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "test_type",
        "test_name",
        "report_id",
        "facility_name",
        "report_form",
        "test_date_text",
        "test_date",
        "measurements",
        "interpretations",
        "visual_content",
        "warnings",
    ],
    "additionalProperties": False,
}


class ExtractedMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None
    confidence: Literal["high", "medium", "low"]


class ExtractedInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["machine", "physician", "other"]
    confirmed: bool
    text: str


class OtherReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_type: str | None
    test_name: str | None
    report_id: str | None
    facility_name: str | None
    report_form: Literal["typed", "handwritten", "machine printout", "unknown"]
    test_date_text: str | None
    test_date: str | None
    measurements: list[ExtractedMeasurement]
    interpretations: list[ExtractedInterpretation]
    visual_content: list[str]
    warnings: list[str]
