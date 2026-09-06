#!/usr/bin/env python3
"""Extract + chunk the downloaded CGST Act/Rules PDFs into
data/corpus/chunks.json -- a stable intermediate artifact so the (future)
embedding step doesn't need to re-run PDF extraction and regex chunking on
every run, and so chunk quality can be inspected/reviewed independently of
whatever comes after it in the pipeline.

Run scripts/fetch_corpus.py first if data/corpus/raw/ is empty.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gstrecon.rag.corpus.chunker import chunk_document
from gstrecon.rag.corpus.extract import extract_pdf_text, truncate_before_appendix

# (filename in data/corpus/raw/, citable source label)
DOCUMENTS = [
    ("cgst_act.pdf", "CGST Act, 2017 (as amended up to 31 Aug 2021, per CBIC's own consolidation)"),
    (
        "cgst_rules_part_a.pdf",
        "CGST Rules, 2017, Part A (as amended up to 1 Jun 2021, per CBIC's own consolidation)",
    ),
]

# The Act PDF bundles the "Removal of Difficulty Orders" appendix after the
# main chapters -- see truncate_before_appendix's docstring for why it's
# dropped rather than kept in the citation namespace.
APPENDIX_MARKERS = {"cgst_act.pdf": "REMOVAL OF DIFFICULTY ORDERS"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/corpus/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/corpus/chunks.json"))
    args = parser.parse_args()

    all_chunks: list[dict[str, object]] = []
    for filename, label in DOCUMENTS:
        pdf_path = args.raw_dir / filename
        if not pdf_path.exists():
            raise SystemExit(f"{pdf_path} not found -- run scripts/fetch_corpus.py first.")
        text = extract_pdf_text(pdf_path)
        if marker := APPENDIX_MARKERS.get(filename):
            text = truncate_before_appendix(text, marker)
        chunks = chunk_document(text, source_document=label)
        print(f"{filename}: {len(chunks)} sections/rules extracted")
        all_chunks.extend(chunk.model_dump() for chunk in chunks)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(all_chunks, indent=2))
    print(f"Wrote {len(all_chunks)} chunks to {args.out}")


if __name__ == "__main__":
    main()
