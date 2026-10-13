"""Extracted results schemas: lab summary and prescription summary (api_contract_spec.md Section 6.2)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.schemas.documents import DatePrecision


def _plain_number(value: Decimal | None) -> str | None:
    """Exact decimal as text without trailing zeros ("18.300000" → "18.3", never "1E+3")."""
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


# Numbers are returned as exact strings (no floating-point rounding).
ExactNumber = Annotated[Decimal | None, PlainSerializer(_plain_number, return_type=str | None)]


class ObservationResponse(BaseModel):
    id: uuid.UUID
    name: str
    value_text: str
    value_numeric: ExactNumber
    unit: str | None
    reference_range_text: str | None
    reference_low: ExactNumber
    reference_high: ExactNumber
    observed_at: date | None
    observed_at_precision: DatePrecision | None
    page: int | None
    source_snippet: str | None
    confidence: Literal["high", "medium", "low"] | None
    needs_review: bool
    validation_findings: list[str]
    notes: str | None


class ExtractionJobResponse(BaseModel):
    status: str
    attempts: int
    error_category: str | None
    updated_at: datetime
    # How the text was obtained: digital, ocr, ocr+vision, or vision; null until the file is read.
    reading_method: str | None = None
    ocr_confidence: int | None = None  # average over OCR pages, 0–100


class ExtractionRequest(BaseModel):
    """Optional body of "Refresh analysis": read the document again as this kind of copy."""

    model_config = ConfigDict(extra="forbid")

    copy_type: Literal["digital", "scanned"] | None = None


class SummaryLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None


class InvalidLineResponse(SummaryLineResponse):
    reason: str  # why it could not be judged


class LabSummaryResponse(BaseModel):
    """Values outside the reference range printed in the report (app/services/lab_summary.py)."""

    model_config = ConfigDict(from_attributes=True)

    report_date: str | None  # exactly as printed; null if not printed or not recorded
    above: list[SummaryLineResponse]
    below: list[SummaryLineResponse]
    normal: list[SummaryLineResponse]
    invalid: list[InvalidLineResponse]  # could not be judged; shown as written


class MedicationLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    strength: str | None
    instructions: str | None
    duration_text: str | None
    unclear: bool  # shown with "(unclear – check original)"
    reason: str | None


class FollowUpLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    due_date: date | None
    description: str
    unclear: bool
    reason: str | None
    when_text: str | None  # timing as written; shown when there is no exact date


class PrescriptionSummaryResponse(BaseModel):
    """Medicines and follow-ups by date; unclear items flagged inline (app/services/prescription_summary.py)."""

    model_config = ConfigDict(from_attributes=True)

    prescribed_on: date | None
    date_text: str | None  # exactly as printed
    prescriber_name: str | None
    medications: list[MedicationLineResponse]
    follow_ups: list[FollowUpLineResponse]
    reminders: Literal["available", "added", "none"]


class KeyResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    first_value: str | None
    last_value: str
    unit: str | None
    reference_range_text: str | None
    flag: Literal["high", "low"] | None
    still: bool
    last_tested: date | None
    unclear: bool


class DischargeSummaryResponse(BaseModel):
    """Stay, diagnoses, key results, medicines, follow-ups, warning signs (app/services/discharge_summary.py)."""

    model_config = ConfigDict(from_attributes=True)

    facility_name: str | None
    admitted_on: date | None
    admitted_text: str | None
    discharged_on: date | None
    discharged_text: str | None
    stay_days: int | None
    diagnoses: list[str]
    key_results: list[KeyResultResponse]
    medications: list[MedicationLineResponse]
    follow_ups: list[FollowUpLineResponse]
    reminders: Literal["available", "added", "none"]
    warning_signs: list[str]


class ConsultationSummaryResponse(BaseModel):
    """Consultation note, exactly as written (app/services/report_summaries.py)."""

    model_config = ConfigDict(from_attributes=True)

    visit_date: date | None
    visit_text: str | None
    clinician_name: str | None
    symptoms: list[str]
    observations: list[str]
    assessment: list[str]
    plan: list[str]
    follow_ups: list[FollowUpLineResponse]
    reminders: Literal["available", "added", "none"]


class ImagingSummaryResponse(BaseModel):
    """The written imaging report, exactly as written; scan images are not read."""

    model_config = ConfigDict(from_attributes=True)

    is_written_report: bool
    exam_name: str | None
    report_id: str | None
    facility_name: str | None
    exam_date: date | None
    exam_text: str | None
    report_date: date | None
    report_text: str | None
    body_region: str | None
    findings: list[str]
    impression: list[str]
    uncertainty: list[str]


class MeasurementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value_text: str
    unit: str | None
    reference_range_text: str | None
    flag: Literal["high", "low"] | None  # against the printed range
    unclear: bool


class InterpretationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: Literal["machine", "physician", "other"]
    confirmed: bool
    text: str


class DiagnosticTestSummaryResponse(BaseModel):
    """Another test report (e.g. ECG): measurements, interpretations by source, visual content not read."""

    model_config = ConfigDict(from_attributes=True)

    test_type: str | None
    test_name: str | None
    report_id: str | None
    facility_name: str | None
    report_form: Literal["typed", "handwritten", "machine printout", "unknown"]
    test_date: date | None
    test_text: str | None
    measurements: list[MeasurementResponse]
    interpretations: list[InterpretationResponse]
    visual_content: list[str]


class DocumentExtractionResponse(BaseModel):
    extraction_enabled: bool
    media_type: str
    copy_type: Literal["digital", "scanned"] | None  # the user's answer; null for older uploads
    job: ExtractionJobResponse | None
    # What the document was read as; null until extraction completes.
    document_kind: (
        Literal[
            "lab_report",
            "prescription",
            "discharge_summary",
            "consultation_note",
            "imaging_report",
            "test_report",
            "other",
        ]
        | None
    )
    items: list[ObservationResponse]
    summary: LabSummaryResponse | None  # lab reports, once extracted
    prescription: PrescriptionSummaryResponse | None  # prescriptions, once extracted
    discharge: DischargeSummaryResponse | None  # discharge summaries, once extracted
    consultation: ConsultationSummaryResponse | None
    imaging: ImagingSummaryResponse | None
    test_report: DiagnosticTestSummaryResponse | None  # other test reports, e.g. ECG
