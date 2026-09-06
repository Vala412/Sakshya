.PHONY: all sync generate reconcile evaluate test lint typecheck clean \
	fetch-corpus ingest-corpus

SYNTHETIC_DIR := data/synthetic

all: generate reconcile evaluate test

sync:
	# ingest_corpus.py needs pypdf, which lives in the optional `rag` extra
	# -- `uv sync --extra dev` alone *reconciles* the venv down to just the
	# dev extra rather than leaving rag packages alone, so it would silently
	# uninstall pypdf if a previous `--extra rag` sync had installed it.
	uv sync --extra dev --extra rag

generate: sync
	uv run python scripts/generate_synthetic.py --out-dir $(SYNTHETIC_DIR)

reconcile: generate
	uv run gstrecon $(SYNTHETIC_DIR)/books.csv $(SYNTHETIC_DIR)/gstr2b.json -o $(SYNTHETIC_DIR)/working_paper.xlsx

evaluate: generate
	uv run python scripts/evaluate.py --data-dir $(SYNTHETIC_DIR)

test: sync
	uv run pytest

# Corpus pipeline: download the CGST Act/Rules -> extract+chunk with
# citation-grade provenance.
fetch-corpus: sync
	uv run python scripts/fetch_corpus.py

ingest-corpus: sync
	uv run python scripts/ingest_corpus.py

lint: sync
	uv run ruff check src tests scripts

typecheck: sync
	uv run mypy src scripts

clean:
	rm -rf $(SYNTHETIC_DIR) .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
