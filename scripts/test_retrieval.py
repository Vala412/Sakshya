#!/usr/bin/env python3
"""Manual retrieval smoke-test harness -- not part of the pytest suite (it
makes real OpenAI + Qdrant calls, i.e. costs money and needs both services
up). Run this by hand after `python scripts/embed_corpus.py` to eyeball
retrieval quality against real queries before wiring the explanation/chat
layer on top of it, per the project roadmap ("test retrieval standalone
before wiring anything").

Queries below are phrased the way an exception in the working paper would
actually need to be explained (EX-09 -> Section 17(5), EX-11 -> Section 34),
not as generic legal questions -- retrieval quality against realistic
queries is what matters here, not retrieval quality in the abstract.
"""

from __future__ import annotations

import asyncio

from gstrecon.rag.retrieval.vector_store import similarity_search

QUERIES = [
    "input tax credit blocked for motor vehicles",
    "conditions for claiming input tax credit on a tax invoice",
    "credit note issued by supplier reducing tax liability",
    "reversal of input tax credit when payment not made to supplier",
    "eligibility to take credit on capital goods",
    "time limit for claiming input tax credit for a financial year",
]


async def main() -> None:
    for query in QUERIES:
        print("=" * 90)
        print(f"QUERY: {query!r}")
        print("-" * 90)
        # score_threshold=0.0 here (bypassing the configured floor) so this
        # harness shows every candidate's real score -- that's the whole
        # point of running it: deciding what the floor *should* be.
        results = await similarity_search(query, top_k=5, score_threshold=0.0)
        if not results:
            print("  (no results at all -- collection empty or query embedding failed)")
        for r in results:
            print(f"  [{r.score:.3f}] {r.chunk.citation}")
            print(f"          {r.chunk.text[:160]}...")


if __name__ == "__main__":
    asyncio.run(main())
