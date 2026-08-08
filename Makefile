.PHONY: verify sync lint format typecheck test audit data data-offline

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

# Build artifacts from locally acquired files (data/raw/ is never in git or CI).
# Add `--assignments data/raw/<the D5 file>` once D5 is acquired (PROVENANCE.md).
data:
	uv run python -m homeroom.artifacts --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --out data/out

# Same pipeline over committed fixtures: runs anywhere, output flagged is_fixture.
data-offline:
	uv run python -m homeroom.artifacts --fixture --directory fixtures/pubschls.sample.txt --enrollment fixtures/cdenroll.sample.txt --assignments fixtures/tamo.sample.txt --out data/out
