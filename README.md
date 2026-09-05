# Homeroom

**California's public school data, readable by the families it describes.**

> Working title. Not affiliated with the State of California or any school district.

**Live at <https://homeroom.chelseakr.com>** — one school so far, in English and
Spanish. What is published there, and why it is one school rather than every
school the pipeline profiles, is under [Status](#status).

## Quickstart

No acquired data and no network. `site-offline` renders every fixture school in
both languages, which is the same renderer and the same code path the published
site is built with — only the inputs differ.

```sh
uv sync --locked --extra ask                    # or: make sync
make site-offline                               # 3 fixture schools, English and Spanish
python3 -m http.server -d build/site-offline    # then open http://localhost:8000
```

The pages carry a fixture banner in both languages, because a page built from
sample rows must never be mistakable for one about a real school.

| Command | What it does |
|---|---|
| `make verify` | The single local gate; run it before opening a PR. Needs Node 22 for the markup and accessibility stages, which run `npm ci`. See CONTRIBUTING.md. |
| `make site-offline` | The school pages, from committed fixtures. |
| `make data-offline` | The same pipeline's JSON artifacts (`data/out/`), from the same fixtures. |
| `make site` | The pages for a real school. Needs the CDE extracts in `data/raw/`, which are not in git — PROVENANCE.md names each file and how to acquire it. |
| `make publish` | Rebuilds the committed `site/` tree that is served at the live URL. Needs `data/raw/` and `ASK_ENDPOINT`. |

## The problem

California publishes an enormous amount of data about its public schools: enrollment,
chronic absenteeism, teacher assignments, per-pupil spending, English learner progress.
Almost none of it is legible to a parent deciding where to enroll a child, or trying to
understand the school their child already attends. The files live in download pages built
for researchers, the dashboard flattens everything into color bands, and commercial school
raters compress it all into a single score with well-documented equity harms.

Homeroom joins the state's own data into plain-language, bilingual school pages, and
holds one rule above all others:

**It refuses to rank schools.** No composite score, no letter grade, no ordering of one
school above another. Each measure is shown on its own terms, beside the statewide and
district context needed to read it, with its suppression and coverage stated. A number
that cannot be shown honestly is not shown at all.

## Honesty rules (ported from sibling projects, enforced in code)

- A suppressed or masked measure (CDE masks small cells to protect students) renders as
  *not published*, never as zero, never interpolated.
- "Not reported" and "reported as zero" are different facts and stay visually different.
- District and statewide context comes from the state's own aggregate rows, never from
  adding schools together. A sum over a column containing masked cells is wrong, and a
  sum that skips them is wrong and looks clean, because it drops exactly the students
  the mask protects.
- Every figure traces to a named public file with an access date (see PROVENANCE.md).
- Coverage is a first-class output: how many schools publish each measure is itself
  published, so absence reads as absence rather than as a clean dataset.
- English and Spanish from the first release. No account, no tracking.

## Data reality

Source files are downloaded from CDE's public data pages the way CDE intends: in a
browser, by a person. The pipeline treats them as **locally acquired inputs**, with each
file's origin, date, and name documented in PROVENANCE.md; drop them in `data/raw/` and
`make data` validates and builds from there. CI never fetches a source file, and a
small committed fixture exercises every rendering case. That is narrower than the
"CI never touches the network" this line carried until 2026-08-29: `make verify-ci`
reaches a package index or an advisory database at `uv sync`, `npm ci`, `pip-audit`,
`npm audit`, and the pinned `uvx` runs of semgrep and zizmor. What never crosses the
network is the data. This mirrors the Afterward project's
answer to the same provenance problem with federal endpoints.

## Status

The school-directory parser (the spine every other dataset joins against, via CDS
codes) is built, tested against a fixture, and verified against the live file
(acquired 2026-08-07): 18,396 directory rows parsed with no drift errors, yielding
10,534 active schools across 1,059 districts and all 58 counties, 1,238 of them
charters. Those 1,059 districts carry only 1,048 distinct names: ten names cover
two districts each, except "Jefferson Elementary", which covers three. Counting
districts by name loses eleven of them, which is why the CDS code is the only key
this project joins on. The 2025-26 Census Day enrollment file (269,090 rows, acquired the same
day) parses end to end and joins that spine, and `make data` now assembles one
profile per active school, with total, grade-span, and subgroup enrollment as
three-status measures, and emits deterministic JSON artifacts: 10,534 profiles,
byte-identical across re-runs, coverage published beside the data (9,860 school
totals joined, the 698-plus-674 join gap counted in both directions, masks kept
as nulls).

The first bilingual school pages are built (M4). One page per school per
language, rendered from those profiles: identity, total enrollment, TK-12 grade
spans, and 25 subgroup figures, each cell in exactly one of four states, with
coverage in the next three columns. Birch Lane Elementary in Davis Joint Unified
renders from the acquired files in English and Spanish, publishing 36 of its 40
figures (30 counts and 6 genuine zeros) and stating in words, for the other four,
that the state published nothing.
Every user-visible string exists in both languages: 193 keys per locale, zero
present in one and missing from the other, enforced by test. The pages carry no
script, no external asset, no account, and no tracking.

Chronic absenteeism (D3) is the first measure Homeroom publishes that CDE masks
at real scale, and it is now built end to end (M3). The 2024-25 file (341,490
rows, acquired 2026-08-21) parses, joins the spine, and renders on every school
page: a total rate plus race/ethnicity, gender, and student-group breakdowns, each
beside its district and statewide figure, read from CDE's own `Charter School =
All` and `DASS = All` rows. Across the 10,534 active schools, the total rate is
published for 9,718 of them, withheld for 83, and not published for 733 that the
file never mentions; some subgroups are withheld far more often than that. The
most-withheld is Non-binary (`GX`), withheld at 1,990 of the 2,045 schools that
report it at all, 97.3%; the other 8,489 active schools carry no Non-binary row
for CDE to withhold, so that share describes a much smaller slice of the state
than the next one does. American Indian or Alaska Native (`RI`) is withheld at
9,350 of 9,801, 95.4%, and 9,801 is nearly every active school. Three categories
are withheld for over 94% of the schools that report them at all.
`docs/SUPPRESSION-SHOWCASE.md` carries the table and walks four real rows, one of
each cell state, from the source file to the rendered markup. Grade-span categories
are recognized so the file parses but are not rendered as a subgroup, the same
choice already made for D2's age ranges.

What a cell can say, and how the four states stay apart on the page:

| State | On the page | Never |
|-------|-------------|-------|
| Published figure | the number, as published | rounded, averaged, or derived |
| Published zero | `0`, plus the words *reported as zero* | confused with an empty cell |
| Withheld (CDE's `*`) | the words *withheld to protect privacy*, no digit | shown as `0`, estimated, or recovered from its siblings |
| Nothing published | the words *no figure published*, no digit | shown as `0` or left blank |

Accessibility and translation are gated, not asserted. `make verify` builds the
pages from committed fixtures and runs html-validate and axe-core (WCAG 2.0/2.1/2.2
A and AA, plus best-practice) over every page in both languages, and re-checks
structure, EN/ES key parity, colour contrast in both themes, and that every number
in a data cell is a number the pipeline counted. Re-verified with M3's four new
tables in the fixture build (2026-08-21): zero violations, same six rule sets.
What none of that can do is look at the pages: layout, reflow at small widths,
focus visibility in practice, and a screen-reader walkthrough in each language
need a person, and that walkthrough has not happened yet. M3 deliberately kept
its new tables at the same seven columns as the existing ones rather than adding
more while that gate is open; see `docs/RESPONSIBLE-TECH-AUDITS.md` §E and RR-05
in `docs/audits/residual-risk-register.md`.

Teacher assignment monitoring (D5) has been acquired and its schema verified
against a real file, and is still not published anywhere. CDE publishes these
files from the Commission on Teacher Credentialing's CalSAAS system: by school,
how much teaching FTE sat on a clear credential appropriately matched to the
assignment, and how much sat in one of the other authorization states the state
tracks. The 2023-24 file (234,206,408 bytes, 1,528,796 rows, acquired
2026-08-21) turned out to disagree with the parser's provisional contract in
every particular -- real column names, seven outcomes rather than five, FTE
fractions rather than integer counts, and up to 150 rows per school rather than
one -- and `src/homeroom/assignments.py` was rewritten to match what the file
actually contains (PROVENANCE.md D5 has the full list). The parser, its coverage
output, and its join to the spine are tested against a fixture shaped like that
real file. No D5 number about a real school is published anywhere: `make data`
and `make site` are not given the file by default, `homeroom.site` accepts no
argument for it at all, and PROVENANCE.md says publishing it is a separate,
not-yet-made decision. No school page shows a teacher figure; each page says so
in words, and a test renders a profile that does carry parsed assignment
outcomes to prove none of them reaches the markup. The remaining datasets (D4,
the state dashboard indicators, and D6, per-pupil spending) were surveyed on
2026-09-05: both exist and are readable, D6 at a different address than this
project had recorded, and neither is acquired or publishes anything. D4 turned
out to be nine files rather than one, sharing 22 columns and not a schema, in
which suppression is a blank cell and `0` means "No Color" rather than zero. D6
turned out not to be in the SACS files this repository had pointed at, which are
district-level; the school-level source is CDE's ESSA per-pupil expenditure
workbook, which publishes four components and no total, so the one number a
reader would expect does not exist in the file and could only be computed. Both
therefore wait on a decision rather than a download: whether an ordered
Dashboard band may be shown at all under ADR 0002, and what "per-pupil spending"
is allowed to mean when the state publishes no total. PROVENANCE.md D4 and D6
carry the measurements and docs/ROADMAP.md "M5 source survey" states the
decisions.

**Live at <https://homeroom.chelseakr.com>** since 2026-08-22, by the owner's
decision. Whether these pages belonged on the internet was a separate question
about real schools and real children, and no build made it; a person did.

What is published there is what this repository has actually built and checked:
Birch Lane Elementary in Davis Joint Unified, in English and Spanish, with the
ask layer below wired to a running service. That is one school out of the 10,534
the pipeline profiles. The landing page does not print that ratio; what it says,
in both languages, is that Homeroom is in development, that the schools listed
are the ones published so far, and that more are added as each source is acquired
and checked. This paragraph said "the landing page says so" until 2026-08-29,
which read as a claim that the 10,534 figure is on the page. It is not, and the
page does not imply the state is covered either. Publishing more is `make publish` with more
`--cds` codes; it is a decision about which schools to put in front of families,
not a technical step.

The site is rendered here and committed to `site/`, because it cannot be built
in CI: the acquired CDE files never enter git and nothing in CI fetches them.
The workflow in `.github/workflows/pages.yml` publishes that directory and
builds nothing, so the bytes reviewed in a pull request are the bytes served,
and `tests/test_published_site.py` gates them in `make verify` on a machine with
no acquired file present.

## AI at the edges (ADR 0003)

As of 2026-08-21, by the owner's direction, Homeroom has an optional
question-answering layer so a family can ask, in English or Spanish, what a
school's page is saying: "Is chronic absenteeism a problem here?", "How many
students are English learners?", "What does 'chronic absenteeism' mean and how
is it measured?". The design, recorded in `docs/adr/0003-grounded-ai-at-the-edges.md`,
keeps the founding rule intact:

- **It still refuses to rank.** The service sees one school per request, so it
  cannot compare schools it cannot see; "is this a good school", "give it a
  grade", "which is better" get a fixed, reviewed refusal in both languages
  that the model does not write, and a second guard withholds any sentence the
  model did write that carries better/worse, grade, score, rank, or
  recommendation language. An adversarial evaluation suite targets zero.
- **The published dataset is the only evidence.** Every claim cites a record
  (school CDS, measure, academic year) or a passage from a committed corpus of
  CDE's own definitions, and a verifier checks every number, every withheld
  cell, every comparison direction, and every quote against the data before
  anything is shown. A claim that cannot be verified is withheld and counted.
- **A withheld cell is never a zero**, in prose any more than in a table.
- **The school pages do not change.** They stay static and script-free and make
  no off-origin request. The opt-in is a link to a separate ask page for that
  school, which makes no request until a question is submitted, and a build not
  given a service endpoint renders neither.
- **Everything the model says is labeled** AI-generated, unofficial, not a
  ranking, and not a recommendation. Spanish narration is labeled
  AI-translated and unreviewed.
- **It is deployed, as of 2026-08-22, by the owner's decision.** The
  cost-bounded shape in `deploy/ask/` is applied: one Lambda behind a Function
  URL in `us-west-2`, CORS and a server-side origin check locked to
  `https://homeroom.chelseakr.com`, reserved concurrency 2, a daily cap of 400
  model calls per warm container, six requests per client per minute, and a
  CloudWatch alarm at 400 daily invocations to an SNS topic in the same stack.
  The cap is per container, not a shared ledger (`deploy/ask/template.yaml`
  `DailyCap`), so with reserved concurrency 2 the worst case is two containers
  each spending it; reserved concurrency is the bound that actually holds, and
  RR-09 carries this as an open item. The deployed model
  is Bedrock `global.anthropic.claude-sonnet-4-6` -- the model the recorded
  evaluations name and the only Claude this account can invoke. `make site`
  still renders no ask page and no link until it is given an endpoint, so a
  build without one is byte-identical to a build from before ADR 0003.
  Rollback is in `deploy/ask/README.md`: delete the stack, rebuild the site
  without an endpoint.

Provider: the public `anthropic` SDK, default model `claude-sonnet-5`,
configurable, credentials from the environment only. The evaluation harness
and its five suites (ranking refusal, suppression fidelity, citation grounding,
comparability, question structuring) live in `evals/`, and results are
committed only from a recorded live run that names the model. The harness exits
nonzero when a suite falls short of its target, and CI holds every committed
results file to the same check, so a regression cannot be committed green
(ADR 0004).

Recorded run (2026-08-22, `evals/results/`): 157 cases over real schools from
the acquired files, on Amazon Bedrock `global.anthropic.claude-sonnet-4-6`
(the model this account could invoke; the code default, Sonnet 5, was not
available to it, and the results say which model they are about). Ranking
refusal 62/62, suppression fidelity 24/24, citation grounding 24/24,
comparability 19/19, structuring 28/28. Across the run the verifier showed
511 sentences and withheld 23 before display: 11 quotes that were not
verbatim CDE text, 5 numbers no cited cell publishes, 3 sentences carrying
judgment language, 2 comparisons of the wrong shape, 2 definitions without a
quote. Those 23 are the product working, not the model failing quietly: each
one would otherwise have reached a family. What no suite measures is whether
the Spanish reads well or whether a person, reading a sample of real answers,
finds them honest; both are open (RR-07, RR-08).

## Development disclosure

Built AI-assisted (Claude Code), with every claim, parser, and number verified against
acquired source files and enforced by the test suite. The honesty rules above bind the
tooling as much as the author: nothing ships that the data does not support.

## Standards conformance

Governed by [portfolio-standards](https://github.com/ChelseaKR/portfolio-standards) (private).

| Standard | State |
|----------|-------|
| Responsible-Tech Framework | Applies (see `docs/RESPONSIBLE-TECH-AUDITS.md`) |
| Code Quality | Applies |
| Security & Supply-Chain | Applies. `make verify` runs semgrep over this project's own source, `tests/` included (semgrep's built-in ignore list drops `tests/`; the committed `.semgrepignore` replaces that list and does not), zizmor over the workflows under a `hash-pin` policy, pip-audit, npm audit, and a secret scan covering git history *and* the working tree, because history mode alone is blind to an uncommitted key. `.semgrepignore` excludes vendored, generated and built output, `site/` among it, so the bytes actually served are gated by `tests/test_published_site.py` rather than by semgrep; this row said "the whole tree" until 2026-08-29. Every step in `.github/workflows/ci.yml` is accounted for by `tests/test_ci_parity.py`: each `run:` step calls a `make` target that `make verify` reaches, and each `uses:` step is either a setup or reporting action or a gating action registered against the target that reproduces it locally, which is what covers the `secret-scan` job, whose only step is an action. So the local gate is a strict superset of CI and the two cannot drift; the sentence said "every step ... is a `make` target", which was true only of the `run:` steps. CI runs `make verify-ci`, which is all of it except the working-tree secret pass: that one needs a binary the runner does not carry, and in CI the working tree is the committed tree anyway |
| CI/CD | Applies |
| Observability | Applies (Tier C, library/CLI; declared in `docs/ROADMAP.md`) |
| Accessibility | Applies, in two halves, one of them open. Automated: html-validate and axe-core over every built page in both languages, plus structure, EN/ES parity and contrast checks in `make verify`. **Review, not yet done:** the keyboard-only and screen-reader walkthrough in each language, and the reflow check at 320 CSS pixels on the seven-column tables. A headless DOM cannot decide any of it. Tracked as [issue #6](https://github.com/ChelseaKR/homeroom/issues/6) and RR-05; owner Chelsea Kelly-Reif. The pages are live, so this is open work rather than work waiting on a publication decision |
| Internationalization | Applies (EN/ES is a launch requirement; parity gate wired and merge-blocking as of ROADMAP M4) |
| AI Evaluation | Applies as of ADR 0003 (2026-08-21): a prompt, a retrieval corpus, and a model-version surface now exist in `src/homeroom/ask/`. Five evaluation suites and their harness live in `evals/`; results carry provider, model, prompt version, commit, and date, and a test rejects results without them. See `docs/RESPONSIBLE-TECH-AUDITS.md` AI-EVAL and Governance |
| Documentation | Applies |
| Quality & Metrics | Applies (see `docs/ROADMAP.md` metrics ledger) |
| Performance | Applies: the school pages are pre-rendered static HTML built from locally acquired files, with no client-side script and no network call at build time, and the pipeline is deterministic: re-running `make data` produces byte-identical artifacts. The optional ask service (ADR 0003) is a hosted route as of 2026-08-22; a measured answer takes about 5 s end to end against Bedrock claude-sonnet-4-6, and no latency objective is declared for it yet. The static pages declare none and need none: they are files. No page-weight or build-time budget is asserted in CI yet |
| AI Development Measurement | Applies: this project is built AI-assisted and says so below. The outcome side is the metrics ledger in `docs/ROADMAP.md`, where every gate names its measurement and its AUTO/REVIEW disposition, and every day-one value was measured against a named acquired file rather than estimated. The diagnostic counters the standard names (sessions, tokens, share of generated code, acceptance rate) are not instrumented here, and by the standard's own rule they would be observe-only if they were: they never gate a merge |
| Incident Response | Applies: `SECURITY.md` routes reports through GitHub private vulnerability reporting with a 72-hour acknowledgement target. The static site and the ask service are deployed as of 2026-08-22 and there is still no account; the ask service (ADR 0003) stores no question and keeps no user data, so the incidents this project can actually have are a wrong or mis-sourced figure on a school page and a model sentence that reached a reader unverified. The first is why masked cells are type-enforced to raise on read, why a number on a page that nothing counted fails the build, and why coverage is published beside the data; the second is why every AI claim passes a verifier and the withheld count is shown. A severity ladder and a committed postmortem template are not yet in the repository |
| Data Governance | Applies: `PROVENANCE.md` is the register: every source is a named California Department of Education public file with its acquisition method, access date, and status, and a source that has not been acquired publishes nothing and says so in `coverage.json`. CDE small-cell masking is preserved as null, never zero and never interpolated; the CDS code is the only join key; no third-party or commercial data enters the pipeline. The artifacts are school-level public aggregates, not personal data, and the site has no account and no tracking. Raw source files are never committed and CI never fetches them. The ask service (ADR 0003) sends a reader's question and one school's published records to the model provider for the duration of the request and stores neither; the subprocessor record is in `docs/RESPONSIBLE-TECH-AUDITS.md` under Privacy, owner-approved 2026-08-22 |
| Release & Versioning | Applies |

## License

Apache 2.0. Source data is California open data; per-source terms in PROVENANCE.md.
