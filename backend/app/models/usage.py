"""Modelo ORM de la tabla `usage_daily`: gasto estimado y actividad por día (UTC)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageDaily(Base):
    """Un registro por día. Sirve para el presupuesto diario (DAILY_BUDGET_USD) y para mostrar
    el uso; sobrevive a reinicios del servidor. No guarda preguntas ni textos."""

    __tablename__ = "usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # Costo estimado en USD (tokens × precio configurado). Numeric: sin errores de redondeo
    # al sumar muchas cantidades pequeñas.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    queries: Mapped[int] = mapped_column(Integer, default=0)
    documents_processed: Mapped[int] = mapped_column(Integer, default=0)
