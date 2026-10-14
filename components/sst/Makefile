.PHONY: install lint format format-check typecheck test test-cov gate clean help

help:
	@echo "SST Development Automation Commands:"
	@echo "  make install       - Install all project dependencies using uv"
	@echo "  make lint          - Run ruff linter checks"
	@echo "  make format        - Format codebase with ruff"
	@echo "  make format-check  - Verify code formatting with ruff"
	@echo "  make typecheck     - Run strict mypy type analysis"
	@echo "  make test          - Run full pytest test suite"
	@echo "  make test-cov      - Run pytest with code coverage"
	@echo "  make gate          - Run all verification quality gates"
	@echo "  make clean         - Remove build artifacts, pycache, and temp databases"

install:
	uv sync --all-extras

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy --strict src/ tests/

test:
	uv run pytest -v

test-cov:
	uv run pytest -v --cov=sst

gate: lint format-check typecheck test
	@echo "All SST quality verification gates PASSED successfully."

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[cod]" -delete
