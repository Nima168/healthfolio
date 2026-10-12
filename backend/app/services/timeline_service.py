"""The health timeline: the user's records in date order (frontend_spec.md Section 7, backend_spec.md BAC-07).

Built from the existing records on each request; nothing new is stored. Rules:
- Records from different dates are never merged: lab results are one entry per report and test date.
- No comparison or trends across dates (deferred, goal_spec.md Section 6).
- A missing date stays missing ("No date", last); it is never guessed.
- Every entry says where it came from and whether the user confirmed or changed it.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import ACTIVE_JOB_STATUSES, Observation, ProcessingJob
from app.models.prescription import Condition, FollowUp, Medication
from app.services.lab_summary import classify
from app.services.medication_service import MedicationService
from app.services.report_summaries import summarise_consultation, summarise_imaging, summarise_test_report

CATEGORIES = (
    "lab_results",
    "imaging",
    "test_reports",
    "consultations",
    "hospital_stays",
    "prescriptions",
    "medications",
    "follow_ups",
    "documents",
)
_COMPLETED = ("completed", "completed_with_warnings")


@dataclass
class TimelineEntry:
    id: str
    date: date | None
    date_precision: str | None  # day, month, year, unknown; None when there is no date
    category: str
    title: str
    lines: list[str] = field(default_factory=list)
    # from_document: read by AI, not checked by the user; confirmed_by_you, edited_by_you, added_by_you.
    trust: str = "from_document"
    tag: str | None = None  # e.g. "Overdue", "Done", "2 outside range"
    source_document_id: uuid.UUID | None = None
    source_document_title: str | None = None
    link: str | None = None


def _day(value: date) -> str:
    return f"{value.day:02d}-{value.strftime('%b')}-{value.year}"


def _join(*parts: str | None) -> str:
    return " ".join(part for part in parts if part)


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _medication_trust(medication: Medication, edited: bool) -> str:
    if medication.origin == "user_entered":
        return "added_by_you"
    if edited:
        return "edited_by_you"
    if medication.status_confirmed_at is not None:
        return "confirmed_by_you"
    return "from_document"


_STATUS_WORDS = {"active": "taking", "stopped": "stopped"}


class TimelineService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------- sources ----------

    def _documents(self, user_id: uuid.UUID) -> dict[uuid.UUID, Document]:
        rows = self.session.scalars(select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None)))
        return {document.id: document for document in rows}

    def _latest_jobs(self, document_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, ProcessingJob]:
        ids = list(document_ids)
        if not ids:
            return {}
        latest: dict[uuid.UUID, ProcessingJob] = {}
        for job in self.session.scalars(
            select(ProcessingJob).where(ProcessingJob.document_id.in_(ids)).order_by(ProcessingJob.created_at)
        ):
            latest[job.document_id] = job  # ordered oldest first, so the last one wins
        return latest

    @staticmethod
    def _document_date(document: Document, job: ProcessingJob | None) -> tuple[date | None, str | None]:
        if job is not None and job.document_date is not None:
            return job.document_date, "day"
        if document.document_date is not None:
            return document.document_date, document.document_date_precision or "day"
        return None, None

    @staticmethod
    def _base(document: Document, category: str, key: str, when: tuple[date | None, str | None]) -> dict:
        return {
            "id": f"{category}:{document.id}:{key}",
            "date": when[0],
            "date_precision": when[1],
            "category": category,
            "source_document_id": document.id,
            "source_document_title": document.title,
            "link": f"/documents/{document.id}",
        }

    def _lab_results(self, user_id: uuid.UUID, documents: dict[uuid.UUID, Document], jobs: dict) -> list[TimelineEntry]:
        rows = self.session.scalars(
            select(Observation)
            .where(Observation.user_id == user_id, Observation.deleted_at.is_(None))
            .order_by(Observation.position, Observation.created_at)
        )
        groups: dict[tuple[uuid.UUID, date | None], list[Observation]] = {}
        for row in rows:
            if row.source_document_id in documents:
                groups.setdefault((row.source_document_id, row.observed_at), []).append(row)

        entries = []
        for (document_id, observed_at), results in groups.items():
            document = documents[document_id]
            when = (
                (observed_at, results[0].observed_at_precision or "day")
                if observed_at
                else self._document_date(document, jobs.get(document_id))
            )
            outside, unchecked, within = [], 0, 0
            for result in results:
                status, _ = classify(result)
                if status in ("above", "below"):
                    word = "high" if status == "above" else "low"
                    outside.append(
                        _join(result.name, result.value_text, result.unit)
                        + f" ({word}; range {result.reference_range_text})"
                    )
                elif status == "within":
                    within += 1
                else:
                    unchecked += 1
            lines = [*outside]
            if within:
                lines.append(f"{within} within range")
            if unchecked:
                lines.append(f"{unchecked} not compared (no clear value or range)")
            count = len(results)
            entries.append(
                TimelineEntry(
                    **self._base(document, "lab_results", str(observed_at), when),
                    title=f"Lab results: {count} test{'s' if count != 1 else ''}",
                    lines=lines,
                    tag=f"{len(outside)} outside range" if outside else None,
                )
            )
        return entries

    def _reports(self, documents: dict[uuid.UUID, Document], jobs: dict, conditions: dict) -> list[TimelineEntry]:
        entries = []
        for document_id, document in documents.items():
            job = jobs.get(document_id)
            if job is None or job.status not in _COMPLETED:
                entries.append(self._plain_document(document, job))
                continue
            kind = job.document_kind or "lab_report"
            details = job.details or {}
            when = self._document_date(document, job)
            if kind == "lab_report":
                continue  # shown as lab-result entries
            if kind == "prescription":
                entries.append(
                    TimelineEntry(
                        **self._base(document, "prescriptions", "", when),
                        title=_join("Prescription", f"({job.prescriber_name})" if job.prescriber_name else None),
                    )
                )  # its medicines are filled in by _medications
            elif kind == "discharge_summary":
                admitted, discharged = _date(details.get("admitted_on")), _date(details.get("discharged_on"))
                when = (discharged, "day") if discharged else when
                lines = []
                if admitted or discharged:
                    stay = _join(
                        f"Admitted {_day(admitted)}" if admitted else None,
                        "→" if admitted and discharged else None,
                        f"Discharged {_day(discharged)}" if discharged else None,
                    )
                    lines.append(stay)
                lines += [f"Diagnosis (as written): {name}" for name in conditions.get(document_id, [])]
                entries.append(
                    TimelineEntry(
                        **self._base(document, "hospital_stays", "", when),
                        title=_join(
                            "Hospital stay", f"at {details['facility_name']}" if details.get("facility_name") else None
                        ),
                        lines=lines,
                    )
                )
            elif kind == "consultation_note":
                summary = summarise_consultation(job, [])
                when = (summary.visit_date, "day") if summary.visit_date else when
                lines = [f"Assessment: {item}" for item in summary.assessment] or [
                    f"Symptoms: {item}" for item in summary.symptoms[:2]
                ]
                entries.append(
                    TimelineEntry(
                        **self._base(document, "consultations", "", when),
                        title=_join("Consultation", f"({summary.clinician_name})" if summary.clinician_name else None),
                        lines=lines,
                    )
                )
            elif kind == "imaging_report":
                summary = summarise_imaging(job)
                when = (summary.exam_date, "day") if summary.exam_date else when
                lines = (
                    [f"Impression: {item}" for item in summary.impression]
                    if summary.is_written_report
                    else ["Scan images only; no written report was read."]
                )
                entries.append(
                    TimelineEntry(
                        **self._base(document, "imaging", "", when),
                        title=summary.exam_name or "Imaging report",
                        lines=lines,
                    )
                )
            elif kind == "test_report":
                summary = summarise_test_report(job)
                when = (summary.test_date, "day") if summary.test_date else when
                lines = [
                    f"{item.source.capitalize()}{' (confirmed)' if item.confirmed else ''}: {item.text}"
                    for item in summary.interpretations
                ]
                flagged = [m for m in summary.measurements if m.flag]
                lines = [f"{m.name} {_join(m.value_text, m.unit)} ({m.flag})" for m in flagged] + lines
                entries.append(
                    TimelineEntry(
                        **self._base(document, "test_reports", "", when),
                        title=summary.test_name or summary.test_type or "Test report",
                        lines=lines,
                        tag=f"{len(flagged)} outside range" if flagged else None,
                    )
                )
            else:
                entries.append(self._plain_document(document, job))
        return entries

    def _plain_document(self, document: Document, job: ProcessingJob | None) -> TimelineEntry:
        tag = "Being read" if job is not None and job.status in ACTIVE_JOB_STATUSES else None
        return TimelineEntry(
            **self._base(document, "documents", "", self._document_date(document, None)),
            title=f"Document: {document.title}",
            tag=tag,
        )

    def _medications(self, user_id: uuid.UUID, documents: dict, entries: list[TimelineEntry]) -> list[TimelineEntry]:
        """Medicines from a prescription are listed in its entry; start/end dates and the user's own medicines
        get entries of their own."""
        medications = list(
            self.session.scalars(
                select(Medication)
                .where(Medication.user_id == user_id, Medication.deleted_at.is_(None))
                .order_by(Medication.position, Medication.created_at)
            )
        )
        edited = MedicationService(self.session).edited_ids(user_id, [m.id for m in medications])
        prescriptions = {e.source_document_id: e for e in entries if e.category == "prescriptions"}
        added = []
        for medication in medications:
            name = _join(medication.name, medication.strength)
            trust = _medication_trust(medication, medication.id in edited)
            entry = prescriptions.get(medication.source_document_id)
            if entry is not None:
                status = _STATUS_WORDS.get(medication.status) if medication.status_confirmed_at else None
                entry.lines.append(
                    _join(name, f"— {medication.dosage_text}" if medication.dosage_text else None)
                    + (f" ({status}, confirmed by you)" if status else "")
                )
            dated = [(medication.start_date, "Started"), (medication.end_date, "Stopped")]
            for when, verb in dated:
                if when is not None:
                    added.append(self._medication_entry(medication, documents, f"{verb} {name}", when, verb, trust))
            if medication.origin == "user_entered" and not medication.start_date and not medication.end_date:
                added.append(self._medication_entry(medication, documents, f"Added {name}", None, "added", trust))
        return added

    @staticmethod
    def _medication_entry(medication, documents, title, when, key, trust) -> TimelineEntry:
        document = documents.get(medication.source_document_id)
        lines = [medication.dosage_text] if medication.dosage_text else []
        return TimelineEntry(
            id=f"medications:{medication.id}:{key}",
            date=when,
            date_precision="day" if when else None,
            category="medications",
            title=title,
            lines=lines,
            trust=trust,
            tag={"active": "Taking", "stopped": "Stopped"}.get(medication.status),
            source_document_id=document.id if document else None,
            source_document_title=document.title if document else None,
            link="/medications",
        )

    def _follow_ups(self, user_id: uuid.UUID, documents: dict) -> list[TimelineEntry]:
        today = datetime.now(UTC).date()
        entries = []
        for follow_up in self.session.scalars(select(FollowUp).where(FollowUp.user_id == user_id)):
            document = documents.get(follow_up.source_document_id)
            if follow_up.status == "scheduled":
                tag = "Overdue" if follow_up.due_date < today else "Upcoming"
            else:
                tag = "Done" if follow_up.status == "completed" else "Cancelled"
            entries.append(
                TimelineEntry(
                    id=f"follow_ups:{follow_up.id}",
                    date=follow_up.due_date,
                    date_precision="day",
                    category="follow_ups",
                    title=f"{follow_up.title} (due)",
                    trust="added_by_you",
                    tag=tag,
                    source_document_id=document.id if document else None,
                    source_document_title=document.title if document else None,
                    link="/follow-ups",
                )
            )
        return entries

    # ---------- public ----------

    def entries(
        self,
        user_id: uuid.UUID,
        categories: set[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[TimelineEntry]:
        """All matching entries, newest first; undated ones last."""
        documents = self._documents(user_id)
        jobs = self._latest_jobs(documents)
        conditions: dict[uuid.UUID, list[str]] = {}
        for condition in self.session.scalars(
            select(Condition)
            .where(
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin == "document_extracted",  # diagnoses as written in the document
            )
            .order_by(Condition.position)
        ):
            conditions.setdefault(condition.source_document_id, []).append(condition.name)

        entries = self._lab_results(user_id, documents, jobs)
        entries += self._reports(documents, jobs, conditions)
        entries += self._medications(user_id, documents, entries)
        entries += self._follow_ups(user_id, documents)

        def keep(entry: TimelineEntry) -> bool:
            if categories and entry.category not in categories:
                return False
            if date_from and (entry.date is None or entry.date < date_from):
                return False
            return not (date_to and (entry.date is None or entry.date > date_to))

        order = {category: index for index, category in enumerate(CATEGORIES)}
        return sorted(
            (entry for entry in entries if keep(entry)),
            key=lambda e: (e.date is None, -(e.date.toordinal() if e.date else 0), order[e.category], e.title),
        )
