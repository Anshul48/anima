.PHONY: install sync lint format typecheck test coverage mutmut all clean

install:
	uv sync --all-groups

sync:
	uv sync --frozen --all-groups

lint:
	uv run ruff check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck:
	uv run mypy src tests

test:
	uv run pytest -v

coverage:
	uv run pytest --cov=stc --cov-report=term-missing --cov-report=html

mutmut:
	uv run mutmut run

all: lint typecheck test
	@echo "[+] All quality gates passed successfully."

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
