"""Esquemas de la consulta RAG (pregunta -> respuesta con fuentes)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.retrieval import Scope


class SearchScope(BaseModel):
    """Limita la búsqueda a una carpeta, a un documento o a una de sus páginas. Solo puede
    reducir el contexto, nunca ampliarlo (ni el costo de la consulta)."""

    folder_id: UUID | None = Field(default=None, description="Buscar solo en esta carpeta")
    document_id: UUID | None = Field(default=None, description="Buscar solo en este documento")
    page_number: int | None = Field(
        default=None, ge=1, description="Buscar solo en esta página (requiere document_id)"
    )

    @model_validator(mode="after")
    def _consistent_scope(self) -> "SearchScope":
        if self.page_number is not None and self.document_id is None:
            raise ValueError("page_number requiere document_id")
        if self.folder_id is not None and self.document_id is not None:
            raise ValueError("Indica una carpeta o un documento, no ambos")
        return self

    def to_scope(self) -> Scope:
        return Scope(
            folder_id=self.folder_id, document_id=self.document_id, page_number=self.page_number
        )


AnswerStyle = Literal["brief", "detailed", "steps"]


class QueryRequest(SearchScope):
    # La longitud máxima (MAX_QUERY_CHARS) se valida en el endpoint.
    question: str = Field(min_length=1, description="Pregunta en lenguaje natural")
    answer_style: AnswerStyle = Field(
        default="brief",
        description="brief: una o dos frases; detailed: resumen y puntos; steps: pasos en orden",
    )


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


class PointItem(BaseModel):
    # Texto plano generado por un LLM: mostrar como texto, nunca como HTML.
    text: str
    sources: list[int] = Field(description="Posiciones (desde 0) en `sources` que lo respaldan")


class QueryResponse(BaseModel):
    # Texto plano generado por un LLM: el cliente debe mostrarlo como texto, nunca como HTML.
    # Puede estar vacío en respuestas detalladas si el resumen no superó la verificación.
    answer: str
    sources: list[SourceItem]
    insufficient_evidence: bool
    answer_style: AnswerStyle
    points: list[PointItem] = Field(
        description="Puntos o pasos, cada uno con sus fuentes (vacío en respuestas breves)"
    )
