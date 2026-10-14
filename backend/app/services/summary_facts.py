"""What an AI summary may say: the user's records as numbered facts, and gaps found by fixed rules.

The model sees only these facts (AI_spec.md Section 6). Each has an id the summary must cite, so every
sentence can be traced back to a record. Names, email, date of birth, and document titles are not sent.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.alerts import Alert
from app.models.document import Document
from app.models.prescription import Medication
from app.services.dashboard_service import DashboardService
from app.services.profile_service import ProfileService
from app.services.timeline_service import TimelineEntry, TimelineService

MAX_RECORD_FACTS = 120  # newest first; keeps the request well inside the model's context
STALE_LAB_DAYS = 365

TRUST = {
    "from_document": "read from a document, not checked by the user",
    "confirmed_by_you": "confirmed by the user",
    "edited_by_you": "changed by the user",
    "added_by_you": "added by the user",
}
PROFILE_LABELS = {"date_of_birth": "date of birth", "sex": "sex", "blood_group": "blood group"}


@dataclass
class Fact:
    id: str
    kind: str
    title: str
    date: str | None = None
    details: list[str] = field(default_factory=list)
    trust: str | None = None
    # Shown to the user with the citation; never sent to the model.
    source_document_id: str | None = None
    source_document_title: str | None = None
    link: str | None = None

    def for_model(self) -> dict:
        data = {"id": self.id, "kind": self.kind, "title": self.title, "date": self.date or "not mentioned"}
        if self.details:
            data["details"] = self.details
        if self.trust:
            data["source"] = TRUST.get(self.trust, self.trust)
        return data

    def reference(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k not in ("id", "details")}


@dataclass
class Facts:
    records: list[Fact]
    checks: list[Fact]  # gaps and items to review, found by fixed rules (insights)

    @property
    def all(self) -> list[Fact]:
        return self.records + self.checks

    def fingerprint(self) -> str:
        """Changes whenever the facts change, so an older summary can be marked out of date."""
        payload = json.dumps([f.for_model() for f in self.all], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def insights(self) -> list[dict]:
        return [{"id": f.id, "text": f.title, "link": f.link} for f in self.checks]


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _entry_fact(index: int, entry: TimelineEntry) -> Fact:
    return Fact(
        id=f"F{index}",
        kind=entry.category,
        title=entry.title,
        date=entry.date.isoformat() if entry.date else None,
        details=[line for line in entry.lines if line],
        trust=entry.trust,
        source_document_id=str(entry.source_document_id) if entry.source_document_id else None,
        source_document_title=entry.source_document_title,
        link=entry.link,
    )


class SummaryFacts:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------- whole history ----------

    def history(self, user_id: uuid.UUID) -> Facts:
        entries = TimelineService(self.session).entries(user_id)
        records = [_entry_fact(i, e) for i, e in enumerate(entries[:MAX_RECORD_FACTS], start=1)]
        records += self._profile(user_id, start=len(records) + 1)
        return Facts(records=records, checks=self._history_checks(user_id, entries))

    def _profile(self, user_id: uuid.UUID, start: int) -> list[Fact]:
        data = ProfileService(self.session).profile(user_id)
        facts: list[Fact] = []

        def add(kind: str, title: str, when: date | None = None, details: list[str] | None = None) -> None:
            facts.append(
                Fact(
                    id=f"F{start + len(facts)}",
                    kind=kind,
                    title=title,
                    date=when.isoformat() if when else None,
                    details=details or [],
                    trust="added_by_you",
                    link="/profile",
                )
            )

        for condition in data["conditions"]:
            add(
                "condition",
                f"Condition in the health profile: {condition.name}",
                details=[f"status: {condition.status}"],
            )
        for allergy in data["allergies"]:
            details = [
                d
                for d in (
                    allergy.category and f"type: {allergy.category}",
                    allergy.detail and f"reaction: {allergy.detail}",
                )
                if d
            ]
            add("allergy", f"Allergy: {allergy.value}", details=details)
        for item in data["surgeries"]:
            add("surgery", f"Past surgery: {item.name}", item.occurred_on)
        for item in data["hospitalizations"]:
            add("hospitalization", f"Hospital stay: {item.name}", item.occurred_on)
        for item in data["family_history"]:
            add("family_history", f"Family history: {item.name}", details=[f"relative: {item.relation}"])
        if data["bmi"] is not None:
            category = data["bmi_category"] or "no adult category (under 18 or age not given)"
            add("bmi", f"BMI {data['bmi']} (calculated from height and weight)", details=[f"category: {category}"])
        values = data["values"]
        for name in ("sex", "blood_group"):
            if values.get(name):
                add("profile", f"{PROFILE_LABELS[name].capitalize()}: {values[name].value}")
        return facts

    def _history_checks(self, user_id: uuid.UUID, entries: list[TimelineEntry]) -> list[Fact]:
        overview = DashboardService(self.session).overview(user_id)
        alerts, review = overview["alerts"], overview["review"]
        to_add = sum(count for _, count in review["follow_ups_to_add"])
        rules = [
            (alerts["open"], "result is", "results are", "outside the range printed on their own report, "
             "waiting for review.", "/alerts"),
            (len(overview["follow_ups"]["overdue"]), "follow-up is", "follow-ups are",
             "past their date and not marked done.", "/follow-ups"),
            (review["unconfirmed_medicines"], "medicine", "medicines",
             "read from documents not yet confirmed as taking or stopped.", "/medications"),
            (review["profile_suggestions"], "diagnosis", "diagnoses",
             "from documents waiting for review in the Health Profile.", "/profile"),
            (to_add, "follow-up", "follow-ups",
             "from documents not yet added to Checkups and Follow-ups.", "/documents"),
            (len(review["failed_documents"]), "document", "documents", "could not be read.", "/documents"),
            (overview["documents"]["reading"], "document is", "documents are",
             "still being read and not included yet.", "/documents"),
        ]  # fmt: skip
        checks = [(f"{_plural(count, one, many)} {text}", link) for count, one, many, text, link in rules if count]

        lab_dates = [e.date for e in entries if e.category == "lab_results" and e.date]
        if not lab_dates:
            checks.append(("No dated lab results in the records yet.", "/documents"))
        elif max(lab_dates) < datetime.now(UTC).date() - timedelta(days=STALE_LAB_DAYS):
            latest = max(lab_dates).isoformat()
            checks.append((f"The most recent lab result is from {latest}, more than a year ago.", "/timeline"))
        missing = [PROFILE_LABELS.get(f, f) for f in overview["profile"]["missing"]]
        if missing:
            checks.append((f"Health Profile details not given: {', '.join(missing)}.", "/profile"))
        return _checks(checks)

    # ---------- one document ----------

    def document(self, user_id: uuid.UUID, document: Document) -> Facts:
        entries = [e for e in TimelineService(self.session).entries(user_id) if e.source_document_id == document.id]
        records = [_entry_fact(i, e) for i, e in enumerate(entries[:MAX_RECORD_FACTS], start=1)]
        return Facts(records=records, checks=self._document_checks(user_id, document))

    def _document_checks(self, user_id: uuid.UUID, document: Document) -> list[Fact]:
        alerts = self.session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.user_id == user_id, Alert.source_document_id == document.id, Alert.status == "open")
        )
        unconfirmed = self.session.scalar(
            select(func.count())
            .select_from(Medication)
            .where(
                Medication.user_id == user_id,
                Medication.source_document_id == document.id,
                Medication.deleted_at.is_(None),
                Medication.status == "unknown",
            )
        )
        rules = [
            (alerts, "result is", "results are", "outside the range printed on this report, waiting for review.",
             "/alerts"),
            (unconfirmed, "medicine", "medicines", "from this document not yet confirmed as taking or stopped.",
             "/medications"),
        ]  # fmt: skip
        return _checks(
            [(f"{_plural(count, one, many)} {text}", link) for count, one, many, text, link in rules if count]
        )


def _checks(items: list[tuple[str, str]]) -> list[Fact]:
    return [Fact(id=f"C{i}", kind="check", title=text, link=link) for i, (text, link) in enumerate(items, start=1)]
