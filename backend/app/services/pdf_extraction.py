"""Validación de PDF y extracción de texto por página con PyMuPDF.

PyMuPDF solo lee el contenido: no ejecuta JavaScript, formularios ni otro contenido
activo del PDF.
"""

from dataclasses import dataclass

import pymupdf

# Todo PDF contiene esta firma ("magic bytes") al principio. Los lectores toleran algunos
# bytes antes de ella, así que la buscamos en el primer kilobyte.
_PDF_SIGNATURE = b"%PDF-"


@dataclass(frozen=True)
class PageText:
    page_number: int  # empieza en 1, como lo ve una persona
    text: str


class InvalidPdfError(Exception):
    """El archivo parece un PDF pero no se puede procesar. `message` es apto para el usuario."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def has_pdf_signature(data: bytes) -> bool:
    return _PDF_SIGNATURE in data[:1024]


def validate_pdf(data: bytes, max_pages: int) -> None:
    """Comprueba que PyMuPDF puede abrir el PDF y que es razonable procesarlo."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise InvalidPdfError(
            "invalid_pdf", "El archivo no es un PDF válido o está dañado."
        ) from exc

    with document:
        if document.needs_pass:
            raise InvalidPdfError(
                "encrypted_pdf", "El PDF está protegido con contraseña y no se puede leer."
            )
        if document.page_count == 0:
            raise InvalidPdfError("empty_pdf", "El PDF no tiene páginas.")
        if document.page_count > max_pages:
            raise InvalidPdfError(
                "too_many_pages", f"El PDF supera el máximo de {max_pages} páginas."
            )


def extract_pages(data: bytes) -> list[PageText]:
    """Devuelve el texto de cada página (puede ser vacío si la página es una imagen)."""
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return [
            PageText(page_number=index + 1, text=page.get_text())
            for index, page in enumerate(document)
        ]
