"""Endpoint de uso: gasto de hoy, espacio ocupado y límites configurados."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.usage import UsageRepository
from app.schemas.usage import UsageRead

router = APIRouter(prefix="/api/v1", tags=["usage"])


@router.get("/usage", response_model=UsageRead)
def get_usage(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UsageRead:
    repository = UsageRepository(session)
    today = repository.today()
    storage = repository.storage()
    return UsageRead(
        day=today.day,
        cost_usd=float(today.cost_usd),
        daily_budget_usd=settings.daily_budget_usd,
        queries_today=today.queries,
        documents_processed_today=today.documents_processed,
        documents=storage.documents,
        max_documents=settings.max_documents,
        storage_bytes=storage.bytes,
        max_storage_bytes=settings.max_storage_mb * 1024 * 1024,
        queries_per_minute=settings.rate_limit_queries_per_minute,
        uploads_per_hour=settings.rate_limit_uploads_per_hour,
    )
