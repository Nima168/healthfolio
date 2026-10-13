"""Record search (api_contract_spec.md Section 9.1).

Searches the user's own records in memory: documents, lab results, medicines, diagnoses and conditions,
follow-ups, the text of read reports (consultations, imaging, test reports, discharge summaries), allergies,
surgeries, hospitalizations, and family history. Every word of the query must appear in the record (any field,
ignoring case), so partial words such as "creat" work. The query text is never logged or stored.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import Observation
from app.models.prescription import Condition, FollowUp, Medication
from app.models.profile import MedicalRecordItem, ProfileValue
from app.services import jobs

_COMPLETED = ("completed", "completed_with_warnings")
_DETAIL_LABELS = {
    "symptoms": "Symptoms",
    "observations": "Observations",
    "assessment": "Assessment",
    "plan": "Plan",
    "findings": "Findings",
    "impression": "Impression",
    "uncertainty": "Uncertainty",
    "exam_name": "Examination",
    "body_region": "Body region",
    "test_name": "Test",
    "interpretations": "Interpretation",
    "measurements": "Measurement",
    "facility_name": "Hospital",
    "warning_signs": "Return to emergency if",
    "clinician_name": "Doctor",
}
SNIPPET = 160


@dataclass
class SearchCriteria:
    query: str | None = None
    document_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    condition: str | None = None
    provider: str | None = None


@dataclass
class Result:
    record_type: str
    id: str
    title: str
    date: date | None
    fields: list[tuple[str, str]]  # (label, text) searched in order
    source_document: Document | None
    link: str
    matched_field: str | None = None
    snippet: str | None = None
    extra: dict = field(default_factory=dict)


def _words(text: str | None) -> list[str]:
    return [w for w in (text or "").casefold().split() if w]


def _snippet(text: str, word: str) -> str:
    """The text around the first match, at most SNIPPET characters."""
    if len(text) <= SNIPPET:
        return text
    at = max(text.casefold().find(word), 0)
    start = max(0, at - SNIPPET // 3)
    end = min(len(text), start + SNIPPET)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key in ("text", "name", "value_text"):
            if isinstance(value.get(key), str):
                yield value[key]


class SearchService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------- the user's records ----------

    def _records(self, user_id: uuid.UUID) -> list[Result]:
        documents = {
            d.id: d
            for d in self.session.scalars(
                select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))
            )
        }
        latest = {doc_id: jobs.latest_job(self.session, doc_id) for doc_id in documents}
        results: list[Result] = []

        for document in documents.values():
            job = latest[document.id]
            results.append(
                Result(
                    "document",
                    str(document.id),
                    document.title or "Untitled",
                    (job.document_date if job else None) or document.document_date,
                    [
                        ("Name", document.title or ""),
                        ("Hospital, lab, or clinic", document.provider_name or ""),
                        ("File", document.original_filename or ""),
                    ],
                    document,
                    f"/documents/{document.id}",
                )
            )
            if job is None or job.status not in _COMPLETED or not job.details:
                continue
            fields = [
                (_DETAIL_LABELS[key], text)
                for key, value in job.details.items()
                if key in _DETAIL_LABELS
                for text in _strings(value)
                if text
            ]
            if fields:
                results.append(
                    Result(
                        "report_text",
                        f"text:{document.id}",
                        document.title or "Report",
                        (job.document_date if job else None) or document.document_date,
                        fields,
                        document,
                        f"/documents/{document.id}",
                    )
                )

        for row in self.session.scalars(
            select(Observation).where(Observation.user_id == user_id, Observation.deleted_at.is_(None))
        ):
            document = documents.get(row.source_document_id)
            if document is None:
                continue
            value = " ".join(part for part in (row.value_text, row.unit) if part)
            results.append(
                Result(
                    "lab_result",
                    str(row.id),
                    f"{row.name} {value}",
                    row.observed_at or document.document_date,
                    [("Test", row.name), ("Result", value), ("Range", row.reference_range_text or "")],
                    document,
                    f"/documents/{document.id}",
                )
            )

        for row in self.session.scalars(
            select(Medication).where(Medication.user_id == user_id, Medication.deleted_at.is_(None))
        ):
            document = documents.get(row.source_document_id)
            results.append(
                Result(
                    "medication",
                    str(row.id),
                    " ".join(part for part in (row.name, row.strength) if part),
                    row.start_date or (document.document_date if document else None),
                    [
                        ("Medicine", row.name),
                        ("Strength", row.strength or ""),
                        ("How to take", row.dosage_text or ""),
                        ("Prescriber", row.prescriber_name or ""),
                        ("Notes", row.notes or ""),
                    ],
                    document,
                    "/medications",
                )
            )

        for row in self.session.scalars(
            select(Condition).where(Condition.user_id == user_id, Condition.deleted_at.is_(None))
        ):
            document = documents.get(row.source_document_id)
            from_document = row.origin == "document_extracted"
            if from_document and document is None:
                continue
            results.append(
                Result(
                    "diagnosis" if from_document else "condition",
                    str(row.id),
                    row.name,
                    document.document_date if document else None,
                    [("Diagnosis as written" if from_document else "Condition", row.name)],
                    document,
                    f"/documents/{document.id}" if from_document else "/profile",
                )
            )

        for row in self.session.scalars(select(FollowUp).where(FollowUp.user_id == user_id)):
            results.append(
                Result(
                    "follow_up",
                    str(row.id),
                    row.title,
                    row.due_date,
                    [("Follow-up", row.title)],
                    documents.get(row.source_document_id),
                    "/follow-ups",
                )
            )

        for row in self.session.scalars(
            select(ProfileValue).where(
                ProfileValue.user_id == user_id, ProfileValue.field == "allergy", ProfileValue.deleted_at.is_(None)
            )
        ):
            results.append(
                Result(
                    "allergy",
                    str(row.id),
                    row.value,
                    None,
                    [("Allergy", row.value), ("Reaction", row.detail or "")],
                    None,
                    "/profile",
                )
            )

        labels = {
            "surgery": ("surgery", "Surgery"),
            "hospitalization": ("hospitalization", "Hospitalization"),
            "family": ("family_history", "Family history"),
        }
        for row in self.session.scalars(
            select(MedicalRecordItem).where(
                MedicalRecordItem.user_id == user_id, MedicalRecordItem.deleted_at.is_(None)
            )
        ):
            record_type, label = labels[row.kind]
            results.append(
                Result(
                    record_type,
                    str(row.id),
                    f"{row.name} ({row.relation})" if row.relation else row.name,
                    row.occurred_on,
                    [(label, row.name), ("Notes", row.notes or "")],
                    None,
                    "/profile",
                )
            )
        return results

    # ---------- matching ----------

    def search(self, user_id: uuid.UUID, criteria: SearchCriteria) -> list[Result]:
        records = self._records(user_id)
        words = _words(criteria.query)

        allowed_documents: set[uuid.UUID] | None = None
        if criteria.provider or criteria.document_type or criteria.condition:
            allowed_documents = self._documents_matching(user_id, criteria)

        found = []
        for record in records:
            document = record.source_document
            if allowed_documents is not None:
                condition_hit = (
                    criteria.condition
                    and record.record_type == "condition"
                    and all(w in record.title.casefold() for w in _words(criteria.condition))
                )
                if not condition_hit and (document is None or document.id not in allowed_documents):
                    continue
            if criteria.date_from and (record.date is None or record.date < criteria.date_from):
                continue
            if criteria.date_to and (record.date is None or record.date > criteria.date_to):
                continue
            if words:
                combined = " ".join(text for _, text in record.fields).casefold()
                if not all(w in combined for w in words):
                    continue
                label, text = next(
                    ((lbl, txt) for lbl, txt in record.fields if words[0] in txt.casefold()), record.fields[0]
                )
                record.matched_field, record.snippet = label, _snippet(text, words[0])
            found.append(record)
        return sorted(
            found, key=lambda r: (r.date is None, -(r.date.toordinal() if r.date else 0), r.record_type, r.title)
        )

    def _documents_matching(self, user_id: uuid.UUID, criteria: SearchCriteria) -> set[uuid.UUID]:
        documents = list(
            self.session.scalars(select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None)))
        )
        allowed = set()
        condition_words = _words(criteria.condition)
        with_condition: set[uuid.UUID] = set()
        if condition_words:
            for row in self.session.scalars(
                select(Condition).where(Condition.user_id == user_id, Condition.deleted_at.is_(None))
            ):
                if row.source_document_id and all(w in row.name.casefold() for w in condition_words):
                    with_condition.add(row.source_document_id)
        provider_words = _words(criteria.provider)
        for document in documents:
            if criteria.document_type:
                job = jobs.latest_job(self.session, document.id)
                kinds = {document.category, job.document_kind if job else None}
                if criteria.document_type not in kinds:
                    continue
            if provider_words and not all(w in (document.provider_name or "").casefold() for w in provider_words):
                continue
            if condition_words and document.id not in with_condition:
                continue
            allowed.add(document.id)
        return allowed
