"""Esquemas de la búsqueda semántica."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    # La longitud máxima depende de la configuración (MAX_QUERY_CHARS) y se valida en el
    # endpoint; aquí solo el mínimo.
    query: str = Field(min_length=1, description="Pregunta o texto a buscar")
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Número de resultados. Se limita en el servidor (RETRIEVAL_MAX_TOP_K).",
    )


class SearchResultItem(BaseModel):
    """Un fragmento encontrado. Nunca incluye el vector de embedding."""

    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    chunk_index: int
    text: str
    score: float
    vector_similarity: float | None
    keyword_match: bool


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    # True cuando ningún fragmento supera los umbrales: es mejor decir "no lo sé" que
    # devolver fragmentos irrelevantes.
    insufficient_evidence: bool
