.PHONY: verify sync lint format typecheck test audit data data-offline \
        site site-offline pages node-sync htmlvalidate a11y ask-optin node-audit \
        ask-bundle ask-serve publish

# CI / `make verify` body — the two MUST stay byte-for-byte identical.
# See STANDARDS/CODE-QUALITY-STANDARD.md §2 and .github/workflows/ci.yml.
verify: sync lint format typecheck test audit pages

sync:
	# `--locked`, not `--frozen`. `--frozen` installs from uv.lock WITHOUT
	# reading pyproject.toml, so it cannot see the two disagree and it exits 0
	# on a drifted lock. `--locked` re-resolves against pyproject.toml and
	# exits 1 when uv.lock no longer matches it, which is the gate this line
	# is here to be.
	uv sync --locked --extra ask

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
# D3 (chronic absenteeism, M3) is wired in by default. Add
# `--assignments data/raw/<the D5 file>` to also carry teacher assignment
# outcomes into the artifact -- D5 is acquired and schema-verified (PROVENANCE.md)
# but publishing it is a separate, not-yet-made decision, so it stays off here.
data:
	uv run python -m homeroom.artifacts --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --absenteeism data/raw/chronicabsenteeism25.txt --out data/out

# Same pipeline over committed fixtures: runs anywhere, output flagged is_fixture.
data-offline:
	uv run python -m homeroom.artifacts --fixture --directory fixtures/pubschls.sample.txt --enrollment fixtures/cdenroll.sample.txt --assignments fixtures/tamo.sample.txt --absenteeism fixtures/chronicabsenteeism.sample.txt --out data/out

# The school Homeroom renders from acquired data (ROADMAP M4: one real school,
# both languages). Override to render another, or drop --cds to render them all:
#   make site SCHOOL=01611190130229
# Birch Lane Elementary in Davis Joint Unified, chosen because it is an ordinary
# elementary school with nothing unusual about its data, which is the case a
# family page has to get right first.
SCHOOL ?= 57726786056246

# The ask layer (ADR 0003) is opt-in at build time too. Set ASK_ENDPOINT to the
# URL of a running ask service to add one link per school page and write the
# ask pages under build/site/ask/; leave it empty (the default, because nothing
# is deployed) and the build is byte-identical to one before ADR 0003.
ASK_ENDPOINT ?=

site:
	uv run python -m homeroom.site --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --absenteeism data/raw/chronicabsenteeism25.txt --cds $(SCHOOL) --out build/site $(if $(ASK_ENDPOINT),--ask-endpoint $(ASK_ENDPOINT),) --landing

# The evidence bundle the ask service reads: one small file per school, from
# the same acquired files and the same assembly code as the pages.
ask-bundle:
	uv run python -m homeroom.ask.evidence --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --absenteeism data/raw/chronicabsenteeism25.txt --out data/out/ask

# Serve the ask service locally. Needs HOMEROOM_ASK_PROVIDER (and, for bedrock,
# HOMEROOM_ASK_MODEL and AWS_REGION) in the environment; without a provider it
# answers "unavailable" and the page stands.
ask-serve:
	HOMEROOM_ASK_BUNDLE=data/out/ask uv run --extra ask --extra ask-bedrock python -m homeroom.ask.http

# The same renderer over committed fixtures: every school, both languages, every
# rendering case (published, genuine zero, withheld, nothing published), no
# acquired file, no network. This is what the gates below read. The fixture
# build is given a placeholder ask endpoint (an .invalid name, which can never
# resolve) so the ask pages exist to be gated; tools/ask-optin.mjs proves they
# request nothing until a question is submitted.
site-offline:
	uv run python -m homeroom.site --fixture --directory fixtures/pubschls.sample.txt --enrollment fixtures/cdenroll.sample.txt --absenteeism fixtures/chronicabsenteeism.sample.txt --ask-endpoint https://ask.example.invalid --out build/site-offline --landing

# The accessibility gate the README's standards table promises from the first
# school page. Builds the pages from fixtures, then checks the markup two ways:
# html-validate for HTML conformance and the markup-level accessibility rules, and
# axe-core in a headless DOM for the WCAG 2.0/2.1/2.2 A and AA rule sets, on every
# page in both languages. Structure, EN/ES parity, and colour contrast are checked
# again in `test`, so `make verify` still has a floor if the node toolchain is
# unavailable. What none of this can do is look at the pages; README.md names what
# still needs a person.
pages: site-offline node-sync htmlvalidate a11y ask-optin node-audit

node-sync:
	npm ci

htmlvalidate:
	npx html-validate "build/site-offline/**/*.html"

a11y:
	node tools/a11y.mjs build/site-offline
	node tools/a11y.mjs build/site-offline/ask

# The ask page is the one page that carries a script. This loads each one in a
# DOM with every network path stubbed and asserts zero requests on load and
# exactly one POST on submit, rendered as text only.
ask-optin:
	node tools/ask-optin.mjs build/site-offline

node-audit:
	npm audit --audit-level=high

# What is served at https://homeroom.chelseakr.com.
#
# The site is rendered here, on a machine that holds the acquired CDE files,
# and the rendered pages are committed. It cannot be built in CI and it is not
# meant to be: `data/raw/` is never in git, CI never touches the network, and
# acquisition is a documented browser step per file (PROVENANCE.md). The
# workflow in .github/workflows/pages.yml publishes this directory and builds
# nothing. So the bytes in `site/` are the bytes served, they are reviewable in
# a diff before they are published, and `tests/test_published_site.py` gates
# them in CI without needing a single acquired file.
#
# Re-publishing is this target plus a commit. ASK_ENDPOINT must be the deployed
# stack's FunctionUrl output; without it the pages carry no ask link at all,
# which is the correct output for a site whose ask service is not running.
PUBLISH_DIR ?= site
SITE_DOMAIN ?= homeroom.chelseakr.com

publish:
	@test -n "$(ASK_ENDPOINT)" || { echo "ASK_ENDPOINT is required: the deployed stack's FunctionUrl output" >&2; exit 1; }
	rm -rf $(PUBLISH_DIR)
	uv run python -m homeroom.site --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --absenteeism data/raw/chronicabsenteeism25.txt --cds $(SCHOOL) --out $(PUBLISH_DIR) --ask-endpoint $(ASK_ENDPOINT) --landing
	# GitHub Pages reads the custom domain from this file in the published
	# output; without it a deploy silently unsets the domain and the site
	# answers on github.io only.
	echo $(SITE_DOMAIN) > $(PUBLISH_DIR)/CNAME
	@echo "published into $(PUBLISH_DIR)/ for $(SITE_DOMAIN); commit it to deploy"
