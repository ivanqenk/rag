"""Acceso a datos de documentos en PostgreSQL."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        original_filename: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
    ) -> Document:
        """Registra un documento nuevo con estado `pending` y confirma la transacción."""
        document = Document(
            original_filename=original_filename,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
        )
        self._session.add(document)
        self._session.commit()
        # Recarga los valores generados por la base de datos (created_at, updated_at).
        self._session.refresh(document)
        return document

    def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        """Devuelve una página de documentos (más recientes primero) y el total."""
        # `id` desempata documentos creados en el mismo instante: la paginación es estable.
        statement = (
            select(Document)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        documents = list(self._session.scalars(statement))
        total = self._session.scalar(select(func.count()).select_from(Document)) or 0
        return documents, total

    def get(self, document_id: UUID) -> Document | None:
        return self._session.get(Document, document_id)


def get_document_repository(session: Annotated[Session, Depends(get_db)]) -> DocumentRepository:
    """Dependencia de FastAPI: un repositorio ligado a la sesión de la petición actual."""
    return DocumentRepository(session)
