"""Unit tests for vector_store._point_id -- pure and offline, no Qdrant or
OpenAI needed, unlike the rest of tests/rag/test_vector_store.py.
"""

from gstrecon.rag.corpus.chunker import LawChunk
from gstrecon.rag.retrieval.vector_store import _point_id


def _chunk(
    section_number: str = "138B", part: int | None = None, text: str = "some text"
) -> LawChunk:
    return LawChunk(
        source_document="CGST Rules",
        chapter=None,
        section_number=section_number,
        section_title="Verification of documents and conveyances",
        text=text,
        part=part,
    )


def test_identical_chunk_produces_identical_id() -> None:
    # The idempotency property upsert_chunks relies on: re-embedding the
    # same content on a subsequent run must overwrite, not duplicate.
    a = _chunk(text="identical content")
    b = _chunk(text="identical content")
    assert _point_id(a) == _point_id(b)


def test_same_section_and_part_but_different_content_gets_different_ids() -> None:
    # Regression: the real CGST Rules PDF quotes an old, pre-amendment
    # version of rule 138B in full inside an inline footnote, producing two
    # distinct chunks that share (source_document, section_number, part)
    # but have different text. Before this fix, both got the same point ID
    # and the second upsert silently discarded the first -- verified by a
    # real point-count mismatch (407 points in Qdrant vs 413 chunks
    # embedded) before the fix, and 418/418 matching after it.
    old_version = _chunk(text="old pre-amendment text quoted in a footnote")
    current_version = _chunk(text="current rule text")
    assert _point_id(old_version) != _point_id(current_version)


def test_different_parts_of_the_same_section_get_different_ids() -> None:
    part_1 = _chunk(section_number="2", part=1, text="first half")
    part_2 = _chunk(section_number="2", part=2, text="second half")
    assert _point_id(part_1) != _point_id(part_2)
