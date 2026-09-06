"""Section-aware chunking of GST law text, with citation-grade provenance.

Splits on the pattern CBIC's own consolidated Act/Rules PDFs use for every
numbered provision: "<number>. <Title>. -- <body>" -- e.g. "16. Eligibility
and conditions for taking input tax credit. -- (1) Every registered
person...". Chapter headings ("CHAPTER V INPUT TAX CREDIT") repeat on every
page of the source PDF; the chunker tracks the most recent one seen as it
scans forward, so each section chunk records which chapter it falls under.

This is deliberately an approximate, single-pass regex splitter, not a
general legal-citation parser -- consistent with the project's existing "no
CA review, best-available-source" posture. Known gaps:
  - A section/rule title containing a period will truncate at that period.
  - Inline amendment footnote markers (e.g. "]38") are left in chunk text;
    distinguishing them from real bracketed statutory text ("[Explanation
    ...]") is not reliably possible by regex alone.
  - The Table of Contents and Schedules are not specially handled -- text
    outside any matched section (before the first header, or a Schedule
    that doesn't follow the "<number>. <title>. --" shape) is dropped.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_CHAPTER_RE = re.compile(r"^[ \t]*CHAPTER\s+([IVXLCDM]+)\s+(.+?)\s*$", re.MULTILINE)
# Most headers are bare "<number>. <title>. --"; a rule inserted by later
# amendment is sometimes instead written "[Rule 41A. <title>. -..." with an
# explicit "Rule"/"Section" word and an opening bracket -- found by a real
# chunking failure (rule 41A wasn't recognized as a boundary, so rule 41's
# chunk silently swallowed everything up to the next bare-numbered header,
# ~36,000 characters later, well past the embedding model's input limit).
#
# The title group excludes "." but NOT "\n": a long title (like 41A's, 18+
# words) wraps across a line break in the PDF's extracted text, and an
# earlier version of this pattern used `[^.\n]*?`, which couldn't cross
# that break -- silently failing to recognize the header at all rather than
# raising, which is what let the oversized chunk above go unnoticed until
# the embedding call rejected it.
_SECTION_RE = re.compile(
    r"^[ \t]*\[?(?:Rule|Section)?\s*(\d{1,3}[A-Z]{0,2})\.\s+([A-Z][^.]*?)\.\s*[-–—]\s*",
    re.MULTILINE,
)


# Retrieval chunks are kept well under the embedding model's hard 8192-
# token input limit (roughly 32,000 characters for English legal prose),
# for two independent reasons found empirically, not assumed: (1) a
# handful of real provisions -- Section 2's ~120 definitions, rule 138's
# heavily-amended e-way-bill text -- are long enough on their own to exceed
# that limit outright and get rejected by the embeddings API; (2) even
# comfortably under the limit, one embedding vector for several thousand
# words of unrelated sub-clauses dilutes semantic focus and hurts retrieval
# precision regardless of the hard limit.
MAX_CHUNK_CHARS = 6000

# When a section is too long and gets split (see _split_oversized), each new
# piece is seeded with this many trailing characters from the previous
# piece -- a cross-reference or a clause that continues right at the old cut
# point stays visible in both pieces instead of only whichever side it fell
# on. ~500 chars is roughly 1-2 sentences of legal prose: enough to restore
# that context without duplicating so much text that embedding cost or
# retrieval noise grows meaningfully.
OVERLAP_CHARS = 500


class LawChunk(BaseModel):
    """One numbered provision (Act section or Rule), or one part of it if
    the whole provision was too long for a single retrieval chunk (see
    MAX_CHUNK_CHARS) -- self-contained enough to cite either way:
    everything needed to point a reader at the exact source passage is on
    the object itself, not recoverable only by re-running the chunker."""

    model_config = ConfigDict(frozen=True)

    source_document: str
    chapter: str | None
    section_number: str
    section_title: str
    text: str
    # None if the section fit in one chunk; 1-indexed if it had to be split.
    # A citation is still correct either way -- "Section 2 of the CGST Act"
    # doesn't change meaning because the definitions were split for
    # embedding purposes -- so this exists for retrieval bookkeeping
    # (distinct point IDs in Qdrant), not because it belongs in a citation.
    part: int | None = None

    @property
    def citation(self) -> str:
        return f"{self.source_document}, Section {self.section_number} ({self.section_title})"


def chunk_document(text: str, *, source_document: str) -> list[LawChunk]:
    """Split `text` (the full extracted document) into one LawChunk per
    numbered section/rule. `source_document` is a citable label such as
    "CGST Act (as amended up to 31 Aug 2021)" -- supplied by the caller
    since the raw text has no reliable self-describing title line.
    """
    chapters = [(m.start(), m.group(1), m.group(2).strip()) for m in _CHAPTER_RE.finditer(text)]

    def chapter_at(pos: int) -> str | None:
        chapter = None
        for start, number, title in chapters:
            if start > pos:
                break
            chapter = f"Chapter {number}: {title}"
        return chapter

    matches = list(_SECTION_RE.finditer(text))
    chunks: list[LawChunk] = []
    for i, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if not body:
            continue
        title = match.group(2).strip()
        whole_section = LawChunk(
            source_document=source_document,
            chapter=chapter_at(match.start()),
            section_number=match.group(1),
            section_title=title,
            text=_normalize_whitespace(f"{title}. {body}"),
        )
        chunks.extend(_split_oversized(whole_section, MAX_CHUNK_CHARS))
    return chunks


def _split_oversized(
    chunk: LawChunk, max_chars: int, overlap_chars: int | None = None
) -> list[LawChunk]:
    if len(chunk.text) <= max_chars:
        return [chunk]

    # Cap overlap relative to max_chars so a small budget (as in tests, or
    # a pathologically short section) can't make the overlap dominate --
    # or exceed -- the piece itself.
    overlap = min(OVERLAP_CHARS, max_chars // 5) if overlap_chars is None else overlap_chars

    # Pack paragraphs (blank-line-separated in the extracted text) greedily
    # into pieces up to max_chars, preferring to split between sub-clauses
    # rather than mid-sentence. Each new piece is seeded with a trailing
    # slice of the previous one so context survives the cut.
    paragraphs = re.split(r"\n\s*\n", chunk.text)
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            pieces.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{paragraph}" if tail else paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)

    # A single paragraph longer than max_chars on its own (rare) is hard-
    # split as a last resort: an awkward split point is a smaller problem
    # than an embedding call that gets rejected outright. The sliding
    # window here overlaps for the same reason as above.
    final_pieces: list[str] = []
    step = max(1, max_chars - overlap)
    for piece in pieces:
        if len(piece) <= max_chars:
            final_pieces.append(piece)
        else:
            final_pieces.extend(piece[i : i + max_chars] for i in range(0, len(piece), step))

    return [
        chunk.model_copy(update={"text": piece, "part": idx + 1})
        for idx, piece in enumerate(final_pieces)
    ]


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()
