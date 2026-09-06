# gst-recon

A books-vs-GSTR-2B reconciliation engine that produces an audit-defensible
working paper, not just a match rate.

See `docs/` (added as each phase lands) for the design rationale. Status and
phase breakdown below will grow as the project does.

## Setup

```bash
uv sync --extra dev            # core engine + test tooling
uv sync --extra dev --extra rag  # + Phase 3 RAG/explanation layer
```

## Run

```bash
make all      # generate synthetic data -> reconcile -> evaluate -> test
```
