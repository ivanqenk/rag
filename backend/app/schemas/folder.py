"""Esquemas de carpetas."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Sin espacios sobrantes; 1-100 caracteres.
FolderName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class FolderWrite(BaseModel):
    """Crear o renombrar una carpeta."""

    name: FolderName


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    document_count: int = Field(description="Documentos dentro de la carpeta")
