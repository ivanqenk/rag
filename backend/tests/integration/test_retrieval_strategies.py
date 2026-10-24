"""Filtros por documento/página, búsqueda por palabras (OR + BM25) y estrategias del RAG."""

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services import ingestion, rag, retrieval
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider, LLMAnswer, LLMError, RerankResult
from app.services.prompts import ContextChunk
from app.services.storage import LocalFileStorage
from tests.integration.test_search import EXPENSES, SECURITY, VACATIONS
from tests.pdf_factory import make_pdf

ABSTAIN = LLMAnswer(answer="No lo sé.", cited_sources=[], insufficient_evidence=True)


def upload(client: TestClient, pages: list[str], filename: str = "manual.pdf") -> str:
    response = client.post(
        "/api/v1/documents", files={"file": (filename, make_pdf(pages), "application/pdf")}
    )
    assert response.json()["status"] == "completed"
    return response.json()["id"]


def create_long_document(session: Session, settings: Settings, pages: int) -> None:
    """Un documento con una página (un fragmento) por tema, todas con la palabra "norma"."""
    storage = LocalFileStorage(settings.storage_dir)
    texts = [f"Norma número {i}: el tema {i} trata del asunto {i}." for i in range(pages)]
    document = ingestion.register_upload(session, storage, settings, "normas.pdf", make_pdf(texts))
    ingestion.process_document(
        session, storage, FakeEmbeddingProvider(), None, settings, document.id
    )


# --- Palabras clave --------------------------------------------------------------------


def test_keyword_terms_drop_stopwords_and_duplicates() -> None:
    terms = retrieval.keyword_terms("¿Cuántos indios de guerra pidió Cortés a los de Tlascala?")

    # Sin tildes, igual que la columna de búsqueda (immutable_unaccent).
    assert terms == ["indios", "guerra", "pidio", "cortes", "tlascala"]


def test_keyword_search_does_not_need_every_word(
    db_session: Session, client: TestClient, settings: Settings
) -> None:
    upload(client, [VACATIONS, EXPENSES, SECURITY])
    # Umbral imposible: solo cuenta la búsqueda por palabras.
    keywords_only = settings.model_copy(update={"retrieval_min_score": 1.0})

    # "marte" no aparece en ningún sitio: antes (todas las palabras) no encontraba nada.
    results = retrieval.search(
        db_session, FakeEmbeddingProvider(), keywords_only, "factura del hotel en Marte", 5
    )

    assert [r.page_number for r in results] == [2]
    assert results[0].keyword_match is True


@pytest.mark.parametrize("query", ["política reembolso factura", "politica reembolsan FACTURA"])
def test_keyword_search_ignores_accents_and_case(
    db_session: Session, client: TestClient, settings: Settings, query: str
) -> None:
    upload(client, [VACATIONS, EXPENSES, SECURITY])
    keywords_only = settings.model_copy(update={"retrieval_min_score": 1.0})

    # El texto dice «Política de gastos… se reembolsan presentando factura».
    results = retrieval.search(db_session, FakeEmbeddingProvider(), keywords_only, query, 5)

    assert [r.page_number for r in results] == [2]


def test_a_single_loose_word_is_not_evidence(
    db_session: Session, client: TestClient, settings: Settings
) -> None:
    upload(client, [VACATIONS, EXPENSES, SECURITY])
    keywords_only = settings.model_copy(update={"retrieval_min_score": 1.0})

    # Solo "factura" coincide (1 de 3 palabras): no basta.
    results = retrieval.search(
        db_session, FakeEmbeddingProvider(), keywords_only, "conductor camión factura", 5
    )

    assert results == []


# --- Filtros por documento y página ----------------------------------------------------


def test_query_limited_to_a_page_only_reads_that_page(
    client: TestClient, llm: FakeLLMProvider
) -> None:
    document_id = upload(client, [VACATIONS, EXPENSES, SECURITY])

    response = client.post(
        "/api/v1/query",
        json={"question": "¿en qué año fue esto?", "document_id": document_id, "page_number": 2},
    )

    assert response.status_code == 200
    [source] = response.json()["sources"]
    assert source["page_number"] == 2
    [(_, context)] = llm.calls
    assert {chunk.page_number for chunk in context} == {2}


def test_search_limited_to_a_document(client: TestClient) -> None:
    upload(client, [VACATIONS], filename="a.pdf")
    other_id = upload(client, [VACATIONS + " Anexo B."], filename="b.pdf")

    response = client.post(
        "/api/v1/search", json={"query": "días de vacaciones", "document_id": other_id}
    )

    results = response.json()["results"]
    assert results
    assert {r["document_id"] for r in results} == {other_id}


@pytest.mark.parametrize("path", ["/api/v1/query", "/api/v1/search"])
def test_scope_is_validated(client: TestClient, path: str) -> None:
    key = "question" if path.endswith("query") else "query"
    unknown = "00000000-0000-0000-0000-000000000000"

    page_without_document = client.post(path, json={key: "vacaciones", "page_number": 2})
    unknown_document = client.post(path, json={key: "vacaciones", "document_id": unknown})
    invalid_page = client.post(path, json={key: "x", "document_id": unknown, "page_number": 0})

    assert page_without_document.status_code == 422
    assert unknown_document.status_code == 404
    assert invalid_page.status_code == 422


# --- Estrategias -----------------------------------------------------------------------


class ReversingReranker(FakeLLMProvider):
    """Elige los candidatos en orden inverso, para comprobar que se respeta su elección."""

    def rerank(self, question: str, candidates: Sequence[ContextChunk], top_n: int) -> RerankResult:
        self.rerank_calls.append((question, list(candidates), top_n))
        refs = [chunk.ref for chunk in reversed(candidates)][:top_n] + ["C999"]  # inventado
        return RerankResult(refs=refs, input_tokens=0, output_tokens=0)


class FailingReranker(FakeLLMProvider):
    def rerank(self, question: str, candidates: Sequence[ContextChunk], top_n: int) -> RerankResult:
        raise LLMError("caído")


def test_rerank_reads_the_chunks_chosen_by_the_llm(db_session: Session, settings: Settings) -> None:
    settings = settings.model_copy(
        update={"rag_strategy": "rerank", "rag_rerank_candidates": 8, "retrieval_min_score": 0}
    )
    create_long_document(db_session, settings, pages=8)
    llm = ReversingReranker()

    rag.answer_question(db_session, FakeEmbeddingProvider(), llm, settings, "norma tema")

    [(_, candidates, top_n)] = llm.rerank_calls
    assert (len(candidates), top_n) == (8, 5)
    [(_, context)] = llm.calls
    # Los 5 elegidos (los últimos candidatos, en orden inverso); el id inventado se ignora.
    assert [c.text for c in context] == [c.text for c in reversed(candidates)][:5]


def test_rerank_failure_falls_back_to_search_order(db_session: Session, settings: Settings) -> None:
    settings = settings.model_copy(update={"rag_strategy": "rerank", "retrieval_min_score": 0})
    create_long_document(db_session, settings, pages=8)
    llm = FailingReranker()

    answer = rag.answer_question(db_session, FakeEmbeddingProvider(), llm, settings, "norma")

    assert answer.insufficient_evidence is False
    [(_, context)] = llm.calls
    assert len(context) == 5


def test_progressive_tries_more_chunks_until_it_finds_an_answer(
    db_session: Session, settings: Settings
) -> None:
    settings = settings.model_copy(update={"rag_strategy": "progressive", "retrieval_min_score": 0})
    create_long_document(db_session, settings, pages=20)
    llm = FakeLLMProvider(scripted=ABSTAIN)

    answer = rag.answer_question(db_session, FakeEmbeddingProvider(), llm, settings, "norma")

    # 5, luego los 5 siguientes y luego 10 más; ningún fragmento se repite.
    assert [len(context) for _, context in llm.calls] == [5, 5, 10]
    texts = [c.text for _, context in llm.calls for c in context]
    assert len(set(texts)) == 20
    assert answer.insufficient_evidence is True


def test_progressive_stops_at_the_first_answer(db_session: Session, settings: Settings) -> None:
    settings = settings.model_copy(update={"rag_strategy": "progressive", "retrieval_min_score": 0})
    create_long_document(db_session, settings, pages=20)
    llm = FakeLLMProvider()

    answer = rag.answer_question(db_session, FakeEmbeddingProvider(), llm, settings, "norma")

    assert len(llm.calls) == 1
    assert answer.insufficient_evidence is False
