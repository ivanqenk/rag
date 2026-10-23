"""Búsqueda híbrida de punta a punta (PostgreSQL + pgvector reales, embeddings falsos)."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EmbeddingError, get_embedding_provider
from tests.pdf_factory import make_pdf

VACATIONS = (
    "Política de vacaciones. Cada empleado dispone de veintidós días hábiles de vacaciones "
    "al año. Las vacaciones deben solicitarse con quince días de antelación al responsable."
)
EXPENSES = (
    "Política de gastos de viaje. Los gastos de hotel y transporte se reembolsan presentando "
    "factura. El código de proyecto para viajes internacionales es PRJ-8812."
)
SECURITY = (
    "Seguridad informática. Las contraseñas deben cambiarse cada noventa días y tener al "
    "menos doce caracteres. Nunca compartas tu contraseña por correo."
)


@pytest.fixture
def handbook_id(client: TestClient) -> str:
    """Un manual de 3 páginas, una política por página."""
    response = client.post(
        "/api/v1/documents",
        files={
            "file": ("manual.pdf", make_pdf([VACATIONS, EXPENSES, SECURITY]), "application/pdf")
        },
    )
    assert response.json()["status"] == "completed"
    return response.json()["id"]


def search(client: TestClient, query: str, **extra: object) -> dict:
    response = client.post("/api/v1/search", json={"query": query, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_finds_the_relevant_page(client: TestClient, handbook_id: str) -> None:
    body = search(client, "¿cuántos días de vacaciones tengo?")

    assert body["insufficient_evidence"] is False
    best = body["results"][0]
    assert best["document_id"] == handbook_id
    assert best["filename"] == "manual.pdf"
    assert best["page_number"] == 1
    assert "veintidós días" in best["text"]
    assert best["vector_similarity"] is not None


def test_keyword_search_finds_exact_codes(client: TestClient, handbook_id: str) -> None:
    body = search(client, "PRJ-8812")

    best = body["results"][0]
    assert best["page_number"] == 2
    assert best["keyword_match"] is True


def test_results_are_ordered_and_limited(client: TestClient, handbook_id: str) -> None:
    body = search(client, "política de vacaciones y de gastos", top_k=2)

    scores = [r["score"] for r in body["results"]]
    assert len(scores) <= 2
    assert scores == sorted(scores, reverse=True)


def test_unrelated_query_reports_insufficient_evidence(
    client: TestClient, handbook_id: str
) -> None:
    body = search(client, "receta de paella valenciana con mariscos")

    assert body == {"results": [], "insufficient_evidence": True}


def test_empty_library_reports_insufficient_evidence(client: TestClient) -> None:
    assert search(client, "vacaciones")["insufficient_evidence"] is True


def test_response_never_includes_embeddings(client: TestClient, handbook_id: str) -> None:
    result = search(client, "vacaciones")["results"][0]

    assert "embedding" not in result


def test_failed_documents_are_not_searchable(
    client: TestClient, db_session: Session, handbook_id: str
) -> None:
    client.post(
        "/api/v1/documents", files={"file": ("vacio.pdf", make_pdf([""]), "application/pdf")}
    )

    for result in search(client, "vacaciones")["results"]:
        assert result["document_id"] == handbook_id


def test_vectors_from_another_model_are_ignored(
    client: TestClient, db_session: Session, handbook_id: str
) -> None:
    # Simula fragmentos generados con un modelo anterior (antes de un cambio de proveedor).
    db_session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == UUID(handbook_id))
        .values(embedding_model="old-model")
    )
    db_session.commit()

    results = search(client, "¿cuántos días de vacaciones tengo?")["results"]

    # Sin coincidencias vectoriales; solo podría aparecer por palabras exactas.
    assert all(r["vector_similarity"] is None for r in results)


def test_min_score_threshold_filters_weak_vector_matches(
    client: TestClient, settings: Settings, handbook_id: str
) -> None:
    strict = settings.model_copy(update={"retrieval_min_score": 0.99})
    app.dependency_overrides[get_settings] = lambda: strict

    results = search(client, "días hábiles de descanso")["results"]

    assert all(r["vector_similarity"] is None for r in results)


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "vacaciones", "top_k": 0},
        {"query": "vacaciones", "top_k": 21},
        {},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/search", json=payload).status_code == 422


def test_provider_failure_returns_503(client: TestClient) -> None:
    class DownProvider:
        model_name = "down"

        def embed_query(self, text: str) -> list[float]:
            raise EmbeddingError("El proveedor de embeddings no está disponible.")

    app.dependency_overrides[get_embedding_provider] = lambda: DownProvider()

    response = client.post("/api/v1/search", json={"query": "vacaciones"})

    assert response.status_code == 503
    assert response.json() == {"detail": "El proveedor de embeddings no está disponible."}


def test_missing_api_key_returns_503(client: TestClient, settings: Settings) -> None:
    # Configuración real (sin el proveedor falso) pero sin clave de OpenAI.
    del app.dependency_overrides[get_embedding_provider]
    unconfigured = settings.model_copy(
        update={"embeddings_provider": "openai", "openai_api_key": None}
    )
    app.dependency_overrides[get_settings] = lambda: unconfigured

    response = client.post("/api/v1/search", json={"query": "vacaciones"})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
