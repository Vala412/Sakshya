#!/usr/bin/env python3
"""Embed data/corpus/chunks.json and upsert into Qdrant.

Requires: Qdrant reachable at RagSettings.qdrant_url (see docker-compose.yml
-- `docker compose up -d qdrant`), and OPENAI_API_KEY set (via .env or the
environment). Run scripts/ingest_corpus.py first to produce chunks.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from gstrecon.rag.corpus.chunker import LawChunk
from gstrecon.rag.retrieval.vector_store import delete_collection, upsert_chunks


async def main_async(chunks_path: Path, *, force: bool) -> None:
    if force:
        print("Dropping existing collection (--force)...")
        await delete_collection()
    raw = json.loads(chunks_path.read_text())
    chunks = [LawChunk(**item) for item in raw]
    print(f"Embedding and upserting {len(chunks)} chunks...")
    count = await upsert_chunks(chunks)
    print(f"Wrote {count} points to Qdrant.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=Path("data/corpus/chunks.json"))
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Drop the existing Qdrant collection first instead of upserting onto it. "
            "upsert_chunks never removes stale points (ones whose section/part no "
            "longer exists after a re-chunk); this is how to actually clear those "
            "rather than accumulate them indefinitely."
        ),
    )
    args = parser.parse_args()
    if not args.chunks.exists():
        raise SystemExit(f"{args.chunks} not found -- run scripts/ingest_corpus.py first.")
    asyncio.run(main_async(args.chunks, force=args.force))


if __name__ == "__main__":
    main()
