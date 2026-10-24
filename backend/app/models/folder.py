"""Modelo ORM de la tabla `folders`: agrupan documentos para consultarlos juntos."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Nombre único sin distinguir mayúsculas: "Contratos" y "contratos" serían confusos. Se define
# fuera de la clase para referirse a la columna (func.lower("name") sería el texto 'name').
Index("uq_folders_name_lower", func.lower(Folder.name), unique=True)
