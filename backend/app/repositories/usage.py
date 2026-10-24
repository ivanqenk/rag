"""Acceso a datos del uso diario (presupuesto y cuotas)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.usage import UsageDaily


def today_utc() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True)
class StorageUsage:
    documents: int  # incluye la papelera: sigue ocupando espacio
    bytes: int


class UsageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, cost_usd: float, queries: int = 0, documents_processed: int = 0) -> None:
        """Suma al día de hoy. Un solo INSERT … ON CONFLICT: dos peticiones simultáneas no se
        pisan (no hay «leer, sumar y escribir»). NO confirma: lo hace quien llama."""
        values = {
            "day": today_utc(),
            "cost_usd": Decimal(str(round(cost_usd, 6))),
            "queries": queries,
            "documents_processed": documents_processed,
        }
        statement = insert(UsageDaily).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[UsageDaily.day],
            set_={
                "cost_usd": UsageDaily.cost_usd + statement.excluded.cost_usd,
                "queries": UsageDaily.queries + statement.excluded.queries,
                "documents_processed": UsageDaily.documents_processed
                + statement.excluded.documents_processed,
            },
        )
        self._session.execute(statement)

    def today(self) -> UsageDaily:
        """El uso de hoy (a cero si todavía no hay registro)."""
        usage = self._session.get(UsageDaily, today_utc())
        return usage or UsageDaily(
            day=today_utc(), cost_usd=Decimal(0), queries=0, documents_processed=0
        )

    def storage(self) -> StorageUsage:
        count, total = self._session.execute(
            select(func.count(Document.id), func.coalesce(func.sum(Document.size_bytes), 0))
        ).one()
        return StorageUsage(documents=count, bytes=int(total))
