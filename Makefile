.PHONY: verify sync lint format typecheck test audit data data-offline \
        site site-offline pages node-sync htmlvalidate a11y node-audit

# CI / `make verify` body — the two MUST stay byte-for-byte identical.
# See STANDARDS/CODE-QUALITY-STANDARD.md §2 and .github/workflows/ci.yml.
verify: sync lint format typecheck test audit pages

sync:
	uv sync --locked

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

# The school Homeroom renders from acquired data (ROADMAP M4: one real school,
# both languages). Override to render another, or drop --cds to render them all:
#   make site SCHOOL=01611190130229
# Birch Lane Elementary in Davis Joint Unified, chosen because it is an ordinary
# elementary school with nothing unusual about its data, which is the case a
# family page has to get right first.
SCHOOL ?= 57726786056246

site:
	uv run python -m homeroom.site --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --cds $(SCHOOL) --out build/site

# The same renderer over committed fixtures: every school, both languages, every
# rendering case (published, genuine zero, withheld, nothing published), no
# acquired file, no network. This is what the gates below read.
site-offline:
	uv run python -m homeroom.site --fixture --directory fixtures/pubschls.sample.txt --enrollment fixtures/cdenroll.sample.txt --out build/site-offline

# The accessibility gate the README's standards table promises from the first
# school page. Builds the pages from fixtures, then checks the markup two ways:
# html-validate for HTML conformance and the markup-level accessibility rules, and
# axe-core in a headless DOM for the WCAG 2.0/2.1/2.2 A and AA rule sets, on every
# page in both languages. Structure, EN/ES parity, and colour contrast are checked
# again in `test`, so `make verify` still has a floor if the node toolchain is
# unavailable. What none of this can do is look at the pages; README.md names what
# still needs a person.
pages: site-offline node-sync htmlvalidate a11y node-audit

node-sync:
	npm ci

htmlvalidate:
	npx html-validate "build/site-offline/*.html"

a11y:
	node tools/a11y.mjs build/site-offline

node-audit:
	npm audit --audit-level=high
