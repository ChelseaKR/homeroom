.PHONY: test lint verify
test:
	uv run python -m pytest -q
lint:
	uv run ruff check src tests
verify: lint test
