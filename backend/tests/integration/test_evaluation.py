"""La evaluación RAG (evaluation/run.py) se ejecuta de punta a punta con proveedores falsos.

No mide calidad (el buscador falso no entiende el significado): solo evita que el script de
evaluación se rompa sin que nadie lo note.
"""

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider
from evaluation.run import DATASET_PATH, _includes, run_evaluation


@pytest.fixture
def clean_engine(engine: Engine) -> Iterator[Engine]:
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents, document_chunks"))


def test_evaluation_runs_over_the_whole_dataset(clean_engine: Engine, settings: Settings) -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    report = run_evaluation(
        clean_engine, settings, FakeEmbeddingProvider(), FakeLLMProvider(), dataset
    )

    assert [q.id for q in report.questions] == [q["id"] for q in dataset["questions"]]
    metrics = report.metrics
    assert metrics["questions"] == len(dataset["questions"])
    for name in ("citation_accuracy", "correct_abstention_rate", "false_abstention_rate"):
        assert 0 <= metrics[name] <= 1
    # Incluso con el buscador falso, las preguntas sin relación con los documentos se abstienen.
    assert metrics["correct_abstention_rate"] == 1.0
    assert metrics["total_cost_usd"] == 0


def test_dataset_is_consistent() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    documents = {d["id"]: d for d in dataset["documents"]}
    ids = [q["id"] for q in dataset["questions"]]

    assert len(ids) == len(set(ids))
    for question in dataset["questions"]:
        if question["type"] == "unanswerable":
            assert question["document"] is None
            continue
        document = documents[question["document"]]
        assert question["must_include"]
        if question["page"] is not None:
            assert 1 <= question["page"] <= len(document["pages"])


def test_content_check_ignores_case_and_accents() -> None:
    assert _includes("Desconéctalo de la red.", [["desconect"]])
    assert _includes("Son VEINTITRÉS días", [["23", "veintitres"]])
    assert not _includes("Apágalo.", [["desconect"]])
