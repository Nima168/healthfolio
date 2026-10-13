"""Exports of the user's own data (frontend_spec.md Section 16.1, backend_spec.md Section 5.5).

Built when asked and streamed straight to the browser: nothing is stored on the server. Only live records
(not deleted ones) and only the requesting user's. Internal fields (password hash, storage paths, queue
details) are left out.
"""

import csv
import io
import json
import re
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models.alerts import Alert, AlertEvent
from app.models.auth import User
from app.models.document import Document
from app.models.extraction import Observation
from app.models.prescription import Condition, FollowUp, Medication, MedicationHistory
from app.models.profile import MedicalRecordItem, ProfileValue, ProfileValueHistory, VitalReading
from app.models.summary import AiSummary
from app.services.document_validation import DEFAULT_EXTENSION
from app.services.storage import DocumentStorage, StorageError

EXPORT_VERSION = 1
SPOOL_BYTES = 20 * 1024 * 1024  # larger exports spill to a temporary file, deleted when streamed

# Name in the export -> model. Order is the order of the JSON keys and CSV files.
TABLES: dict[str, Any] = {
    "documents": Document,
    "lab_results": Observation,
    "medications": Medication,
    "medication_history": MedicationHistory,
    "conditions": Condition,
    "follow_ups": FollowUp,
    "alerts": Alert,
    "profile_values": ProfileValue,
    "profile_value_history": ProfileValueHistory,
    "medical_records": MedicalRecordItem,
    "vital_readings": VitalReading,
    "ai_summaries": AiSummary,
}
# Never exported: internal or meaningless outside this server.
_HIDDEN = {"user_id", "storage_key", "deleted_at", "processing_job_id", "idempotency_key", "fingerprint"}


def _value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _order(model: Any) -> Any:
    """Oldest first, by whichever time the table records."""
    for name in ("created_at", "changed_at", "occurred_at"):
        if hasattr(model, name):
            return getattr(model, name)
    return model.id


def _row(obj: Any) -> dict[str, Any]:
    return {c.key: _value(getattr(obj, c.key)) for c in inspect(obj).mapper.column_attrs if c.key not in _HIDDEN}


class ExportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _live_documents(self, user_id: uuid.UUID) -> list[Document]:
        return list(
            self.session.scalars(
                select(Document)
                .where(Document.user_id == user_id, Document.deleted_at.is_(None))
                .order_by(Document.created_at)
            )
        )

    def records(self, user_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
        """Every live record of the user, by table."""
        live_documents = {d.id for d in self._live_documents(user_id)}
        data: dict[str, list[dict[str, Any]]] = {}
        for name, model in TABLES.items():
            query = select(model).where(model.user_id == user_id)
            if hasattr(model, "deleted_at"):
                query = query.where(model.deleted_at.is_(None))
            rows = []
            for obj in self.session.scalars(query.order_by(_order(model))):
                # Records read from a deleted document went with it.
                source = getattr(obj, "source_document_id", None)
                if name != "documents" and source is not None and source not in live_documents:
                    continue
                rows.append(_row(obj))
            data[name] = rows
        medicines = {row["id"] for row in data["medications"]}
        data["medication_history"] = [r for r in data["medication_history"] if r["medication_id"] in medicines]
        alert_ids = [uuid.UUID(row["id"]) for row in data["alerts"]]
        data["alert_events"] = [
            _row(event)
            for event in self.session.scalars(
                select(AlertEvent).where(AlertEvent.alert_id.in_(alert_ids)).order_by(AlertEvent.occurred_at)
            )
        ]
        return data

    def json_export(self, user: User) -> bytes:
        payload = {
            "export_version": EXPORT_VERSION,
            "exported_at": _value(datetime.now().astimezone()),
            "account": {"email": user.email, "display_name": user.display_name, "created_at": _value(user.created_at)},
            "notes": [
                "Your own records only. Values read from documents by AI are as read, not checked by a clinician.",
                "Original files are in the separate documents download.",
            ],
            "records": self.records(user.id),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def csv_export(self, user: User) -> bytes:
        """A ZIP with one CSV per record type (nested values as JSON text)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, rows in self.records(user.id).items():
                columns: list[str] = []
                for row in rows:
                    columns += [key for key in row if key not in columns]
                text = io.StringIO()
                writer = csv.DictWriter(text, fieldnames=columns or ["id"], extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                            for k, v in row.items()
                        }
                    )
                # A byte-order mark so spreadsheet programs read the text as UTF-8.
                archive.writestr(f"{name}.csv", "﻿" + text.getvalue())
        return buffer.getvalue()

    def documents_export(self, user_id: uuid.UUID, storage: DocumentStorage) -> Iterator[bytes]:
        """A ZIP of every original file, named by date and title. Streams from a temporary spool."""
        spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
        used: set[str] = set()
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_STORED) as archive:  # PDFs and photos are compressed already
            for document in self._live_documents(user_id):
                if not document.storage_key:
                    continue
                name = _archive_name(document, used)
                try:
                    with archive.open(name, "w") as entry:
                        for chunk in storage.open(document.storage_key):
                            entry.write(chunk)
                except StorageError:
                    archive.writestr(f"{name}.missing.txt", "This file could not be read from storage.")
        spool.seek(0)

        def stream() -> Iterator[bytes]:
            with spool:
                while chunk := spool.read(64 * 1024):
                    yield chunk

        return stream()


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _archive_name(document: Document, used: set[str]) -> str:
    when = document.document_date.isoformat() if document.document_date else "undated"
    title = _UNSAFE.sub("_", document.title or "document").strip(" .")[:80] or "document"
    extension = DEFAULT_EXTENSION.get(document.media_type, "")
    base, number = f"{when} {title}", 1
    name = f"{base}{extension}"
    while name.lower() in used:
        number += 1
        name = f"{base} ({number}){extension}"
    used.add(name.lower())
    return name
