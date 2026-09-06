.PHONY: all sync generate reconcile evaluate test lint typecheck clean

SYNTHETIC_DIR := data/synthetic

all: generate reconcile evaluate test

sync:
	uv sync --extra dev

generate: sync
	uv run python scripts/generate_synthetic.py --out-dir $(SYNTHETIC_DIR)

reconcile: generate
	uv run gstrecon $(SYNTHETIC_DIR)/books.csv $(SYNTHETIC_DIR)/gstr2b.json -o $(SYNTHETIC_DIR)/working_paper.xlsx

evaluate: generate
	uv run python scripts/evaluate.py --data-dir $(SYNTHETIC_DIR)

test: sync
	uv run pytest

lint: sync
	uv run ruff check src tests scripts

typecheck: sync
	uv run mypy src scripts

clean:
	rm -rf $(SYNTHETIC_DIR) .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
