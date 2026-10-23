"""Modelo ORM de la tabla `document_chunks`."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    # El índice único (document_id, chunk_index) también sirve para buscar por document_id
    # (es la primera columna), así que no hace falta un índice aparte.
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # ON DELETE CASCADE: al borrar un documento, PostgreSQL borra sus fragmentos.
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # La columna `embedding` (pgvector) se añadirá en la Fase 4.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
