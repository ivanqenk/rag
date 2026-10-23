import pytest

from app.services.chunking import chunk_pages, normalize_text, split_text
from app.services.pdf_extraction import PageText

WORDS = " ".join(f"palabra{i:03d}" for i in range(300))  # ~3000 caracteres


def test_normalize_collapses_whitespace_and_removes_nul() -> None:
    assert normalize_text("  hola\n\n  mundo\t\x00fin ") == "hola mundo fin"


def test_short_text_is_a_single_chunk() -> None:
    assert split_text("Texto corto.", chunk_size=100, chunk_overlap=20) == ["Texto corto."]


def test_empty_or_blank_text_produces_no_chunks() -> None:
    assert split_text("   \n\t ", chunk_size=100, chunk_overlap=20) == []


def test_chunks_respect_max_size() -> None:
    chunks = split_text(WORDS, chunk_size=200, chunk_overlap=50)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_chunks_do_not_split_words() -> None:
    words = set(WORDS.split())

    for chunk in split_text(WORDS, chunk_size=200, chunk_overlap=50):
        assert set(chunk.split()) <= words


def test_consecutive_chunks_overlap() -> None:
    chunks = split_text(WORDS, chunk_size=200, chunk_overlap=50)

    for previous, current in zip(chunks, chunks[1:], strict=False):
        # La primera palabra de un fragmento ya aparecía al final del anterior.
        assert current.split()[0] in previous.split()


def test_without_overlap_all_text_is_kept_once() -> None:
    chunks = split_text(WORDS, chunk_size=200, chunk_overlap=0)

    assert " ".join(chunks).split() == WORDS.split()


def test_with_overlap_no_text_is_lost() -> None:
    chunks = split_text(WORDS, chunk_size=200, chunk_overlap=50)

    covered = set(" ".join(chunks).split())
    assert covered == set(WORDS.split())


def test_long_word_without_spaces_still_terminates() -> None:
    chunks = split_text("x" * 1000, chunk_size=300, chunk_overlap=100)

    assert all(len(chunk) <= 300 for chunk in chunks)
    assert "".join(chunks).count("x") >= 1000


@pytest.mark.parametrize("overlap", [-1, 100, 150])
def test_invalid_overlap_is_rejected(overlap: int) -> None:
    with pytest.raises(ValueError):
        split_text(WORDS, chunk_size=100, chunk_overlap=overlap)


def test_chunk_pages_keeps_page_numbers_and_global_index() -> None:
    pages = [
        PageText(page_number=1, text=WORDS[:500]),
        PageText(page_number=2, text=""),  # página sin texto: no genera fragmentos
        PageText(page_number=3, text="Final del documento."),
    ]

    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=50)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 3}
    assert chunks[-1].page_number == 3
    assert chunks[-1].text == "Final del documento."
