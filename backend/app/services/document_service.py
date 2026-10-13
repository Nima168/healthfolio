"""Document business rules (api_contract_spec.md Section 6.1.2)."""

import base64
import binascii
import hashlib
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.document import Document
from app.models.extraction import Observation
from app.models.prescription import Condition, Medication, Suggestion
from app.repositories.auth import AuditRepository
from app.repositories.documents import DocumentFilters, DocumentRepository
from app.schemas.documents import DocumentUpdate, normalise_date
from app.services import jobs, summary_service, upload_quality
from app.services.alert_service import AlertService
from app.services.document_validation import SNIFF_BYTES, detect_media_type, sanitise_filename
from app.services.storage import CHUNK_SIZE, DocumentStorage, StorageError, storage_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadMetadata:
    title: str = ""
    category: str | None = None
    document_date: object = None  # datetime.date | None
    document_date_precision: str | None = None
    provider_name: str | None = None


def _not_found() -> ApiError:
    return ApiError(404)


def _storage_unavailable() -> ApiError:
    return ApiError(503, message="Document storage is temporarily unavailable. Please try again.")


def encode_cursor(document: Document) -> str:
    raw = f"{document.created_at.isoformat()}|{document.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, document_id = base64.urlsafe_b64decode(padded).decode().split("|")
        return datetime.fromisoformat(created_at), uuid.UUID(document_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ApiError(422, details=[{"field": "cursor", "issue": "Invalid cursor."}]) from exc


class DocumentService:
    def __init__(self, session: Session, settings: Settings, storage: DocumentStorage) -> None:
        self.session = session
        self.settings = settings
        self.storage = storage
        self.documents = DocumentRepository(session)
        self.audit = AuditRepository(session)

    # ---------- upload ----------

    def upload(self, user_id: uuid.UUID, file: BinaryIO, filename: str | None, metadata: UploadMetadata) -> Document:
        size, sha256, head = self._measure(file)
        if size == 0:
            raise ApiError(422, details=[{"field": "file", "issue": "The file is empty."}])
        if size > self.settings.max_upload_mb * 1024 * 1024:
            raise ApiError(413)
        media_type = detect_media_type(head)
        if media_type is None:
            raise ApiError(415, message="Only PDF, JPEG, and PNG files are supported.")

        self._raise_if_duplicate(user_id, sha256)
        file.seek(0)
        self._check_readable(file.read(), media_type, metadata.category)

        document_date, precision = normalise_date(metadata.document_date, metadata.document_date_precision)
        document = Document(
            id=uuid.uuid4(),
            user_id=user_id,
            title=metadata.title,
            original_filename=sanitise_filename(filename, media_type),
            media_type=media_type,
            size_bytes=size,
            sha256=sha256,
            category=metadata.category or "unknown",
            provider_name=metadata.provider_name,
            document_date=document_date,
            document_date_precision=precision,
        )
        document.storage_key = storage_key(user_id, document.id)

        file.seek(0)
        try:
            self.storage.save(document.storage_key, iter(lambda: file.read(CHUNK_SIZE), b""))
        except StorageError as exc:
            raise _storage_unavailable() from exc

        try:
            self.documents.add(document)
            # Queued in the same transaction: a stored document always has its extraction job.
            jobs.enqueue_extraction(self.session, document)
            self.audit.record("document.uploaded", "success", user_id, {"document_id": str(document.id)})
            self.session.commit()
        except IntegrityError as exc:  # the same file uploaded twice at the same moment
            self.session.rollback()
            self._remove_file_quietly(document.storage_key)
            self._raise_if_duplicate(user_id, sha256)
            raise ApiError(409) from exc
        except Exception:
            self.session.rollback()
            self._remove_file_quietly(document.storage_key)
            raise
        return document

    @staticmethod
    def _check_readable(content: bytes, media_type: str, category: str | None) -> None:
        """Unclear photos and scans are sent back for a better copy; discharge summaries are one page."""
        report = upload_quality.check(content, media_type)
        if report.problem:
            raise ApiError(422, details=[{"field": "file", "issue": report.message()}])
        if category == "discharge_summary" and (report.page_count or 0) > 1:
            raise ApiError(422, details=[{"field": "file", "issue": upload_quality.DISCHARGE_ONE_PAGE}])

    def _measure(self, file: BinaryIO) -> tuple[int, str, bytes]:
        digest = hashlib.sha256()
        size = 0
        head = b""
        file.seek(0)
        while chunk := file.read(CHUNK_SIZE):
            if len(head) < SNIFF_BYTES:
                head += chunk[: SNIFF_BYTES - len(head)]
            digest.update(chunk)
            size += len(chunk)
        return size, digest.hexdigest(), head

    def _raise_if_duplicate(self, user_id: uuid.UUID, sha256: str) -> None:
        existing = self.documents.get_by_hash(user_id, sha256)
        if existing is not None:
            raise ApiError(
                409,
                "DUPLICATE_DOCUMENT",
                "You have already uploaded this file.",
                details=[{"field": "existing_document_id", "issue": str(existing.id)}],
            )

    # ---------- read ----------

    def get(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = self.documents.get(user_id, document_id)
        if document is None:
            raise _not_found()
        return document

    def list_documents(
        self, user_id: uuid.UUID, limit: int, cursor: str | None, filters: DocumentFilters
    ) -> tuple[list[Document], str | None]:
        if filters.date_from and filters.date_to and filters.date_to < filters.date_from:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "The end date cannot be before the start date.",
                [{"field": "date_to", "issue": "The end date cannot be before the start date."}],
            )
        rows = self.documents.list_page(user_id, limit, decode_cursor(cursor) if cursor else None, filters)
        page, has_more = rows[:limit], len(rows) > limit
        return page, encode_cursor(page[-1]) if has_more and page else None

    def providers(self, user_id: uuid.UUID) -> tuple[list[tuple[str, int]], int]:
        return self.documents.providers(user_id)

    def open_file(self, user_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Document, Iterator[bytes]]:
        document = self.get(user_id, document_id)
        try:
            chunks = self.storage.open(document.storage_key or "")
        except (StorageError, ValueError) as exc:
            logger.error("document file unavailable", extra={"document_id": str(document.id)})
            raise _storage_unavailable() from exc
        self.audit.record("document.accessed", "success", user_id, {"document_id": str(document.id)})
        self.session.commit()
        return document, chunks

    # ---------- change ----------

    def update(self, user_id: uuid.UUID, document_id: uuid.UUID, changes: DocumentUpdate) -> Document:
        document = self.get(user_id, document_id)
        fields = changes.model_fields_set

        if "title" in fields and changes.title:
            document.title = changes.title
        if "category" in fields:
            document.category = changes.category or "unknown"
        if "provider_name" in fields:
            document.provider_name = changes.provider_name
        if "document_date" in fields:
            precision = changes.document_date_precision if "document_date_precision" in fields else None
            document.document_date, document.document_date_precision = normalise_date(changes.document_date, precision)

        self.audit.record(
            "document.updated", "success", user_id, {"document_id": str(document.id), "fields": sorted(fields)}
        )
        self.session.commit()
        return document

    def delete(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Tombstone the record first, then remove the file, so no live record ever points at a missing file."""
        document = self.get(user_id, document_id)
        key = document.storage_key

        document.deleted_at = datetime.now(UTC)
        document.storage_key = None
        document.title = None
        document.original_filename = None
        document.sha256 = None
        document.provider_name = None
        document.document_date = None
        document.document_date_precision = None
        # Extracted results go with their document, and any queued extraction is cancelled.
        jobs.cancel_active_jobs(self.session, document.id)
        summary_service.forget_document(self.session, user_id, document.id)
        self.session.execute(
            update(Observation)
            .where(Observation.source_document_id == document.id, Observation.deleted_at.is_(None))
            .values(deleted_at=document.deleted_at)
        )
        self.session.execute(
            update(Condition)
            .where(
                Condition.source_document_id == document.id,
                Condition.deleted_at.is_(None),
                Condition.origin == "document_extracted",  # conditions the user accepted into the profile stay
            )
            .values(deleted_at=document.deleted_at)
        )
        # Medicines the user changed (edited, or marked taking or stopped) are theirs now and stay.
        self.session.execute(
            update(Medication)
            .where(
                Medication.source_document_id == document.id,
                Medication.deleted_at.is_(None),
                Medication.user_updated_at.is_(None),
            )
            .values(deleted_at=document.deleted_at)
        )
        # Follow-ups the user already added stay theirs; ones not yet added are withdrawn.
        self.session.execute(
            update(Suggestion)
            .where(Suggestion.source_document_id == document.id, Suggestion.status == "pending")
            .values(status="superseded")
        )
        self.session.flush()
        AlertService(self.session).try_sync(user_id)  # alerts from this document's results are resolved
        self.audit.record("document.deleted", "success", user_id, {"document_id": str(document.id)})
        self.session.commit()

        if key:
            self._remove_file_quietly(key)

    def _remove_file_quietly(self, key: str) -> None:
        try:
            self.storage.delete(key)
        except (StorageError, ValueError):
            # Not referenced by any live record; logged (IDs only) for clean-up.
            logger.error("orphaned document file could not be removed", extra={"storage_key": key})
