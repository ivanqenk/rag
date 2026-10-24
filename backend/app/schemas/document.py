"""Esquemas Pydantic de documentos: definen lo que la API acepta y devuelve."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentRead(BaseModel):
    """Documento tal como lo ve el cliente.

    No incluye `storage_key` ni otras rutas internas: la API nunca debe revelar
    dónde se guardan los archivos en el servidor.
    """

    # Permite construirlo directamente desde un objeto ORM (DocumentRead.model_validate(orm_obj)).
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None
    # Generado por un LLM: el cliente debe mostrarlo como texto, nunca como HTML.
    summary: str | None = None
    folder_id: UUID | None = None
    # En la papelera desde esta fecha; None si está activo.
    deleted_at: datetime | None = None


class DocumentUpdate(BaseModel):
    """Mover un documento: a una carpeta, o fuera de cualquier carpeta con `null`."""

    folder_id: UUID | None


class DocumentPage(BaseModel):
    """Una página de resultados de la lista de documentos."""

    items: list[DocumentRead]
    total: int
    limit: int
    offset: int


class TrashPage(DocumentPage):
    """Documentos de la papelera; se borran del todo `retention_days` después de `deleted_at`."""

    retention_days: int
