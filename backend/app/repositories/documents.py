"""Acceso a datos de documentos en PostgreSQL."""

# Evalúa las anotaciones de forma diferida: sin esto, dentro de la clase el método `list`
# tapa al tipo `list` y `-> list[DocumentChunk]` fallaría al importar el módulo.
from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.chunking import TextChunk


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

    def delete(self, document: Document) -> None:
        """Borra el documento; PostgreSQL borra sus fragmentos (ON DELETE CASCADE).
        NO confirma: quien llama decide cuándo, p. ej. antes de borrar el archivo."""
        self._session.delete(document)

    def replace_chunks(
        self,
        document_id: UUID,
        chunks: Sequence[TextChunk],
        embeddings: Sequence[list[float]],
        embedding_model: str,
    ) -> None:
        """Sustituye los fragmentos de un documento. NO confirma: lo hace quien llama,
        para que el cambio de fragmentos y de estado ocurran en la misma transacción."""
        if len(chunks) != len(embeddings):
            raise ValueError("Cada fragmento necesita exactamente un embedding")
        self._session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self._session.add_all(
            DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                text=chunk.text,
                embedding=embedding,
                embedding_model=embedding_model,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )

    def list_chunks(self, document_id: UUID) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(self._session.scalars(statement))


def get_document_repository(session: Annotated[Session, Depends(get_db)]) -> DocumentRepository:
    """Dependencia de FastAPI: un repositorio ligado a la sesión de la petición actual."""
    return DocumentRepository(session)
