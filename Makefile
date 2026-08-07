.PHONY: verify sync lint format typecheck test audit

# CI / `make verify` body — the two MUST stay byte-for-byte identical.
# See STANDARDS/CODE-QUALITY-STANDARD.md §2 and .github/workflows/ci.yml.
verify: sync lint format typecheck test audit

sync:
	uv sync --frozen

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

typecheck:
	uv run mypy --strict src

test:
	uv run pytest -n auto --cov=src --cov-branch --cov-report=xml --cov-fail-under=85

audit:
	uv run pip-audit
