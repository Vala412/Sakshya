#!/usr/bin/env python3
"""Download the CGST Act and CGST Rules PDFs from CBIC's own site into
data/corpus/raw/, so the corpus this project cites is reproducible from a
documented source rather than a one-off manual download.

Source notes (read before trusting a citation built from this corpus):
- GSTN/CBIC has never published a single, always-current consolidated PDF
  at a stable URL. The direct link from cbic-gst.gov.in/gst-acts.html
  ("CGST-bill-e.html") 404s; these URLs were found via web search of
  cbic-gst.gov.in's own /pdf/ directory instead.
- The Act PDF is CBIC's own "as amended up to" consolidation dated
  31 August 2021 -- the most recent one locatable at time of writing. It is
  NOT guaranteed current: GST law has been amended since (Finance Acts
  2022-2025 etc.) and this project has not cross-checked for gaps.
- Only CGST Rules "Part A" (the numbered rules) is fetched, not "Part B"
  (FORMS) -- forms are procedural templates, not citable legal provisions,
  and are out of scope for an explanation layer that cites sections/rules.
- Both PDFs carry CBIC's own disclaimer that they have "no legal binding or
  force" and are prepared "for convenience" only. That disclaimer belongs
  in any citation surfaced to a user -- see rag/corpus/chunker.py.
"""

from __future__ import annotations

import argparse
import ssl
import urllib.request
from pathlib import Path

import certifi

SOURCES = {
    "cgst_act.pdf": "https://cbic-gst.gov.in/pdf/CGST-Act-Updated-31082021.pdf",
    "cgst_rules_part_a.pdf": "https://cbic-gst.gov.in/pdf/01062021-CGST-Rules-2017-Part-A-Rules.pdf",
}


def fetch(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    request_headers = {"User-Agent": "Mozilla/5.0 (compatible; gstrecon-corpus-fetch/0.1)"}
    # uv-managed standalone Python builds don't reliably inherit the OS
    # certificate store on macOS, so urlopen's default SSL context can fail
    # cert verification even though curl (which does use the OS store)
    # succeeds against the same URL. Pointing at certifi's bundle explicitly
    # sidesteps that rather than disabling verification.
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    for filename, url in SOURCES.items():
        dest = out_dir / filename
        print(f"Fetching {url} -> {dest}")
        request = urllib.request.Request(url, headers=request_headers)
        with urllib.request.urlopen(request, context=ssl_context) as response, dest.open("wb") as f:
            f.write(response.read())
        print(f"  {dest.stat().st_size:,} bytes")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("data/corpus/raw"))
    args = parser.parse_args()
    fetch(args.out_dir)


if __name__ == "__main__":
    main()
