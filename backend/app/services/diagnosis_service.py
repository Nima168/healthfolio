"""Diagnoses and Conditions: health issues written in the user's documents, tracked across documents.

Deterministic, from stored readings only; nothing is inferred or worded by the AI here:
- discharge summaries: each diagnosis as written ("diagnosis");
- consultation notes: each assessment statement ("assessment");
- imaging reports (written reports only): each impression statement ("impression");
- pathology reports: each written diagnosis ("diagnosis", stored like discharge diagnoses);
- specialist and other test reports (ECG, echo, ...): each conclusion or interpretation ("assessment").
The same wording in several documents is one entry (case and spacing ignored), with the first and last
date it was written and every document it came from. Normal findings ("Normal heart size.") are marked so the
page can keep them apart. Lab values outside their range are not diagnoses; they stay in Alerts.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.readability import NOT_IDENTIFIED
from app.models.document import Document
from app.models.extraction import ProcessingJob
from app.models.prescription import Condition
from app.services.profile_service import ProfileService
from app.services.report_summaries import (
    summarise_consultation,
    summarise_imaging,
    summarise_specialist,
    summarise_test_report,
)

_COMPLETED = ("completed", "completed_with_warnings")


def issue_key(text: str) -> str:
    """Same wording, ignoring case, spacing, and a closing full stop."""
    return " ".join(text.casefold().split()).rstrip(" .;")


# Normal findings (decision 2026-10-17). Cautious: when in doubt a statement stays a health issue.
_CONTRAST = re.compile(r"\b(but|however|except|although|though|yet|while|whereas)\b|;", re.IGNORECASE)
_NEGATIVE = re.compile(r"^(no|negative for|without|nil)\b", re.IGNORECASE)
# "No improvement", "No new lesions", "No residual stone": about a problem, so not normal.
_NEGATIVE_PROBLEM = re.compile(r"\b(improv|change|response|resol|longer|further|new|interval|residual|recurr)", re.I)
_POSITIVE = re.compile(
    r"^(normal|unremarkable|within normal limits)\b"
    r"|\b(is|are) (normal|clear|unremarkable)\.?$"
    r"|\bwithin normal limits\.?$",
    re.IGNORECASE,
)
_PROBLEM = re.compile(
    r"\b(mild|moderate|severe|small|large|enlarged|abnormal|reduced|increased|decreased|lesion|mass|nodule|cyst|"
    r"effusion|fracture|suspicious|possible|probable|likely|degenerat|hernia|stenosis|bulge|infection|thicken|"
    r"calcif|elevat|borderline|high|low)",
    re.IGNORECASE,
)


def is_normal_finding(text: str) -> bool:
    """A statement that reports nothing wrong: "Normal heart size.", "No acute fracture.", "Lungs are clear."

    Never one with a contrast ("Normal heart size but mild effusion", "...; small cyst"), a "No ..." about a
    problem's course ("No improvement"), or a positive statement naming a problem ("Kidneys are normal in size,
    small cyst").
    """
    text = text.strip()
    if _CONTRAST.search(text):
        return False
    if _NEGATIVE.match(text):
        return not _NEGATIVE_PROBLEM.search(text)
    return bool(_POSITIVE.search(text)) and not _PROBLEM.search(text)


@dataclass
class Mention:
    text: str
    kind: str  # "diagnosis", "assessment", or "impression"
    document_id: uuid.UUID
    document_title: str | None
    date: date | None


@dataclass
class HealthIssue:
    name: str
    mentions: list[Mention] = field(default_factory=list)
    # "in_profile" (with condition_status), "to_review" (a diagnosis suggested in Health Profile), or "not_in_profile"
    profile: str = "not_in_profile"
    condition_status: str | None = None

    @property
    def kinds(self) -> list[str]:
        return sorted({mention.kind for mention in self.mentions})

    @property
    def normal(self) -> bool:
        """A normal finding: never a written diagnosis, only assessments or impressions that report nothing wrong."""
        return all(m.kind != "diagnosis" and is_normal_finding(m.text) for m in self.mentions)

    @property
    def first_seen(self) -> date | None:
        return min((m.date for m in self.mentions if m.date), default=None)

    @property
    def last_seen(self) -> date | None:
        return max((m.date for m in self.mentions if m.date), default=None)


class DiagnosisService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def issues(self, user_id: uuid.UUID) -> list[HealthIssue]:
        """Most recently written first; issues with no date last."""
        documents = {
            d.id: d
            for d in self.session.scalars(
                select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))
            )
        }
        jobs: dict[uuid.UUID, ProcessingJob] = {}
        if documents:
            for job in self.session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id.in_(list(documents)))
                .order_by(ProcessingJob.created_at)
            ):
                jobs[job.document_id] = job  # the latest reading wins

        mentions: list[Mention] = []
        for condition in self.session.scalars(
            select(Condition)
            .where(
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin == "document_extracted",
            )
            .order_by(Condition.position)
        ):
            document = documents.get(condition.source_document_id)
            if document is not None:
                mentions.append(self._mention(condition.name, "diagnosis", document, jobs.get(document.id)))

        for document_id, job in jobs.items():
            if job.status not in _COMPLETED:
                continue
            document = documents[document_id]
            if job.document_kind == "consultation_note":
                summary = summarise_consultation(job, [])
                for text in summary.assessment:
                    mentions.append(self._mention(text, "assessment", document, job, summary.visit_date))
            elif job.document_kind == "imaging_report":
                summary = summarise_imaging(job)
                if summary.is_written_report:
                    for text in summary.impression:
                        mentions.append(self._mention(text, "impression", document, job, summary.exam_date))
            elif job.document_kind in ("specialist_report", "test_report"):
                test = summarise_specialist(job, []) if job.document_kind == "specialist_report" else None
                conclusions = test.conclusions if test else summarise_test_report(job).interpretations
                tested_on = test.test_date if test else summarise_test_report(job).test_date
                for item in conclusions:
                    if item.text != NOT_IDENTIFIED:
                        mentions.append(self._mention(item.text, "assessment", document, job, tested_on))

        issues: dict[str, HealthIssue] = {}
        for mention in mentions:
            issue = issues.setdefault(issue_key(mention.text), HealthIssue(name=mention.text))
            issue.mentions.append(mention)
        self._profile_status(user_id, issues)

        for issue in issues.values():
            issue.mentions.sort(key=lambda m: (m.date is None, -(m.date.toordinal() if m.date else 0)))
            issue.name = issue.mentions[0].text  # the most recent wording
        return sorted(
            issues.values(),
            key=lambda i: (i.last_seen is None, -(i.last_seen.toordinal() if i.last_seen else 0), i.name.casefold()),
        )

    @staticmethod
    def _mention(
        text: str, kind: str, document: Document, job: ProcessingJob | None, written_on: date | None = None
    ) -> Mention:
        when = written_on or (job.document_date if job else None) or document.document_date
        return Mention(text=text, kind=kind, document_id=document.id, document_title=document.title, date=when)

    def _profile_status(self, user_id: uuid.UUID, issues: dict[str, HealthIssue]) -> None:
        for condition in self.session.scalars(
            select(Condition).where(
                Condition.user_id == user_id,
                Condition.deleted_at.is_(None),
                Condition.origin != "document_extracted",
            )
        ):
            if (issue := issues.get(issue_key(condition.name))) is not None:
                issue.profile, issue.condition_status = "in_profile", condition.status
        for suggestion, _ in ProfileService(self.session).suggestions(user_id):
            issue = issues.get(issue_key(suggestion.name))
            if issue is not None and issue.profile == "not_in_profile":
                issue.profile = "to_review"
