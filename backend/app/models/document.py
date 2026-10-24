"""Modelo ORM de la tabla `documents`."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.schemas.document import DocumentStatus

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in DocumentStatus)


class Document(Base):
    __tablename__ = "documents"
    # Se usa VARCHAR + CHECK en lugar de un ENUM nativo de PostgreSQL porque
    # añadir o renombrar valores de un ENUM nativo requiere migraciones más delicadas.
    __table_args__ = (CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_documents_status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Resumen generado por el LLM al procesar el documento (None si no se pudo generar).
    summary: Mapped[str | None] = mapped_column(Text)
    summary_model: Mapped[str | None] = mapped_column(String(100))
