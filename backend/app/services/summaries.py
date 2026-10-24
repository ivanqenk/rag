"""Resumen automático de documentos y detección de preguntas de resumen.

Problema que resuelve: la búsqueda RAG recupera los fragmentos más parecidos a la pregunta,
y una pregunta como "¿de qué trata?" no se parece a ningún fragmento concreto. Por eso,
al procesar cada documento se genera un resumen una sola vez, y las preguntas de resumen
usan esos resúmenes como contexto en lugar de la búsqueda.
"""

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import replace

from app.core.config import Settings
from app.services.chunking import TextChunk
from app.services.llm import LLMError, LLMProvider
from app.services.prompts import SUMMARY_PROMPT_VERSION, ContextChunk

logger = logging.getLogger(__name__)

# Se comparan sin tildes y en minúsculas (ver _normalize). Heurística deliberadamente
# simple y explicable; las preguntas que no encajan siguen el camino RAG normal.
_SUMMARY_PATTERNS = [
    r"\bde que (trata|va|habla)",
    r"\bsobre que (trata|es|va|habla)",
    r"\bresum",  # resume, resumen, resúmeme, resumir…
    r"\b(idea|tema|punto)s? (principal|clave)",
    r"\bsummar",  # summary, summarize, summarise
    r"\bwhat\b.*\b(document|file|pdf|report|paper)s?\b.*\babout\b",
    r"\bmain (idea|topic|point)s?\b",
]
_SUMMARY_RE = re.compile("|".join(_SUMMARY_PATTERNS))


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def is_summary_question(question: str) -> bool:
    """True si la pregunta pide un resumen o de qué trata un documento."""
    return _SUMMARY_RE.search(_normalize(question)) is not None


def select_summary_chunks(chunks: Sequence[TextChunk], max_chars: int) -> list[TextChunk]:
    """Elige fragmentos repartidos por todo el documento sin superar `max_chars`.

    Si el documento cabe entero, se usa entero. Si no, se toman fragmentos a intervalos
    regulares: así el resumen ve el principio, el medio y el final, no solo el principio.
    """
    if sum(len(chunk.text) for chunk in chunks) <= max_chars:
        return list(chunks)
    average = sum(len(chunk.text) for chunk in chunks) / len(chunks)
    count = max(1, min(len(chunks), int(max_chars // average)))
    step = len(chunks) / count
    candidates = [chunks[int(i * step)] for i in range(count)]

    selected: list[TextChunk] = []
    used = 0
    for chunk in candidates:
        if used + len(chunk.text) > max_chars:
            continue
        used += len(chunk.text)
        selected.append(chunk)
    # Garantiza al menos algo de texto aunque un solo fragmento supere el límite.
    return selected or [replace(chunks[0], text=chunks[0].text[:max_chars])]


def summarize_document(
    llm: LLMProvider | None,
    settings: Settings,
    filename: str,
    chunks: Sequence[TextChunk],
) -> str | None:
    """Genera el resumen o devuelve None si no hay LLM o el proveedor falla.

    El resumen es un extra: si falla, el documento sigue siendo consultable con normalidad.
    """
    if llm is None or not chunks:
        return None
    selected = select_summary_chunks(chunks, settings.summary_max_input_chars)
    context = [
        ContextChunk(
            ref=str(chunk.chunk_index),
            filename=filename,
            page_number=chunk.page_number,
            text=chunk.text,
        )
        for chunk in selected
    ]
    try:
        result = llm.generate_summary(filename, context)
    except LLMError as exc:
        logger.warning("No se pudo generar el resumen: %s", exc.message)
        return None

    summary = result.summary.strip()[: settings.summary_max_chars]
    cost = (
        result.input_tokens * settings.llm_input_price_per_mtok
        + result.output_tokens * settings.llm_output_price_per_mtok
    ) / 1_000_000
    logger.info(
        "Resumen generado: %d fragmentos de %d, modelo=%s, prompt=%s, tokens=%d/%d, costo~$%.6f",
        len(selected),
        len(chunks),
        llm.model_name,
        SUMMARY_PROMPT_VERSION,
        result.input_tokens,
        result.output_tokens,
        cost,
    )
    return summary or None
