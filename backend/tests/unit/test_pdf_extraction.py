import pytest

from app.services.pdf_extraction import (
    InvalidPdfError,
    extract_pages,
    has_pdf_signature,
    validate_pdf,
)
from tests.pdf_factory import make_encrypted_pdf, make_pdf


def test_extracts_text_per_page() -> None:
    pages = extract_pages(make_pdf(["Primera página", "", "Tercera página"]))

    assert [p.page_number for p in pages] == [1, 2, 3]
    assert "Primera página" in pages[0].text
    assert pages[1].text.strip() == ""
    assert "Tercera página" in pages[2].text


def test_signature_detection() -> None:
    assert has_pdf_signature(make_pdf(["hola"]))
    assert not has_pdf_signature(b"Esto es un archivo de texto")
    assert not has_pdf_signature(b"MZ\x90\x00 ejecutable")


def test_valid_pdf_passes_validation() -> None:
    validate_pdf(make_pdf(["hola"]), max_pages=10)


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(InvalidPdfError) as exc_info:
        validate_pdf(b"%PDF-1.7\nesto no es un PDF de verdad", max_pages=10)

    assert exc_info.value.code == "invalid_pdf"


def test_encrypted_pdf_is_rejected() -> None:
    with pytest.raises(InvalidPdfError) as exc_info:
        validate_pdf(make_encrypted_pdf(), max_pages=10)

    assert exc_info.value.code == "encrypted_pdf"


def test_pdf_with_too_many_pages_is_rejected() -> None:
    with pytest.raises(InvalidPdfError) as exc_info:
        validate_pdf(make_pdf(["a", "b", "c"]), max_pages=2)

    assert exc_info.value.code == "too_many_pages"
