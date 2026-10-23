"""Modelos ORM. Importarlos aquí registra sus tablas en Base.metadata (lo usa Alembic)."""

from app.models.document import Document

__all__ = ["Document"]
