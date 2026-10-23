"""Consulta RAG de punta a punta (PostgreSQL real, embeddings y LLM falsos)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm import FakeLLMProvider, LLMAnswer, LLMError, get_llm_provider
from app.services.rag import NO_EVIDENCE_ANSWER
from tests.integration.test_search import EXPENSES, SECURITY, VACATIONS
from tests.pdf_factory import make_pdf


@pytest.fixture
def handbook_id(client: TestClient) -> str:
    response = client.post(
        "/api/v1/documents",
        files={
            "file": ("manual.pdf", make_pdf([VACATIONS, EXPENSES, SECURITY]), "application/pdf")
        },
    )
    assert response.json()["status"] == "completed"
    return response.json()["id"]


def use_llm(llm: FakeLLMProvider) -> FakeLLMProvider:
    app.dependency_overrides[get_llm_provider] = lambda: llm
    return llm


def ask(client: TestClient, question: str) -> dict:
    response = client.post("/api/v1/query", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_answer_includes_verifiable_sources(client: TestClient, handbook_id: str) -> None:
    body = ask(client, "¿cuántos días de vacaciones tengo?")

    assert body["insufficient_evidence"] is False
    assert "veintidós días" in body["answer"]
    [source] = body["sources"]
    assert source["document_id"] == handbook_id
    assert source["filename"] == "manual.pdf"
    assert source["page_number"] == 1
    assert source["chunk_id"]
    assert source["excerpt"] in VACATIONS
    # Nunca exponemos vectores ni rutas internas.
    assert "embedding" not in source
    assert "storage_key" not in source


def test_no_relevant_chunks_abstains_without_calling_the_llm(
    client: TestClient, llm: FakeLLMProvider, handbook_id: str
) -> None:
    body = ask(client, "receta de paella valenciana con mariscos")

    assert body == {"answer": NO_EVIDENCE_ANSWER, "sources": [], "insufficient_evidence": True}
    assert llm.calls == []  # sin evidencia no se gasta dinero en el LLM


def test_llm_abstention_is_respected(client: TestClient, handbook_id: str) -> None:
    use_llm(
        FakeLLMProvider(
            scripted=LLMAnswer(answer="No lo sé.", cited_sources=[], insufficient_evidence=True)
        )
    )

    body = ask(client, "¿cuántos días de vacaciones tengo?")

    assert body["insufficient_evidence"] is True
    assert body["sources"] == []


def test_invented_citations_are_discarded(client: TestClient, handbook_id: str) -> None:
    use_llm(
        FakeLLMProvider(
            scripted=LLMAnswer(
                answer="Son 22 días.", cited_sources=["S1", "S99"], insufficient_evidence=False
            )
        )
    )

    body = ask(client, "¿cuántos días de vacaciones tengo?")

    assert body["insufficient_evidence"] is False
    assert len(body["sources"]) == 1  # S99 no existía en el contexto


def test_answer_without_any_valid_citation_is_not_trusted(
    client: TestClient, handbook_id: str
) -> None:
    use_llm(
        FakeLLMProvider(
            scripted=LLMAnswer(
                answer="Son 30 días (inventado).",
                cited_sources=["S42"],
                insufficient_evidence=False,
            )
        )
    )

    body = ask(client, "¿cuántos días de vacaciones tengo?")

    assert body == {"answer": NO_EVIDENCE_ANSWER, "sources": [], "insufficient_evidence": True}


def test_llm_receives_bounded_context_from_retrieval(
    client: TestClient, llm: FakeLLMProvider, handbook_id: str
) -> None:
    ask(client, "política de vacaciones y de gastos")

    [(question, context)] = llm.calls
    assert question == "política de vacaciones y de gastos"
    assert 1 <= len(context) <= 5
    assert [c.ref for c in context] == [f"S{i}" for i in range(1, len(context) + 1)]


@pytest.mark.parametrize(
    "payload", [{"question": ""}, {"question": "  "}, {"question": "x" * 1001}, {}]
)
def test_invalid_questions_are_rejected(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/query", json=payload).status_code == 422


def test_client_cannot_raise_context_limits(
    client: TestClient, llm: FakeLLMProvider, handbook_id: str
) -> None:
    response = client.post(
        "/api/v1/query",
        json={"question": "vacaciones", "top_k": 1000, "max_context_chars": 10**9},
    )

    assert response.status_code == 200
    [(_, context)] = llm.calls
    assert len(context) <= 5


def test_llm_failure_returns_503(client: TestClient, handbook_id: str) -> None:
    class DownLLM:
        model_name = "down"

        def generate_answer(self, question: str, context: list) -> None:
            raise LLMError("El proveedor de LLM no está disponible. Inténtalo más tarde.")

    app.dependency_overrides[get_llm_provider] = lambda: DownLLM()

    response = client.post("/api/v1/query", json={"question": "¿cuántos días de vacaciones?"})

    assert response.status_code == 503
    assert "no está disponible" in response.json()["detail"]
