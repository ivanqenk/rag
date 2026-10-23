"""Genera PDFs de prueba en memoria, para no versionar archivos binarios."""

import pymupdf


def make_pdf(pages: list[str]) -> bytes:
    """Un PDF con una página por elemento; una cadena vacía produce una página sin texto."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=9)
    return document.tobytes()


def make_encrypted_pdf() -> bytes:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Contenido secreto")
    return document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="usuario", owner_pw="propietario"
    )
