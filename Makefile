.PHONY: verify sync lint format typecheck test audit data data-offline \
        site site-offline pages node-sync htmlvalidate a11y ask-optin node-audit \
        ask-bundle ask-serve publish determinism secret-scan sast workflow-audit verify-ci

# The gate. Every stage CI runs is a target here, and every CI step runs one of
# these targets, so `make verify` green and CI green mean the same thing.
#
# They did not, until 2026-08-28. CI had three jobs; this target covered one of
# them. `secret-scan`, `sast`, and the twice-build determinism check existed
# only in .github/workflows/ci.yml, with no target to run them by, so a tree
# that CI would reject passed `make verify` locally -- while AGENTS.md said
# "`make verify` is the gate, byte-for-byte identical to CI" and the comment
# that used to sit here said the two MUST stay identical. Neither was true.
# `tests/test_ci_parity.py` now checks it instead of asserting it.
#
# See STANDARDS/CODE-QUALITY-STANDARD.md §2 and .github/workflows/ci.yml.
verify: verify-ci secret-scan
	@echo "make verify: every stage CI runs, plus the working-tree secret scan."

# Everything CI runs, and the target CI's verify job calls. `verify` is this
# plus `secret-scan`, so the local gate is a strict superset: `make verify`
# green implies CI green, never the other way round.
#
# `secret-scan` is the one stage that is local-only, and the reason is
# specific rather than a shrug. It needs the `gitleaks` binary, which is not on
# the GitHub runner image, and the honest ways to put it there are a pinned
# download this repository would then have to keep verifying or a container it
# would have to keep pinning -- both of which add supply-chain surface to a
# workflow whose whole point is to have less of it. What that stage adds over
# the `secret-scan` job's gitleaks action is the *working-tree* pass, and in CI
# the working tree is the committed tree: there is no uncommitted file there for
# it to find. The pass earns its keep on a developer's machine, before the
# commit exists, which is where `make verify` runs. So it runs there.
verify-ci: sync lint format typecheck test audit pages determinism sast workflow-audit

sync:
	# `--locked`, not `--frozen`. `--frozen` installs from uv.lock WITHOUT
	# reading pyproject.toml, so it cannot see the two disagree and it exits 0
	# on a drifted lock. `--locked` re-resolves against pyproject.toml and
	# exits 1 when uv.lock no longer matches it, which is the gate this line
	# is here to be.
	#
	# Every stage below invokes its tool through `uv run --locked`, never a bare
	# `uv run`. A bare `uv run` performs an implicit sync: when uv.lock no longer
	# agrees with pyproject.toml it rewrites the tracked lockfile in place and
	# carries on, so the stage would pass against a resolution nobody committed
	# and nobody reviewed -- and, worse, would have repaired the drift that `sync`
	# is here to report. Until 2026-08-29 the individual targets were unguarded
	# and the property held only because `sync` happens to be listed first;
	# `make lint` on its own could rewrite uv.lock and print "All checks passed!".
	# `--locked` makes that case an error instead. Regenerating the lockfile is a
	# deliberate act (`uv lock`) whose result is a reviewable diff.
	uv sync --locked --extra ask

lint:
	uv run --locked ruff check .

format:
	uv run --locked ruff format --check .

typecheck:
	uv run --locked mypy --strict src

test:
	uv run --locked pytest -n auto --cov=src --cov-branch --cov-report=xml --cov-fail-under=95

audit:
	uv run --locked pip-audit

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
# ask pages under build/site/ask/; leave it empty and the build is
# byte-identical to one before ADR 0003. The default is empty because a default
# endpoint would bake one build's service into every build, not for want of one
# to point at: a service has been deployed since 2026-08-22, and this comment
# claimed the opposite until 2026-08-29. `deploy/ask/README.md` has the URL.
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
#
# It is also given a site url, so the canonical, sitemap and social markup that
# only a hosted build carries is markup the gates actually read. The origin is a
# reserved-TLD name, not homeroom.chelseakr.com: a fixture build is not the
# published site, and must not claim the published site's addresses.
site-offline:
	uv run --locked python -m homeroom.site --fixture --directory fixtures/pubschls.sample.txt --enrollment fixtures/cdenroll.sample.txt --absenteeism fixtures/chronicabsenteeism.sample.txt --ask-endpoint https://ask.example.invalid --site-url https://homeroom.example --out build/site-offline --landing

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
# meant to be: `data/raw/` is never in git, no build step anywhere fetches a
# source file, and acquisition is a documented browser step per file
# (PROVENANCE.md). The
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
	uv run python -m homeroom.site --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt --absenteeism data/raw/chronicabsenteeism25.txt --cds $(SCHOOL) --out $(PUBLISH_DIR) --ask-endpoint $(ASK_ENDPOINT) --site-url https://$(SITE_DOMAIN) --landing
	# GitHub Pages reads the custom domain from this file in the published
	# output; without it a deploy silently unsets the domain and the site
	# answers on github.io only.
	echo $(SITE_DOMAIN) > $(PUBLISH_DIR)/CNAME
	@echo "published into $(PUBLISH_DIR)/ for $(SITE_DOMAIN); commit it to deploy"

# ----------------------------------------------------------------------------
# The gates that used to live only in CI.
# ----------------------------------------------------------------------------

# The page build must be a function of its inputs, because `site/` is rendered
# here and committed, and a build that differs run to run makes a diff
# unreviewable.
#
# The hash comparison has a floor under it. `find | xargs shasum` over an empty
# directory writes an empty file, and diffing two empty files succeeds, so
# without the -s test this stage would report determinism having hashed nothing
# at all -- which is what it did in CI before 2026-08-28.
determinism:
	rm -rf build/determinism && mkdir -p build/determinism
	$(MAKE) site-offline
	find build/site-offline -type f | sort | xargs shasum -a 256 > build/determinism/first.txt
	@test -s build/determinism/first.txt || { echo "determinism: hashed zero files; the build produced nothing" >&2; exit 1; }
	$(MAKE) site-offline
	find build/site-offline -type f | sort | xargs shasum -a 256 > build/determinism/second.txt
	diff build/determinism/first.txt build/determinism/second.txt
	@echo "determinism: $$(wc -l < build/determinism/first.txt) files byte-identical across two builds"

# Secrets, in both places one can be.
#
# `gitleaks git` reads history and is blind to the working tree: demonstrated on
# this repo 2026-08-28, an uncommitted file holding a high-entropy GitHub token
# left history mode reporting "68 commits scanned, no leaks found", exit 0. The
# second pass reads the working tree instead, scoped to exactly the files git
# would consider -- tracked plus untracked-and-not-ignored -- which is where an
# uncommitted key actually sits, and which keeps the pass off node_modules/ and
# .venv/ (577 MB and 71 s, versus 1.3 MB and 0.3 s).
#
# Two commands, each with its own exit status, deliberately not a loop: a shell
# `for` loop exits with only its last iteration's status and would swallow a
# finding from the first.
SECRET_SCAN_TREE ?= build/secret-scan-tree
secret-scan:
	gitleaks git . --no-banner --redact
	rm -rf $(SECRET_SCAN_TREE) && mkdir -p $(SECRET_SCAN_TREE)
	git ls-files -co --exclude-standard -z | rsync -a --files-from=- --from0 . $(SECRET_SCAN_TREE)/
	@test "$$(find $(SECRET_SCAN_TREE) -type f | wc -l)" -gt 0 || { echo "secret-scan: copied zero files; nothing was scanned" >&2; exit 1; }
	gitleaks dir $(SECRET_SCAN_TREE) --no-banner --redact

# Static analysis. `.semgrepignore` in the repository root is load-bearing:
# semgrep's built-in ignore list drops tests/ from every scan, which on this
# repo silently reduced a stated scope of 55 tracked Python files to 30.
SEMGREP_VERSION ?= 1.168.0
sast:
	uvx --from semgrep==$(SEMGREP_VERSION) semgrep scan --error --metrics off --config p/python --config p/security-audit .

# The workflows themselves. Three documents -- docs/audits/threat-model.md
# (twice) and docs/ROADMAP.md's metrics ledger -- named zizmor as the control
# holding `uses:` pins and `permissions:` blocks in place. It was not in this
# repository at all until 2026-08-28: a claimed control that ran nowhere. It
# runs here now, pinned like every other tool, so the claim is checkable.
#
# One finding is ignored, in `.github/workflows/pages.yml`, with the reasoning
# written at the line it applies to. Nothing else is suppressed.
ZIZMOR_VERSION ?= 1.16.3
workflow-audit:
	uvx zizmor@$(ZIZMOR_VERSION) --persona=regular --config .github/zizmor.yml .github/workflows/
