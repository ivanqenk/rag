"""Esquemas de la consulta RAG (pregunta -> respuesta con fuentes)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SearchScope(BaseModel):
    """Limita la búsqueda a un documento o a una de sus páginas. Solo puede reducir el
    contexto, nunca ampliarlo (ni el costo de la consulta)."""

    document_id: UUID | None = Field(default=None, description="Buscar solo en este documento")
    page_number: int | None = Field(
        default=None, ge=1, description="Buscar solo en esta página (requiere document_id)"
    )

    @model_validator(mode="after")
    def _page_requires_document(self) -> "SearchScope":
        if self.page_number is not None and self.document_id is None:
            raise ValueError("page_number requiere document_id")
        return self


class QueryRequest(SearchScope):
    # La longitud máxima (MAX_QUERY_CHARS) se valida en el endpoint.
    question: str = Field(min_length=1, description="Pregunta en lenguaje natural")


class SourceItem(BaseModel):
    document_id: UUID
    filename: str
    page_number: int | None
    source_type: Literal["chunk", "summary"] = Field(
        description="'chunk': un fragmento del documento; 'summary': el resumen del documento"
    )
    chunk_id: UUID | None = Field(description="None cuando la fuente es el resumen")
    excerpt: str = Field(description="Fragmento breve que respalda la respuesta")
    score: float | None = Field(description="Relevancia de la búsqueda; None en resúmenes")


class QueryResponse(BaseModel):
    # Texto plano generado por un LLM: el cliente debe mostrarlo como texto, nunca como HTML.
    answer: str
    sources: list[SourceItem]
    insufficient_evidence: bool
