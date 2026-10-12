"""Background worker: processes queued extraction jobs (backend_spec.md Section 4).

Run:  uv run python -m app.worker          (keeps running)
      uv run python -m app.worker --once   (processes what is queued, then exits)
"""

import argparse
import logging
import signal
import sys
import time
from collections.abc import Callable

from app.ai.extractor import GroqExtractor, make_client
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.services import jobs
from app.services.extraction_service import ExtractionRunner
from app.services.storage import get_document_storage

logger = logging.getLogger("app.worker")


class Worker:
    def __init__(self, settings: Settings, extractor: GroqExtractor) -> None:
        self.settings = settings
        self.extractor = extractor
        self.storage = get_document_storage(settings)
        self.stopping = False

    def process_one(self) -> bool:
        """Claim and run one job. Returns False when nothing is waiting."""
        session = get_session_factory()()
        try:
            job = jobs.claim_next(session)
            if job is None:
                return False
            ExtractionRunner(session, self.settings, self.storage, self.extractor).run(job)
            return True
        finally:
            session.close()

    def recover(self) -> None:
        session = get_session_factory()()
        try:
            jobs.recover_stale(session)
        finally:
            session.close()

    def run(self, *, once: bool = False, sleep: Callable[[float], None] = time.sleep) -> int:
        self.recover()
        processed = 0
        while not self.stopping:
            if self.process_one():
                processed += 1
                continue
            if once:
                break
            sleep(self.settings.worker_poll_seconds)
        return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process queued document extraction jobs.")
    parser.add_argument("--once", action="store_true", help="process queued jobs, then exit")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.app_env.value)
    if not settings.extraction_enabled:
        logger.error("extraction is disabled; set EXTRACTION_ENABLED=true to run the worker")
        return 2
    if settings.groq_api_key is None:
        logger.error("GROQ_API_KEY is not set; the worker cannot call the AI provider")
        return 2

    worker = Worker(settings, GroqExtractor(make_client(settings), settings))

    def stop(*_: object) -> None:
        logger.info("worker stopping after the current job")
        worker.stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    logger.info("worker started", extra={"model": settings.ai_model, "once": args.once})
    processed = worker.run(once=args.once)
    logger.info("worker stopped", extra={"jobs_processed": processed})
    return 0


if __name__ == "__main__":
    sys.exit(main())
