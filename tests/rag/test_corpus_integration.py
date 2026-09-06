"""Integration test against the real downloaded CGST Act/Rules PDFs.

Skipped entirely if the corpus hasn't been fetched (e.g. a fresh clone
before running `python scripts/fetch_corpus.py`) -- this is deliberately
not a synthetic fixture: the whole point is checking extraction quality
against the actual legal text this project cites, especially the sections
the project's own docs call out as most load-bearing (16, 17, 34).
"""

from pathlib import Path

import pytest

from gstrecon.rag.corpus.chunker import chunk_document
from gstrecon.rag.corpus.extract import extract_pdf_text, truncate_before_appendix

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "corpus" / "raw"
ACT_PDF = RAW_DIR / "cgst_act.pdf"
RULES_PDF = RAW_DIR / "cgst_rules_part_a.pdf"

pytestmark = pytest.mark.skipif(
    not ACT_PDF.exists() or not RULES_PDF.exists(),
    reason="corpus not fetched -- run scripts/fetch_corpus.py first",
)


@pytest.fixture(scope="module")
def act_chunks() -> list:
    text = extract_pdf_text(ACT_PDF)
    text = truncate_before_appendix(text, "REMOVAL OF DIFFICULTY ORDERS")
    return chunk_document(text, source_document="CGST Act")


def _full_text(chunks: list, section_number: str) -> str:
    """Join every part of `section_number` back together -- a long section
    (like 17, which is split) shouldn't make a content-presence check
    fragile to exactly which part happened to land the relevant sentence.
    """
    parts = [c for c in chunks if c.section_number == section_number]
    assert parts, f"section {section_number} not found at all"
    return " ".join(c.text for c in parts)


class TestPrioritySections:
    """Sections 16, 17(5), and 34 are the ones the project's own docs name
    as most load-bearing for ITC exceptions -- if any of these silently
    failed to extract, every citation the explanation layer produces for
    the corresponding reason codes (EX-09, EX-11) would be unsupported.
    """

    def test_section_16_extracted(self, act_chunks: list) -> None:
        section = next(c for c in act_chunks if c.section_number == "16")
        assert "input tax credit" in section.section_title.lower()
        assert "electronic credit ledger" in _full_text(act_chunks, "16")

    def test_section_17_includes_blocked_credits_subsection(self, act_chunks: list) -> None:
        section = next(c for c in act_chunks if c.section_number == "17")
        assert "blocked credits" in section.section_title.lower()
        assert "shall not be available" in _full_text(act_chunks, "17")

    def test_section_34_credit_debit_notes_extracted(self, act_chunks: list) -> None:
        section = next(c for c in act_chunks if c.section_number == "34")
        assert "credit and" in section.section_title.lower()
        assert "debit note" in section.section_title.lower()


class TestOverallExtractionSanity:
    def test_extracts_a_plausible_number_of_sections(self, act_chunks: list) -> None:
        # The CGST Act has 174 sections; the regex-based splitter isn't
        # exact (see chunker.py's documented limitations), and a handful of
        # long sections are split into multiple retrieval chunks (see
        # MAX_CHUNK_CHARS), so the raw chunk count runs a bit above the
        # true section count -- this checks it's in a plausible
        # neighborhood, not an exact match.
        assert 150 <= len(act_chunks) <= 220

    def test_every_chunk_has_non_trivial_body_text(self, act_chunks: list) -> None:
        assert all(len(c.text) > 20 for c in act_chunks)

    def test_no_chunk_exceeds_the_embedding_input_budget(self, act_chunks: list) -> None:
        from gstrecon.rag.corpus.chunker import MAX_CHUNK_CHARS

        assert all(len(c.text) <= MAX_CHUNK_CHARS for c in act_chunks)

    def test_no_duplicate_section_and_part_pairs(self, act_chunks: list) -> None:
        # A long section's parts legitimately share a section_number (e.g.
        # Section 2's ~120 definitions, split across several parts) -- the
        # real invariant is that (section_number, part) is unique, not
        # section_number alone.
        keys = [(c.section_number, c.part) for c in act_chunks]
        assert len(keys) == len(set(keys))
