"""Database access for documents. Every query is scoped to one user and excludes deleted rows."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document


@dataclass(frozen=True)
class DocumentFilters:
    category: str | None = None
    date_from: date | None = None  # on the report's date; documents without one are left out
    date_to: date | None = None
    provider: str | None = None  # matched ignoring case and extra spaces
    provider_missing: bool = False


def provider_key(name: str) -> str:
    """The comparison form of a hospital or clinic name: lower case, single spaces."""
    return " ".join(name.lower().split())


def _provider_key_sql(column):
    return func.lower(func.regexp_replace(func.trim(column), r"\s+", " ", "g"))


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _live(self, user_id: uuid.UUID):
        return select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))

    def get(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        return self.session.scalar(self._live(user_id).where(Document.id == document_id))

    def get_by_hash(self, user_id: uuid.UUID, sha256: str) -> Document | None:
        return self.session.scalar(self._live(user_id).where(Document.sha256 == sha256))

    def list_page(
        self,
        user_id: uuid.UUID,
        limit: int,
        after: tuple[datetime, uuid.UUID] | None = None,
        filters: DocumentFilters | None = None,
    ) -> list[Document]:
        """Newest first, keyset-paginated on (created_at, id) so pages stay stable as uploads arrive."""
        query = self._live(user_id)
        filters = filters or DocumentFilters()
        if filters.category:
            query = query.where(Document.category == filters.category)
        if filters.date_from:
            query = query.where(Document.document_date >= filters.date_from)
        if filters.date_to:
            query = query.where(Document.document_date <= filters.date_to)
        if filters.provider_missing:
            query = query.where(or_(Document.provider_name.is_(None), func.trim(Document.provider_name) == ""))
        elif filters.provider:
            query = query.where(_provider_key_sql(Document.provider_name) == provider_key(filters.provider))
        if after:
            created_at, document_id = after
            query = query.where(
                or_(
                    Document.created_at < created_at,
                    and_(Document.created_at == created_at, Document.id < document_id),
                )
            )
        query = query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
        return list(self.session.scalars(query))

    def providers(self, user_id: uuid.UUID) -> tuple[list[tuple[str, int]], int]:
        """The user's hospital and clinic names (spelling variants of case and spacing counted as one),
        with how many documents each has, and how many documents have none."""
        rows = self.session.execute(
            select(Document.provider_name, func.count())
            .where(Document.user_id == user_id, Document.deleted_at.is_(None))
            .group_by(Document.provider_name)
        )
        names: dict[str, tuple[str, int, int]] = {}  # key -> (shown name, its own count, total)
        missing = 0
        for name, count in rows:
            if name is None or not name.strip():
                missing += count
                continue
            key = provider_key(name)
            spelling = " ".join(name.split())
            shown, shown_count, total = names.get(key, (spelling, 0, 0))
            # Show the most used spelling; on a tie, the same one every time.
            if count > shown_count or (count == shown_count and spelling < shown):
                shown, shown_count = spelling, count
            names[key] = (shown, shown_count, total + count)
        listed = sorted(((shown, total) for shown, _, total in names.values()), key=lambda item: item[0].lower())
        return listed, missing

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document
