"""PDF text extraction for the law corpus.

Uses pypdf (pure Python) rather than shelling out to the `pdftotext`
poppler binary: the reference project's whole design is "runs anywhere pip
can install it," and pdftotext availability isn't guaranteed on a deployment
host, only on this dev machine (see fetch_corpus.py's own note about the
uv-managed Python's cert-store quirk -- external binary dependencies have a
habit of working on one machine and not another).
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

# Pure noise lines pypdf's page-by-page extraction introduces that carry no
# section content: a lone page number, or the Rules PDF's own running
# "Page N of NNN" footer. Left in, these would occasionally land mid-section
# and get chunked as if they were part of a provision's text.
_NOISE_LINE_RE = re.compile(r"^\s*(\d{1,4}|Page \d+ of \d+)\s*$")


def extract_pdf_text(path: str | Path) -> str:
    """Full text of the PDF, one page's text per element, joined with
    newlines, and stripped of page-number-only noise lines. Chapter-heading
    lines are deliberately NOT stripped even though they repeat on every
    page -- chunker.py needs every repetition to track which chapter a
    section falls under as it scans forward through the document.
    """
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [line for line in text.splitlines() if not _NOISE_LINE_RE.match(line)]
        pages.append("\n".join(lines))
    return "\n".join(pages)


def truncate_before_appendix(text: str, marker: str) -> str:
    """Drop everything from the second occurrence of `marker` onward.

    CBIC's consolidated Act PDF lists an appendix heading once in its Table
    of Contents (first occurrence) and again where the appendix actually
    starts (second occurrence). Built for the "REMOVAL OF DIFFICULTY
    ORDERS" appendix specifically: it bundles several independent legal
    orders, each restarting its own section numbering from 1 -- left in,
    they collide with the Act's real Section 1/2/3 in the citation
    namespace (verified: this is exactly what
    tests/rag/test_corpus_integration.py caught). These orders are
    procedural deadline-relief notices, not substantive ITC law, so they're
    dropped rather than re-namespaced -- out of scope for this project's
    citation needs.

    If `marker` appears fewer than twice, the text is returned unchanged
    (nothing to truncate, or the document's shape doesn't match this
    heuristic and it's safer to leave it alone than guess).
    """
    first = text.find(marker)
    if first == -1:
        return text
    second = text.find(marker, first + len(marker))
    if second == -1:
        return text
    return text[:second]
