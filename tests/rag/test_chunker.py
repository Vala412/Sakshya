from gstrecon.rag.corpus.chunker import LawChunk, _split_oversized, chunk_document
from gstrecon.rag.corpus.extract import truncate_before_appendix

# A miniature document shaped like the real CBIC PDFs: chapter headers
# repeating (as they do on every page of the source PDF), numbered
# sections with the "<num>. <title>. -- <body>" shape, and a lettered
# section number (10A-style) to check that pattern is recognized too.
SAMPLE_DOCUMENT = """
CHAPTER I PRELIMINARY

1. Short title, extent and commencement. — (1) This Act may be called
the Central Goods and Services Tax Act, 2017.

2. Definitions. — In this Act, unless the context otherwise requires,—
(1) "actionable claim" shall have the same meaning as assigned to it in
section 3 of the Transfer of Property Act, 1882.

CHAPTER I PRELIMINARY

CHAPTER V INPUT TAX CREDIT

16. Eligibility and conditions for taking input tax credit. — (1) Every
registered person shall be entitled to take credit of input tax charged
on any supply of goods or services, as specified in section 49.

CHAPTER V INPUT TAX CREDIT

17. Apportionment of credit and blocked credits. — (1) Where goods or
services are used partly for business and partly for other purposes.
(5) Input tax credit shall not be available in respect of the following.

CHAPTER VI REGISTRATION

10A. Registration for a class of persons. — The Government may notify a
class of persons who shall be granted registration.
"""


def test_chapter_and_section_are_correctly_attached() -> None:
    chunks = chunk_document(SAMPLE_DOCUMENT, source_document="Test Act")
    by_number = {c.section_number: c for c in chunks}

    assert by_number["16"].chapter == "Chapter V: INPUT TAX CREDIT"
    assert by_number["16"].section_title == "Eligibility and conditions for taking input tax credit"
    assert "section 49" in by_number["16"].text

    assert by_number["1"].chapter == "Chapter I: PRELIMINARY"
    assert by_number["2"].chapter == "Chapter I: PRELIMINARY"


def test_lettered_section_number_is_recognized() -> None:
    chunks = chunk_document(SAMPLE_DOCUMENT, source_document="Test Act")
    by_number = {c.section_number: c for c in chunks}
    assert "10A" in by_number
    assert by_number["10A"].chapter == "Chapter VI: REGISTRATION"


def test_section_body_stops_at_the_next_section_header() -> None:
    chunks = chunk_document(SAMPLE_DOCUMENT, source_document="Test Act")
    by_number = {c.section_number: c for c in chunks}
    assert "Apportionment" not in by_number["16"].text
    assert "blocked credits" in by_number["17"].text
    assert "sub-section" not in by_number["17"].text  # didn't bleed into section 10A


def test_citation_property_is_human_readable() -> None:
    chunks = chunk_document(SAMPLE_DOCUMENT, source_document="Test Act")
    section_16 = next(c for c in chunks if c.section_number == "16")
    assert section_16.citation == (
        "Test Act, Section 16 (Eligibility and conditions for taking input tax credit)"
    )


def test_repeated_chapter_headers_do_not_create_duplicate_chunks() -> None:
    chunks = chunk_document(SAMPLE_DOCUMENT, source_document="Test Act")
    numbers = [c.section_number for c in chunks]
    assert len(numbers) == len(set(numbers))


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_document("", source_document="Test Act") == []


def _chunk(text: str, section_number: str = "2") -> LawChunk:
    return LawChunk(
        source_document="Test Act",
        chapter=None,
        section_number=section_number,
        section_title="Definitions",
        text=text,
    )


class TestSplitOversized:
    def test_short_chunk_is_returned_unsplit(self) -> None:
        chunk = _chunk("short text")
        result = _split_oversized(chunk, max_chars=100)
        assert result == [chunk]
        assert result[0].part is None

    def test_long_chunk_is_split_on_paragraph_boundaries(self) -> None:
        paragraphs = [f"({i}) clause number {i} with some words in it." for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = _split_oversized(_chunk(text), max_chars=200)

        assert len(result) > 1
        # Every piece stays under the budget.
        assert all(len(piece.text) <= 200 for piece in result)
        # Parts are numbered from 1, in order, with no gaps.
        assert [piece.part for piece in result] == list(range(1, len(result) + 1))
        # Metadata is preserved on every part.
        assert all(piece.section_number == "2" for piece in result)
        # No paragraph is lost -- every one appears in some piece.
        assert all(any(paragraph in piece.text for piece in result) for paragraph in paragraphs)
        # Consecutive pieces share trailing/leading text (the overlap).
        # strict=False is correct (not just quieting the linter): this is
        # the pairwise idiom, where result[1:] is intentionally one shorter.
        for prev, nxt in zip(result, result[1:], strict=False):
            tail = prev.text[-(200 // 5) :]
            assert tail in nxt.text

    def test_no_overlap_when_explicitly_disabled(self) -> None:
        paragraphs = [f"({i}) clause number {i} with some words in it." for i in range(20)]
        text = "\n\n".join(paragraphs)
        result = _split_oversized(_chunk(text), max_chars=200, overlap_chars=0)
        # With overlap off, concatenating pieces reproduces the original text.
        assert "".join(paragraphs) in "".join(p.text.replace("\n\n", "") for p in result)

    def test_single_paragraph_longer_than_budget_is_hard_split(self) -> None:
        text = "a" * 500  # one giant "paragraph", no blank lines to split on
        result = _split_oversized(_chunk(text), max_chars=100, overlap_chars=0)
        assert len(result) == 5
        assert all(len(piece.text) == 100 for piece in result)

    def test_hard_split_pieces_overlap(self) -> None:
        text = "".join(f"{i:04d}" for i in range(200))  # distinguishable, no blank lines
        result = _split_oversized(_chunk(text), max_chars=100)
        assert len(result) > 1
        for prev, nxt in zip(result, result[1:], strict=False):
            assert prev.text[-20:] == nxt.text[:20]

    def test_citation_is_unaffected_by_splitting(self) -> None:
        text = "\n\n".join(f"({i}) clause {i}" for i in range(50))
        result = _split_oversized(_chunk(text), max_chars=50)
        citations = {piece.citation for piece in result}
        # Same citation for every part -- "part" is retrieval bookkeeping,
        # not something that belongs in a citation shown to a user.
        assert citations == {"Test Act, Section 2 (Definitions)"}


class TestTruncateBeforeAppendix:
    def test_truncates_at_second_occurrence(self) -> None:
        text = "TOC\nAPPENDIX HERE\nmain body text\nMORE\nAPPENDIX HERE\nappendix content"
        result = truncate_before_appendix(text, "APPENDIX HERE")
        assert result == "TOC\nAPPENDIX HERE\nmain body text\nMORE\n"
        assert "appendix content" not in result

    def test_single_occurrence_is_left_unchanged(self) -> None:
        text = "TOC\nsome text\nAPPENDIX HERE\nappendix content"
        assert truncate_before_appendix(text, "APPENDIX HERE") == text

    def test_no_occurrence_is_left_unchanged(self) -> None:
        text = "no marker at all here"
        assert truncate_before_appendix(text, "APPENDIX HERE") == text
