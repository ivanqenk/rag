"""Evaluación del RAG con el conjunto versionado de evaluation/dataset.json.

Mide, para cada pregunta:
- Recuperación: si el fragmento relevante (documento y página esperados) está entre los
  resultados de la búsqueda.
- Citas: si la respuesta cita el documento (y la página) esperados.
- Contenido: si la respuesta incluye los datos esperados (aproximación a "está respaldada").
- Abstención: si dice "no lo sé" cuando no hay evidencia, y solo entonces.
- Prompt injection: si la respuesta contiene texto prohibido.
- Latencia, tokens y costo aproximado.

Uso (desde backend/):
    uv run python -m evaluation.run                        # proveedores falsos: gratis
    uv run python -m evaluation.run --provider openai      # real: ~$0.01 por ejecución
    uv run python -m evaluation.run --provider openai --pause 7   # cuenta en "Free tier"

Necesita PostgreSQL (`docker compose up -d db`). Usa la base de PRUEBAS (se vacía al empezar),
nunca la de desarrollo. Con los proveedores falsos solo se comprueba que el proceso funciona:
el buscador falso no entiende el significado, así que la calidad medida no es representativa.
"""

import argparse
import json
import os
import statistics
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services import ingestion, rag, retrieval
from app.services.embeddings import EmbeddingProvider, build_embedding_provider
from app.services.llm import (
    LLMProvider,
    LLMResult,
    RerankResult,
    RewriteResult,
    SummaryResult,
    VerificationResult,
    build_llm_provider,
)
from app.services.prompts import (
    ANSWER_STYLES,
    PROMPT_VERSION,
    RERANK_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    VERIFY_PROMPT_VERSION,
    ContextChunk,
)
from app.services.storage import LocalFileStorage
from tests.pdf_factory import make_pdf

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = Path(__file__).with_name("dataset.json")
RESULTS_DIR = Path(__file__).with_name("results")
DEFAULT_DATABASE_URL = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel_test"


class MeteredLLM:
    """Envuelve un proveedor de LLM y acumula los tokens usados, para estimar el costo."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.model_name = inner.model_name
        self.input_tokens = 0
        self.output_tokens = 0

    def generate_answer(
        self, question: str, context: list[ContextChunk], style: str = "brief"
    ) -> LLMResult:
        result = self._inner.generate_answer(question, context, style)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        return result

    def generate_summary(self, filename: str, chunks: list[ContextChunk]) -> SummaryResult:
        result = self._inner.generate_summary(filename, chunks)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        return result

    def verify(
        self, question: str, claims: list[tuple[str, str, list[ContextChunk]]]
    ) -> VerificationResult:
        result = self._inner.verify(question, claims)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        return result

    def rewrite_question(self, question: str, history: list[tuple[str, str]]) -> RewriteResult:
        result = self._inner.rewrite_question(question, history)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        return result

    def rerank(self, question: str, candidates: list[ContextChunk], top_n: int) -> RerankResult:
        result = self._inner.rerank(question, candidates, top_n)
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        return result


@dataclass
class QuestionResult:
    id: str
    type: str
    style: str
    question: str
    # Cómo se entendió una pregunta de seguimiento (None si no hubo conversación o no cambió).
    standalone_question: str | None
    answer: str
    points: list[str]
    points_ordered: bool
    # Si se esperaban puntos numerados (procedimiento) y coincidió. None si no aplica.
    ordered_correct: bool | None
    # Afirmaciones descartadas por el servidor (sin cita válida o sin respaldo verificado).
    removed_claims: list[str]
    abstained: bool
    expected_abstention: bool
    abstention_correct: bool
    # Si el LLM leyó algún fragmento de la página esperada. None si no aplica (resumen o
    # sin respuesta).
    retrieval_hit: bool | None
    best_vector_similarity: float | None
    citation_correct: bool | None
    content_correct: bool | None
    forbidden_text_found: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class Report:
    dataset_version: str
    provider: str
    embedding_model: str
    llm_model: str
    prompt_versions: list[str]
    rag_strategy: str
    retrieval_min_score: float
    started_at: str
    metrics: dict[str, Any] = field(default_factory=dict)
    questions: list[QuestionResult] = field(default_factory=list)


def _cost(settings: Settings, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * settings.llm_input_price_per_mtok
        + output_tokens * settings.llm_output_price_per_mtok
    ) / 1_000_000


def _fold(text: str) -> str:
    """Minúsculas y sin tildes: «Desconéctalo» debe contar como «desconect»."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _includes(answer: str, groups: list[list[str]]) -> bool:
    """Cada grupo es una lista de alternativas; todos los grupos deben aparecer."""
    folded = _fold(answer)
    return all(any(_fold(option) in folded for option in group) for group in groups)


def _document_bytes(spec: dict[str, Any], dataset_dir: Path) -> bytes:
    """Un documento del conjunto: texto por páginas (se genera el PDF) o un PDF real
    (`path`, relativo al archivo del conjunto; no se versiona)."""
    if "pages" in spec:
        return make_pdf(spec["pages"])
    path = dataset_dir / spec["path"]
    if not path.is_file():
        raise SystemExit(f"Falta {path}: este conjunto usa un PDF que no está en el repositorio.")
    return path.read_bytes()


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def prepare_database(database_url: str) -> Engine:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE documents, document_chunks, folders, usage_daily"))
    return engine


def run_evaluation(
    engine: Engine,
    settings: Settings,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    dataset: dict[str, Any],
    pause_seconds: float = 0,
    provider_label: str = "fake",
    dataset_dir: Path = DATASET_PATH.parent,
    style: str | None = None,
) -> Report:
    """`style` fuerza un formato de respuesta para todas las preguntas; si no, cada pregunta
    usa el suyo (o breve)."""
    metered = MeteredLLM(llm)
    report = Report(
        dataset_version=dataset["version"],
        provider=provider_label,
        embedding_model=embedder.model_name,
        llm_model=llm.model_name,
        prompt_versions=[
            PROMPT_VERSION,
            RERANK_PROMPT_VERSION,
            VERIFY_PROMPT_VERSION,
            SUMMARY_PROMPT_VERSION,
        ],
        rag_strategy=settings.rag_strategy,
        retrieval_min_score=settings.retrieval_min_score,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    with tempfile.TemporaryDirectory() as storage_dir, Session(engine) as session:
        storage = LocalFileStorage(Path(storage_dir))
        document_ids: dict[str, UUID] = {}
        for spec in dataset["documents"]:
            document = ingestion.register_upload(
                session, storage, settings, spec["filename"], _document_bytes(spec, dataset_dir)
            )
            document = ingestion.process_document(
                session, storage, embedder, metered, settings, document.id
            )
            if document.status != "completed":
                raise RuntimeError(f"{spec['filename']}: {document.error_message}")
            document_ids[spec["id"]] = document.id
            time.sleep(pause_seconds)
        ingestion_cost = _cost(settings, metered.input_tokens, metered.output_tokens)

        for spec in dataset["questions"]:
            question_style = style or spec.get("style", "brief")
            report.questions.append(
                _evaluate_question(
                    session, settings, embedder, metered, spec, document_ids, question_style
                )
            )
            time.sleep(pause_seconds)

    report.metrics = _aggregate(report.questions, ingestion_cost)
    return report


def _evaluate_question(
    session: Session,
    settings: Settings,
    embedder: EmbeddingProvider,
    llm: MeteredLLM,
    spec: dict[str, Any],
    document_ids: dict[str, UUID],
    style: str = "brief",
) -> QuestionResult:
    question = spec["question"]
    expected_doc = document_ids.get(spec["document"]) if spec["document"] else None
    expected_page = spec["page"]
    expected_abstention = spec["type"] == "unanswerable"
    # Preguntas hechas desde un documento o una página concretos ("¿en qué año fue esto?").
    spec_filter = spec.get("filter", {})
    filter_document = document_ids[spec_filter["document"]] if "document" in spec_filter else None
    filter_page = spec_filter.get("page")

    # Búsqueda aparte, sin umbral, solo para ver la similitud (calibrar el umbral). Repite el
    # embedding de la pregunta: costo despreciable.
    unfiltered = settings.model_copy(update={"retrieval_min_score": 0.0})
    scope = retrieval.Scope(document_id=filter_document, page_number=filter_page)
    candidates = retrieval.search(
        session, embedder, unfiltered, question, settings.retrieval_top_k, scope
    )
    similarities = [c.vector_similarity for c in candidates if c.vector_similarity is not None]
    best_similarity = round(max(similarities), 3) if similarities else None

    tokens_before = (llm.input_tokens, llm.output_tokens)
    started = time.perf_counter()
    # Preguntas de seguimiento: la conversación previa, como la enviaría el navegador.
    history = [(turn[0], turn[1]) for turn in spec.get("history", [])]
    answer = rag.answer_question(session, embedder, llm, settings, question, scope, style, history)
    latency_ms = (time.perf_counter() - started) * 1000
    input_tokens = llm.input_tokens - tokens_before[0]
    output_tokens = llm.output_tokens - tokens_before[1]

    retrieval_hit: bool | None = None
    if expected_doc is not None and expected_page is not None:
        retrieval_hit = (expected_doc, expected_page) in answer.considered

    # El contenido se busca en el resumen y en los puntos.
    full_text = " ".join([answer.answer, *(p.text for p in answer.points)])
    citation_correct: bool | None = None
    content_correct: bool | None = None
    if not expected_abstention:
        citation_correct = any(
            s.document_id == expected_doc
            and (expected_page is None or s.page_number == expected_page)
            for s in answer.sources
        )
        content_correct = not answer.insufficient_evidence and _includes(
            full_text, spec.get("must_include", [])
        )
    forbidden = any(_fold(t) in _fold(full_text) for t in spec.get("must_not_include", []))

    return QuestionResult(
        id=spec["id"],
        type=spec["type"],
        style=style,
        question=question,
        standalone_question=answer.standalone_question,
        answer=answer.answer,
        points=[p.text for p in answer.points],
        points_ordered=answer.points_ordered,
        ordered_correct=(
            answer.points_ordered == spec["expect_ordered"]
            if "expect_ordered" in spec and not answer.insufficient_evidence
            else None
        ),
        removed_claims=answer.removed_claims,
        abstained=answer.insufficient_evidence,
        expected_abstention=expected_abstention,
        abstention_correct=answer.insufficient_evidence == expected_abstention,
        retrieval_hit=retrieval_hit,
        best_vector_similarity=best_similarity,
        citation_correct=citation_correct,
        content_correct=content_correct,
        forbidden_text_found=forbidden,
        latency_ms=round(latency_ms, 1),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost(settings, input_tokens, output_tokens),
    )


def _aggregate(results: list[QuestionResult], ingestion_cost: float) -> dict[str, Any]:
    answerable = [r for r in results if not r.expected_abstention]
    unanswerable = [r for r in results if r.expected_abstention]
    latencies = sorted(r.latency_ms for r in results)
    relevant_sims = [
        r.best_vector_similarity
        for r in answerable
        if r.retrieval_hit is not None and r.best_vector_similarity is not None
    ]
    unanswerable_sims = [
        r.best_vector_similarity for r in unanswerable if r.best_vector_similarity is not None
    ]
    return {
        "questions": len(results),
        "retrieval_hit_rate": _rate(
            [r.retrieval_hit for r in results if r.retrieval_hit is not None]
        ),
        "citation_accuracy": _rate([bool(r.citation_correct) for r in answerable]),
        "content_accuracy": _rate([bool(r.content_correct) for r in answerable]),
        "correct_abstention_rate": _rate([r.abstained for r in unanswerable]),
        "false_abstention_rate": _rate([r.abstained for r in answerable]),
        "injection_resisted": _rate(
            [not r.forbidden_text_found for r in results if r.type == "injection"]
        ),
        # Preguntas que invitan a añadir lo que no está en los documentos (consejos genéricos):
        # 1.0 = ninguna respuesta contuvo el texto prohibido.
        "grounding_resisted": _rate(
            [not r.forbidden_text_found for r in results if r.type == "grounding"]
        ),
        "removed_claims_total": sum(len(r.removed_claims) for r in results),
        # Respuestas detalladas: numeradas si son un procedimiento, y solo entonces.
        "ordered_accuracy": _rate(
            [r.ordered_correct for r in results if r.ordered_correct is not None]
        ),
        "latency_ms_p50": round(statistics.median(latencies), 1),
        "latency_ms_max": latencies[-1],
        "query_cost_usd_avg": round(statistics.fmean(r.cost_usd for r in results), 6),
        "total_cost_usd": round(sum(r.cost_usd for r in results) + ingestion_cost, 6),
        # Para calibrar RETRIEVAL_MIN_SCORE: el umbral debería quedar entre ambos valores.
        "min_similarity_answerable": min(relevant_sims) if relevant_sims else None,
        "max_similarity_unanswerable": max(unanswerable_sims) if unanswerable_sims else None,
    }


def _mark(value: bool | None) -> str:
    return "—" if value is None else ("✓" if value else "✗")


def print_report(report: Report) -> None:
    print(
        f"\nEvaluación {report.dataset_version} · proveedor={report.provider} · "
        f"embeddings={report.embedding_model} · LLM={report.llm_model} · "
        f"estrategia={report.rag_strategy} · umbral={report.retrieval_min_score}\n"
    )
    print(
        f"{'id':4} {'tipo':15} {'formato':8} {'recup':5} {'cita':4} {'datos':5} {'abst':4} "
        f"{'invent':6} {'sim':>5} {'ms':>7}"
    )
    for r in report.questions:
        sim = f"{r.best_vector_similarity:.2f}" if r.best_vector_similarity is not None else "—"
        print(
            f"{r.id:4} {r.type:15} {r.style:8} {_mark(r.retrieval_hit):5} "
            f"{_mark(r.citation_correct):4} {_mark(r.content_correct):5} "
            f"{_mark(r.abstention_correct):4} {'✗' if r.forbidden_text_found else '✓':6} "
            f"{sim:>5} {r.latency_ms:7.0f}"
        )
    print("\nMétricas:")
    for name, value in report.metrics.items():
        print(f"  {name:28} {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--provider", choices=["fake", "openai"], default="fake")
    parser.add_argument(
        "--dataset", type=Path, default=DATASET_PATH, help="conjunto (por defecto dataset.json)"
    )
    parser.add_argument(
        "--strategy",
        choices=["simple", "rerank", "progressive"],
        help="RAG_STRATEGY a evaluar (por defecto, la de la configuración)",
    )
    parser.add_argument(
        "--style",
        choices=ANSWER_STYLES,
        help="fuerza un formato de respuesta para todas las preguntas",
    )
    parser.add_argument(
        "--pause", type=float, default=0, help="segundos entre llamadas (límites por minuto)"
    )
    args = parser.parse_args()
    provider: Literal["fake", "openai"] = args.provider

    settings = get_settings().model_copy(
        update={"embeddings_provider": provider, "llm_provider": provider}
    )
    if args.strategy:
        settings = settings.model_copy(update={"rag_strategy": args.strategy})
    if provider == "fake":
        # Calibrado para el buscador falso (ver tests/integration/conftest.py).
        settings = settings.model_copy(update={"retrieval_min_score": 0.2})
    database_url = os.environ.get("EVAL_DATABASE_URL", DEFAULT_DATABASE_URL)

    dataset_path: Path = args.dataset.resolve()
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    engine = prepare_database(database_url)
    report = run_evaluation(
        engine,
        settings,
        build_embedding_provider(settings),
        build_llm_provider(settings),
        dataset,
        pause_seconds=args.pause,
        provider_label=provider,
        dataset_dir=dataset_path.parent,
        style=args.style,
    )
    print_report(report)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = f"{dataset['version']}-{provider}-{settings.rag_strategy}-{args.style or 'mixto'}"
    output = RESULTS_DIR / f"{label}-{stamp}.json"
    output.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nInforme completo: {output.relative_to(BACKEND_DIR)}")


if __name__ == "__main__":
    main()
