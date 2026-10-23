"""Modelo ORM de la tabla `document_chunks`."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Dimensión de text-embedding-3-small. Cambiarla exige una migración y reindexar todo.
EMBEDDING_DIMENSIONS = 1536


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    # El índice único (document_id, chunk_index) también sirve para buscar por document_id
    # (es la primera columna), así que no hace falta un índice aparte.
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
        # GIN es el tipo de índice adecuado para búsquedas de texto completo.
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        # Sin índice vectorial (HNSW) a propósito: la búsqueda exacta es correcta y rápida
        # con pocos miles de fragmentos. Se añadirá cuando las mediciones lo justifiquen.
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # ON DELETE CASCADE: al borrar un documento, PostgreSQL borra sus fragmentos.
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Nulos solo en fragmentos creados antes de la Fase 4: hay que reprocesarlos.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    # Columna calculada por PostgreSQL para la búsqueda por palabras. Configuración 'simple':
    # sin stemming ni stopwords de un idioma concreto, sirve igual para español e inglés y
    # encuentra literalmente nombres propios, códigos y números.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
