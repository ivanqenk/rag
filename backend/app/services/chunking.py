"""División del texto en fragmentos solapados.

Decisiones:
- Se mide en caracteres, no en tokens: no depende de un tokenizador concreto y, para
  textos en español/inglés, 1000 caracteres son aprox. 200-300 tokens.
- Cada fragmento pertenece a una sola página, para poder citar la página exacta.
- Se intenta cortar en un espacio para no partir palabras.
- El solapamiento repite el final de un fragmento al inicio del siguiente, para que una
  idea que cae en el corte siga apareciendo completa en al menos uno de los dos.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.services.pdf_extraction import PageText


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int  # posición global en el documento, empezando en 0
    page_number: int
    text: str


def normalize_text(text: str) -> str:
    """Colapsa espacios y saltos de línea. Quita NUL, que PostgreSQL no admite en TEXT."""
    return " ".join(text.replace("\x00", " ").split())


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap debe estar entre 0 y chunk_size - 1")

    text = normalize_text(text)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Retrocede hasta el último espacio, pero sin encoger el fragmento a menos de la mitad.
            space = text.rfind(" ", start + chunk_size // 2, end)
            if space != -1:
                end = space
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break

        # max(..., start + 1) garantiza que siempre avanzamos (evita bucles infinitos).
        next_start = max(end - chunk_overlap, start + 1)
        # Si caímos en mitad de una palabra, saltamos al inicio de la siguiente.
        if text[next_start - 1] != " ":
            space = text.find(" ", next_start, end)
            if space != -1:
                next_start = space + 1
        start = next_start

    return [chunk for chunk in chunks if chunk]


def chunk_pages(pages: Sequence[PageText], chunk_size: int, chunk_overlap: int) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page in pages:
        for text in split_text(page.text, chunk_size, chunk_overlap):
            chunks.append(
                TextChunk(chunk_index=len(chunks), page_number=page.page_number, text=text)
            )
    return chunks
