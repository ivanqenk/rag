"""Esquema del uso y los límites (para mostrarlos en la interfaz)."""

from datetime import date

from pydantic import BaseModel, Field


class UsageRead(BaseModel):
    day: date = Field(description="Día (UTC) al que se refieren los contadores")
    cost_usd: float = Field(description="Gasto estimado de hoy en el proveedor de IA")
    daily_budget_usd: float = Field(description="Gasto máximo por día; 0 = sin límite")
    queries_today: int
    documents_processed_today: int
    documents: int = Field(description="Documentos guardados, incluida la papelera")
    max_documents: int = Field(description="0 = sin límite")
    storage_bytes: int = Field(description="Espacio ocupado, incluida la papelera")
    max_storage_bytes: int = Field(description="0 = sin límite")
    queries_per_minute: int = Field(description="Límite por cliente; 0 = sin límite")
    uploads_per_hour: int = Field(description="Límite por cliente; 0 = sin límite")
