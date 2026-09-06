# gst-recon

A books-vs-GSTR-2B reconciliation engine that produces an **audit-defensible
working paper**, not just a match rate.

Indian GST lets a business deduct tax paid on purchases (Input Tax Credit,
ITC) from tax collected on sales. GSTR-2B is the monthly statement the GST
portal auto-generates from what suppliers actually filed — it states what ITC
a business *may* claim. The books (usually Tally) record what was *actually*
claimed. The two disagree constantly: suppliers file late, invoice numbers
get keyed differently across systems, GSTINs get mistyped, credit notes
reverse credit already taken. A chartered accountant reviewing this needs to
*prove* how every claimed rupee was reached — that proof is the deliverable
here, not a percentage.

## What makes this different from a fuzzy-match script

1. **The matcher is built on GSTN's own taxonomy**, not an invented one.
   `matching.py` implements the exact 6-category, 7-parameter classification
   scheme documented in GSTN's Matching Offline Tool manual (Exact / Partial
   / Probable / Unmatched / orphan-on-either-side), including the detail
   that tolerance applies per tax head (IGST/CGST/SGST/CESS individually),
   never on the summed total — a distinction the manual is explicit about
   and that most naive implementations get wrong.
2. **The ITC bridge ties to nil by construction, not by assertion.** Every
   document contributes its `signed_tax` to exactly one bridge line; the
   closing variance is the *remainder* of that decomposition, not a
   separately-computed number that happens to match. A randomized property
   test (`test_bridge_ties_to_nil_property`) checks this across dozens of
   generated scenarios specifically to keep that guarantee honest.
3. **Reproducibility is a first-class requirement**, not a nice-to-have: the
   working paper's Reproducibility sheet SHA-256-hashes both input files,
   and the reconciliation's output order is deterministic across process
   runs (verified against a real bug — Python's per-process string-hash
   randomization was silently reordering results; see `matching.py`'s
   `reconcile()`).
4. **Every design decision is defended in place**, in the code, against the
   specific failure it prevents — not in a separate doc that drifts out of
   sync. Search for "Regression:" in the test suite for the bugs this
   project's own eval harness caught during development.

## Architecture

```
Ingestion (Tally CSV + GSTR-2B JSON)
        |
        v
Deterministic tiered matcher  (matching.py — GSTN's own 6-category taxonomy)
        |
        v
Exception classifier          (exceptions.py — 12 reason codes, EX-01..EX-12)
        |
        v
Working paper (.xlsx)         (report.py — ITC bridge + register + repro sheet)
```

Phase 3 (`src/gstrecon/rag/`) adds retrieval over the actual CGST Act and
Rules text so exceptions can eventually carry a cited legal explanation:

```
CGST Act/Rules PDFs (CBIC)
        |
        v
Section-aware chunker         (rag/corpus/chunker.py — citation-grade provenance)
        |
        v
OpenAI embeddings -> Qdrant    (rag/retrieval/ — similarity-floor guardrail)
```

The matching/classification engine is **fully deterministic and has zero
dependency on an LLM or vector store** — Phase 3 only ever *explains* a
finding the deterministic engine already made; it never participates in
deciding what the finding is.

## Reason codes

| Code | Meaning | Severity |
|---|---|---|
| EX-01 | In books, not in GSTR-2B | High |
| EX-02 | In GSTR-2B, not in books | Low |
| EX-03 | Taxable value mismatch | Medium |
| EX-04 | Tax amount mismatch | High |
| EX-05 | Tax head mismatch (total agrees, split doesn't) | Medium |
| EX-06 | GSTIN invalid or mismatched | High |
| EX-07 | Invoice number variance | Low |
| EX-08 | Period timing difference | Low |
| EX-09 | ITC flagged unavailable in 2B but claimed in books | High |
| EX-10 | Duplicate booking | High |
| EX-11 | Credit note in 2B with no reversal in books | High |
| EX-12 | Credit note booked but not yet reflected in 2B | Low |

## Setup

```bash
uv sync --extra dev              # core engine + test tooling
uv sync --extra dev --extra rag  # + Phase 3 RAG/retrieval layer
```

Phase 3 also needs Qdrant and an OpenAI key:

```bash
cp .env.example .env             # fill in OPENAI_API_KEY
docker compose up -d qdrant
```

## Run

```bash
make all                         # generate synthetic data -> reconcile -> evaluate -> test
gstrecon books.csv gstr2b.json -o working_paper.xlsx   # reconcile real files

make fetch-corpus                # download CGST Act + Rules from CBIC
make ingest-corpus                # extract + chunk into data/corpus/chunks.json
make embed-corpus                 # embed into Qdrant
make test-retrieval               # manual retrieval smoke test (real API calls)
```

## Testing

```bash
make test        # full suite (offline, free)
make test-live    # + tests that make real OpenAI/Qdrant calls (small real cost)
```

250 labelled synthetic cases (`scripts/generate_synthetic.py`) exercise all
12 reason codes with exactly one injected defect per case; the eval harness
(`scripts/evaluate.py`) reports per-code precision/recall. **Read that score
honestly**: the generator and the classifier share the same assumptions
about what each code means, so a perfect score is a regression gate — proof
the engine still agrees with itself — not evidence of accuracy against a
real GSTR-2B export, which this project has never had access to.

## Known limitations

- GSTN has never published an official GSTR-2B JSON schema; field names in
  `ingest.py` are triangulated from adjacent GST return formats, not
  confirmed against a real export.
- Amendments (B2BA/CDNRA) aren't handled — an amended invoice currently
  reads as a second, unmatched document.
- The CGST Act corpus is CBIC's own consolidation "as amended up to 31 Aug
  2021" — the most recent stable-URL version locatable; not cross-checked
  against amendments since.
- Candidate matching is O(n×m) per document-type bucket (see `matching.py`)
  — fine at realistic single-filer volume, not optimized for tens of
  thousands of documents in one bucket.
- No RCM, ISD, multi-period carry-forward, or unregistered-supplier
  handling.
