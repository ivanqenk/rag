"""Modelos ORM. Importarlos aquí registra sus tablas en Base.metadata (lo usa Alembic)."""

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

__all__ = ["Document", "DocumentChunk"]
