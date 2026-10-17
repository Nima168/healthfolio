"""PostgreSQL-backed job queue (backend_spec.md Section 4).

Jobs live in `processing_jobs`. Workers claim them with SELECT … FOR UPDATE SKIP LOCKED,
so several workers can run safely and a job is never processed twice at the same time.
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.extraction import ACTIVE_JOB_STATUSES, Observation, ProcessingJob
from app.models.prescription import Condition, Medication, Suggestion

FINISHED_JOB_STATUSES = ("completed", "completed_with_warnings")

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)  # a running job without a heartbeat for this long is presumed dead
RETRY_DELAYS = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10))


def now() -> datetime:
    return datetime.now(UTC)


def enqueue_extraction(session: Session, document: Document, *, retry: bool = False) -> ProcessingJob:
    """Queue extraction for a document. Called inside the caller's transaction (no commit here)."""
    key = f"extraction:{document.id}" + (f":retry:{uuid.uuid4().hex}" if retry else "")
    job = ProcessingJob(user_id=document.user_id, document_id=document.id, kind="extraction", idempotency_key=key)
    session.add(job)
    document.processing_status = "pending"
    session.flush()
    return job


def latest_job(session: Session, document_id: uuid.UUID) -> ProcessingJob | None:
    return session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


def shown_job(session: Session, document_id: uuid.UUID) -> ProcessingJob | None:
    """The reading whose results are shown: the latest finished one, so a failed or running re-read keeps it.

    A document never read successfully has none; then the latest job (being read, or failed).
    """
    finished = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id, ProcessingJob.status.in_(FINISHED_JOB_STATUSES))
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    return finished or latest_job(session, document_id)


def shown_jobs(session: Session, document_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, ProcessingJob]:
    """`shown_job` for many documents at once."""
    ids = list(document_ids)
    if not ids:
        return {}
    latest: dict[uuid.UUID, ProcessingJob] = {}
    finished: dict[uuid.UUID, ProcessingJob] = {}
    for job in session.scalars(
        select(ProcessingJob).where(ProcessingJob.document_id.in_(ids)).order_by(ProcessingJob.created_at)
    ):
        latest[job.document_id] = job  # ordered oldest first, so the last one wins
        if job.status in FINISHED_JOB_STATUSES:
            finished[job.document_id] = job
    return {**latest, **finished}


def withdraw_earlier_readings(session: Session, job: ProcessingJob) -> None:
    """Replace the document's earlier readings once `job` has succeeded (never before: a failed re-read keeps them).

    Diagnoses the user accepted into the profile, medicines the user changed (re-linked by the new reading),
    and follow-ups already added stay (data_model_spec.md Section 5.6).
    """
    document_id, now_ = job.document_id, now()

    def other(model):
        return or_(model.processing_job_id.is_(None), model.processing_job_id != job.id)

    session.execute(
        update(Observation)
        .where(Observation.source_document_id == document_id, Observation.deleted_at.is_(None), other(Observation))
        .values(deleted_at=now_)
    )
    session.execute(
        update(Condition)
        .where(
            Condition.source_document_id == document_id,
            Condition.deleted_at.is_(None),
            Condition.origin == "document_extracted",
            other(Condition),
        )
        .values(deleted_at=now_)
    )
    session.execute(
        update(Medication)
        .where(
            Medication.source_document_id == document_id,
            Medication.deleted_at.is_(None),
            Medication.user_updated_at.is_(None),
            other(Medication),
        )
        .values(deleted_at=now_)
    )
    session.execute(
        update(Suggestion)
        .where(Suggestion.source_document_id == document_id, Suggestion.status == "pending", other(Suggestion))
        .values(status="superseded")
    )


def claim_next(session: Session) -> ProcessingJob | None:
    """Atomically take the oldest runnable job and mark it running. Commits."""
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.status == "pending", ProcessingJob.run_after <= now())
        .order_by(ProcessingJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        session.rollback()
        return None
    started = now()
    job.status = "running"
    job.attempts += 1
    job.started_at = job.started_at or started
    job.heartbeat_at = started
    job.stage = "claimed"
    _mirror_status(session, job)
    session.commit()
    return job


def heartbeat(session: Session, job: ProcessingJob, stage: str) -> None:
    job.stage = stage
    job.heartbeat_at = now()
    session.commit()


def finish(session: Session, job: ProcessingJob, status: str, error_category: str | None = None) -> None:
    job.status = status
    job.error_category = error_category
    job.completed_at = now()
    job.stage = "done"
    _mirror_status(session, job)


def schedule_retry(session: Session, job: ProcessingJob, error_category: str, max_attempts: int) -> bool:
    """Put a transiently failed job back in the queue with backoff. Returns False when attempts are used up."""
    if job.attempts >= max_attempts:
        finish(session, job, "failed", error_category)
        return False
    delay = RETRY_DELAYS[min(job.attempts - 1, len(RETRY_DELAYS) - 1)]
    job.status = "pending"
    job.error_category = error_category
    job.run_after = now() + delay
    job.stage = "waiting_to_retry"
    _mirror_status(session, job)
    return True


def recover_stale(session: Session) -> int:
    """Return jobs abandoned by a crashed worker to the queue (backend_spec.md Section 9.4). Commits."""
    cutoff = now() - STALE_AFTER
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.status == "running",
            or_(ProcessingJob.heartbeat_at.is_(None), ProcessingJob.heartbeat_at < cutoff),
        )
        .values(status="pending", run_after=now(), stage="recovered")
    )
    session.commit()
    if result.rowcount:
        logger.warning("recovered stale jobs", extra={"count": result.rowcount})
    return result.rowcount


def cancel_active_jobs(session: Session, document_id: uuid.UUID) -> None:
    """Used when a document is deleted. A running job notices on its next step and stops."""
    session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.document_id == document_id, ProcessingJob.status.in_(ACTIVE_JOB_STATUSES))
        .values(status="cancelled", completed_at=now(), stage="cancelled")
    )


def _mirror_status(session: Session, job: ProcessingJob) -> None:
    """The document shows the state of its latest job."""
    document = session.get(Document, job.document_id)
    if document is not None and document.deleted_at is None:
        document.processing_status = job.status
