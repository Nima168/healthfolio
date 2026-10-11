"""Database access for documents. Every query is scoped to one user and excludes deleted rows."""

import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document


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
        category: str | None = None,
    ) -> list[Document]:
        """Newest first, keyset-paginated on (created_at, id) so pages stay stable as uploads arrive."""
        query = self._live(user_id)
        if category:
            query = query.where(Document.category == category)
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

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        return document
