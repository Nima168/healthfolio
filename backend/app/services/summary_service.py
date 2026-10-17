"""AI summaries: collect facts, ask the model, keep only what the facts support, and store the result.

Written on request (not automatically), so nothing is sent to the AI provider unless the user asks.
"""

import logging
import time
import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.ai.extractor import ChatClient, ExtractionError, GroqExtractor, Task
from app.ai.summary import SUMMARY_PROMPT_VERSION, SUMMARY_SCHEMA, SYSTEM_PROMPT, SummaryPayload, build_request, check
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.document import Document
from app.models.summary import AiSummary
from app.repositories.auth import AuditRepository
from app.services import jobs
from app.services.summary_facts import Facts, SummaryFacts

logger = logging.getLogger(__name__)

SUMMARY_TASK = Task("health_summary", SUMMARY_PROMPT_VERSION, SYSTEM_PROMPT, "", SUMMARY_SCHEMA, SummaryPayload)
_READ = ("completed", "completed_with_warnings")

_FAILURES = {
    "ai_not_configured": "AI summaries are not set up on this server.",
    "ai_unavailable": "The AI service is busy or unreachable. Please try again in a minute.",
    "ai_request_too_large": "There is too much to summarise in one request for the AI service. Please contact support.",
}


class SummaryService:
    def __init__(self, session: Session, settings: Settings, client: ChatClient | None = None) -> None:
        self.session = session
        self.settings = settings
        self.client = client
        self.facts = SummaryFacts(session)

    @property
    def enabled(self) -> bool:
        return self.settings.extraction_enabled  # the same switch as document reading: both send data to the AI

    # ---------- read ----------

    def latest(self, user_id: uuid.UUID, document_id: uuid.UUID | None = None) -> AiSummary | None:
        return self.session.scalar(
            select(AiSummary)
            .where(
                AiSummary.user_id == user_id,
                AiSummary.scope == ("document" if document_id else "history"),
                AiSummary.document_id == document_id if document_id else AiSummary.document_id.is_(None),
            )
            .order_by(AiSummary.created_at.desc())
            .limit(1)
        )

    def current_facts(self, user_id: uuid.UUID, document: Document | None = None) -> Facts:
        return self.facts.document(user_id, document) if document else self.facts.history(user_id)

    def readable(self, document: Document) -> bool:
        job = jobs.shown_job(self.session, document.id)
        return job is not None and job.status in _READ

    # ---------- write ----------

    def create(self, user_id: uuid.UUID, document: Document | None = None) -> AiSummary:
        if not self.enabled:
            raise ApiError(503, message="AI summaries are turned off on this server.")
        if document is not None and not self.readable(document):
            raise ApiError(409, message="This document has not been read yet, so there is nothing to summarise.")
        facts = self.current_facts(user_id, document)
        if not facts.records:
            raise ApiError(409, message="There are no records to summarise yet.")
        if self.client is None:
            raise ApiError(503, message=_FAILURES["ai_not_configured"])

        scope = "document" if document else "history"
        started = time.perf_counter()
        try:
            payload, model, input_tokens, output_tokens = GroqExtractor(self.client, self.settings).call(
                build_request(facts, self.settings, scope=scope), SUMMARY_TASK
            )
        except ExtractionError as exc:
            logger.warning("summary failed", extra={"reason": exc.category, "scope": scope})
            raise ApiError(
                503, message=_FAILURES.get(exc.category, "The summary could not be written. Please try again.")
            ) from exc

        checked = check(payload, facts)
        # IDs, counts, and timings only: never facts, prompts, or the summary text.
        logger.info(
            "summary written",
            extra={
                "scope": scope,
                "facts": len(facts.all),
                "dropped": checked.dropped,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        if checked.empty:
            raise ApiError(503, message="The summary could not be matched to your records. Please try again.")

        summary = AiSummary(
            user_id=user_id,
            scope=scope,
            document_id=document.id if document else None,
            content={"sections": checked.sections},
            source_refs={fact.id: fact.reference() for fact in facts.all},
            general_knowledge_sections=checked.explanations,
            insights=facts.insights(),
            dropped_count=checked.dropped,
            fingerprint=facts.fingerprint(),
            model_version=model,
            prompt_version=SUMMARY_PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.session.add(summary)
        self.session.flush()
        AuditRepository(self.session).record(
            "ai.summary_created", "success", user_id, {"summary_id": str(summary.id), "scope": scope}
        )
        self.session.commit()
        return summary


def forget_document(session: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """A deleted document's text must not live on in summaries: its own and every whole-history one go."""
    session.execute(
        delete(AiSummary).where(
            AiSummary.user_id == user_id,
            or_(AiSummary.document_id == document_id, AiSummary.scope == "history"),
        )
    )


def is_stale(summary: AiSummary, facts: Facts) -> bool:
    return summary.fingerprint != facts.fingerprint()
