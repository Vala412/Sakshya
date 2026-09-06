.PHONY: all sync generate reconcile evaluate test test-live lint typecheck clean \
	fetch-corpus ingest-corpus embed-corpus test-retrieval explain-synthetic

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

# Makes real OpenAI/Qdrant calls -- small real cost, needs Qdrant running
# and OPENAI_API_KEY set. See tests/rag/test_vector_store.py.
test-live: sync
	uv run pytest -m live

# Corpus pipeline: download the CGST Act/Rules -> extract+chunk with
# citation-grade provenance -> embed into Qdrant.
fetch-corpus: sync
	uv run python scripts/fetch_corpus.py

ingest-corpus: sync
	uv run python scripts/ingest_corpus.py

embed-corpus: sync
	uv run python scripts/embed_corpus.py

# Manual smoke test, not part of the pytest suite -- see its docstring.
test-retrieval: sync
	uv run python scripts/test_retrieval.py

# Reconcile the synthetic dataset AND generate cited AI explanations for
# every HIGH/MEDIUM finding -- makes real OpenAI calls (small real cost).
explain-synthetic: generate
	uv run python scripts/explain_findings.py $(SYNTHETIC_DIR)/books.csv $(SYNTHETIC_DIR)/gstr2b.json -o $(SYNTHETIC_DIR)/working_paper.xlsx

lint: sync
	uv run ruff check src tests scripts

typecheck: sync
	uv run mypy src scripts

clean:
	rm -rf $(SYNTHETIC_DIR) .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
