"""Safety alerts (backend_spec.md Section 7.5): approved rules decide, deterministically; nothing here uses AI.

Rule RESULT_OUTSIDE_REPORT_RANGE v1: a plain-number result outside the reference range printed on the same
report raises a "warning" alert for review (not a diagnosis). Discharge summaries: only each test's last value.

Alerts are kept in step with the records (`sync`): a new out-of-range result raises one; when its source
disappears (document deleted or read again without it) the system resolves it; if it comes back, the system
reopens it. Alerts the user resolved stay resolved. The absence of an alert never means everything is fine.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.alerts import Alert, AlertEvent, SafetyRule
from app.models.document import Document
from app.models.extraction import Observation
from app.repositories.auth import AuditRepository
from app.services import jobs as job_queue
from app.services.lab_summary import classify
from app.services.report_summaries import summarise_specialist, summarise_test_report

logger = logging.getLogger(__name__)

OUT_OF_RANGE = "RESULT_OUTSIDE_REPORT_RANGE"
_COMPLETED = ("completed", "completed_with_warnings")

NEXT_STEPS = (
    "Discuss this result with your doctor, especially if it has not already been explained to you. "
    "Do not start, stop, or change any treatment because of this alert alone. "
    "If you feel unwell or are worried, contact your doctor; in an emergency, call your local emergency number."
)
UNCERTAINTY = (
    "Reference ranges differ between laboratories and can depend on age, sex, and how the sample was taken. "
    "One result outside the range can have many causes and is not a diagnosis."
)
SOURCE_GONE = "The result is no longer in your records (its document was deleted or read again without it)."


@dataclass
class Candidate:
    key: str
    document: Document
    title: str
    reason: str
    uncertainty: str
    refs: dict = field(default_factory=dict)


def _value(value_text: str, unit: str | None) -> str:
    return f"{value_text} {unit}" if unit else value_text


def _candidate(
    document: Document,
    name: str,
    value_text: str,
    unit: str | None,
    range_text: str,
    direction: str,
    when: object,
    refs: dict,
    extra_uncertainty: str | None = None,
) -> Candidate:
    word, comparison = ("above", "higher") if direction == "above" else ("below", "lower")
    value = _value(value_text, unit)
    return Candidate(
        key=f"{document.id}|{' '.join(name.casefold().split())}|{value_text.strip()}|{when or ''}",
        document=document,
        title=f"{name} {value} is {word} the report's range ({range_text})",
        reason=(
            f"The report gives {range_text} as the reference range for {name}. "
            f"The result, {value}, is {comparison} than that range. "
            "This is a rule-based flag for review, not a diagnosis."
        ),
        uncertainty=" ".join(part for part in (extra_uncertainty, UNCERTAINTY) if part),
        refs=refs | {"result_date": str(when) if when else None},  # the result's own date, for filtering
    )


class AlertService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditRepository(session)

    def _rule(self) -> SafetyRule | None:
        return self.session.scalar(
            select(SafetyRule)
            .where(SafetyRule.code == OUT_OF_RANGE, SafetyRule.active.is_(True))
            .order_by(SafetyRule.version.desc())
            .limit(1)
        )

    # ---------- the rule ----------

    def _candidates(self, user_id: uuid.UUID) -> dict[str, Candidate]:
        documents = {
            d.id: d
            for d in self.session.scalars(
                select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))
            )
        }
        if not documents:
            return {}
        # The shown reading: a failed or running re-read keeps the last successful one.
        shown = job_queue.shown_jobs(self.session, documents)
        completed = {doc_id: job for doc_id, job in shown.items() if job.status in _COMPLETED}

        found: dict[str, Candidate] = {}
        rows = self.session.scalars(
            select(Observation).where(
                Observation.user_id == user_id,
                Observation.deleted_at.is_(None),
                Observation.source_document_id.in_(list(completed)),
            )
        )
        by_document: dict[uuid.UUID, list[Observation]] = {}
        for row in rows:
            by_document.setdefault(row.source_document_id, []).append(row)

        for document_id, observations in by_document.items():
            document, job = documents[document_id], completed[document_id]
            discharge = job.document_kind == "discharge_summary"
            if discharge:  # only each test's last value: the state at discharge
                last: dict[str, Observation] = {}
                for row in sorted(observations, key=lambda r: (r.observed_at is not None, r.observed_at or 0)):
                    last[row.name.casefold()] = row
                observations = list(last.values())
            for row in observations:
                status, _ = classify(row)
                if status not in ("above", "below"):
                    continue  # within range, or not comparable (no range, not a number, unclear): no alert
                candidate = _candidate(
                    document,
                    row.name,
                    row.value_text,
                    row.unit,
                    (row.reference_range_text or "").strip(),
                    status,
                    row.observed_at,
                    {"observation_id": str(row.id), "document_id": str(document.id)},
                    "This was the last value recorded before discharge." if discharge else None,
                )
                found[candidate.key] = candidate

        for document_id, job in completed.items():
            # Measurements in other test reports and specialist reports, against their printed range.
            if job.document_kind == "test_report":
                summary = summarise_test_report(job)
            elif job.document_kind == "specialist_report":
                summary = summarise_specialist(job, [])
            else:
                continue
            for index, measurement in enumerate(summary.measurements):
                if measurement.flag not in ("high", "low") or not measurement.reference_range_text:
                    continue
                candidate = _candidate(
                    documents[document_id],
                    measurement.name,
                    measurement.value_text,
                    measurement.unit,
                    measurement.reference_range_text,
                    "above" if measurement.flag == "high" else "below",
                    summary.test_date,
                    {"document_id": str(document_id), "measurement": index, "processing_job_id": str(job.id)},
                )
                found[candidate.key] = candidate
        return found

    # ---------- keeping alerts in step ----------

    def _event(self, alert: Alert, event: str, actor: str, now: datetime, note: str | None = None) -> None:
        self.session.add(AlertEvent(alert_id=alert.id, event=event, actor=actor, note=note, occurred_at=now))

    def sync(self, user_id: uuid.UUID) -> None:
        """Apply the rule to the user's current records. Idempotent; the caller commits."""
        rule = self._rule()
        if rule is None:
            logger.warning("no active safety rule", extra={"rule": OUT_OF_RANGE})
            return
        now = datetime.now(UTC)
        candidates = self._candidates(user_id)
        existing = {
            alert.input_key: alert
            for alert in self.session.scalars(select(Alert).where(Alert.user_id == user_id, Alert.rule_id == rule.id))
        }

        for key, candidate in candidates.items():
            alert = existing.get(key)
            if alert is None:
                alert = Alert(
                    user_id=user_id,
                    rule_id=rule.id,
                    rule_version=rule.version,
                    severity=rule.severity,
                    status="open",
                    input_key=key,
                    input_refs=candidate.refs,
                    source_document_id=candidate.document.id,
                    title=candidate.title,
                    reason=candidate.reason,
                    uncertainty=candidate.uncertainty,
                    next_steps=NEXT_STEPS,
                )
                self.session.add(alert)
                self.session.flush()
                self._event(alert, "raised", "system", now)
                self.audit.record("alert.raised", "success", user_id, {"alert_id": str(alert.id), "rule": rule.code})
                continue
            alert.input_refs = candidate.refs  # the same result, possibly re-read
            if alert.status == "resolved" and alert.resolved_by == "system":
                alert.status = "acknowledged" if alert.acknowledged_at else "open"
                alert.resolved_at = alert.resolved_by = alert.resolution_note = None
                self._event(alert, "reopened", "system", now, "The result is in your records again.")

        for key, alert in existing.items():
            if key not in candidates and alert.status != "resolved":
                alert.status = "resolved"
                alert.resolved_at = now
                alert.resolved_by = "system"
                alert.resolution_note = SOURCE_GONE
                self._event(alert, "resolved", "system", now, SOURCE_GONE)

    def try_sync(self, user_id: uuid.UUID) -> None:
        """`sync` inside a savepoint, for callers whose own work must not fail because of alerts
        (reading or deleting a document). A failure is logged; the next `list_alerts` call catches up."""
        try:
            with self.session.begin_nested():
                self.sync(user_id)
        except Exception:
            logger.exception("alert evaluation failed; it will be retried when alerts are listed")

    # ---------- the user's actions ----------

    def list_alerts(self, user_id: uuid.UUID) -> list[tuple[Alert, Document | None, list[AlertEvent]]]:
        self.sync(user_id)
        self.session.commit()
        alerts = list(
            self.session.scalars(
                select(Alert)
                .where(Alert.user_id == user_id)
                .order_by(
                    case((Alert.status == "open", 0), (Alert.status == "acknowledged", 1), else_=2),
                    case((Alert.severity == "urgent", 0), (Alert.severity == "warning", 1), else_=2),
                    Alert.created_at.desc(),
                )
            )
        )
        return [self._with_details(alert) for alert in alerts]

    def _with_details(self, alert: Alert) -> tuple[Alert, Document | None, list[AlertEvent]]:
        document = self.session.get(Document, alert.source_document_id) if alert.source_document_id else None
        events = list(
            self.session.scalars(
                select(AlertEvent).where(AlertEvent.alert_id == alert.id).order_by(AlertEvent.occurred_at)
            )
        )
        return alert, document, events

    def change_status(self, user_id: uuid.UUID, alert_id: uuid.UUID, status: str, note: str | None):
        """open → acknowledged → resolved, or open → resolved. Resolved is final for the user."""
        alert = self.session.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id))
        if alert is None:
            raise ApiError(404)
        allowed = {"open": ("acknowledged", "resolved"), "acknowledged": ("resolved",), "resolved": ()}
        if status not in allowed[alert.status]:
            raise ApiError(
                409,
                "INVALID_TRANSITION",
                f"An alert that is {alert.status} cannot be marked {status}.",
            )
        now = datetime.now(UTC)
        if status == "acknowledged":
            alert.acknowledged_at = now
        else:
            alert.resolved_at = now
            alert.resolved_by = "user"
            alert.resolution_note = note
        alert.status = status
        self._event(alert, status, "user", now, note)
        self.audit.record("alert.updated", "success", user_id, {"alert_id": str(alert.id), "status": status})
        self.session.commit()
        return self._with_details(alert)
