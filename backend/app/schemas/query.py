"""Esquemas de la consulta RAG (pregunta -> respuesta con fuentes)."""

from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    # Solo la pregunta: el cliente no puede ampliar el contexto ni el costo de la consulta.
    # La longitud máxima (MAX_QUERY_CHARS) se valida en el endpoint.
    question: str = Field(min_length=1, description="Pregunta en lenguaje natural")


class SourceItem(BaseModel):
    document_id: UUID
    filename: str
    page_number: int | None
    chunk_id: UUID
    excerpt: str = Field(description="Fragmento breve que respalda la respuesta")
    score: float


class QueryResponse(BaseModel):
    # Texto plano generado por un LLM: el cliente debe mostrarlo como texto, nunca como HTML.
    answer: str
    sources: list[SourceItem]
    insufficient_evidence: bool
