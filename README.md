# Homeroom

**California's public school data, readable by the families it describes.**

> Working title. Not affiliated with the State of California or any school district.

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
`make data` validates and builds from there. CI never touches the network; a small
committed fixture exercises every rendering case. This mirrors the Afterward project's
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
Every user-visible string exists in both languages: 157 keys per locale, zero
present in one and missing from the other, enforced by test. The pages carry no
script, no external asset, no account, and no tracking.

Chronic absenteeism (D3) is the first measure Homeroom publishes that CDE masks
at real scale, and it is now built end to end (M3). The 2024-25 file (341,490
rows, acquired 2026-08-21) parses, joins the spine, and renders on every school
page: a total rate plus race/ethnicity, gender, and student-group breakdowns, each
beside its district and statewide figure, read from CDE's own `Charter School =
All` and `DASS = All` rows. Across the 10,534 active schools, the total rate is
published for 9,718 of them, withheld for 83, and not published for 733 that the
file never mentions; some subgroups are withheld far more often than that, up to
95.4% of the schools that have any row at all for American Indian or Alaska
Native students. `docs/SUPPRESSION-SHOWCASE.md` walks four real rows, one of each
cell state, from the source file to the rendered markup. Grade-span categories
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
the state dashboard indicators, and D6, per-pupil spending) are a plan recorded
in PROVENANCE.md too.

Nothing is published or hosted. Whether these pages belong on the internet is a
separate decision about real schools and real children, and no build makes it.

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
| Security & Supply-Chain | Applies |
| CI/CD | Applies |
| Observability | Applies (Tier C, library/CLI; declared in `docs/ROADMAP.md`) |
| Accessibility | Applies (gated from the first school page: html-validate and axe-core over every built page in both languages, plus structure and contrast checks in `make verify`) |
| Internationalization | Applies (EN/ES is a launch requirement; parity gate wired and merge-blocking as of ROADMAP M4) |
| AI Evaluation | N/A (no prompt, retrieval, or model-version surface) |
| Documentation | Applies |
| Quality & Metrics | Applies (see `docs/ROADMAP.md` metrics ledger) |
| Performance | Applies: the shipped surface is pre-rendered static HTML built from locally acquired files, with no client-side script and no network call at build time, and the pipeline is deterministic: re-running `make data` produces byte-identical artifacts. There is no hosted route, so no latency objective is declared. No page-weight or build-time budget is asserted in CI yet |
| AI Development Measurement | Applies: this project is built AI-assisted and says so below. The outcome side is the metrics ledger in `docs/ROADMAP.md`, where every gate names its measurement and its AUTO/REVIEW disposition, and every day-one value was measured against a named acquired file rather than estimated. The diagnostic counters the standard names (sessions, tokens, share of generated code, acceptance rate) are not instrumented here, and by the standard's own rule they would be observe-only if they were: they never gate a merge |
| Incident Response | Applies: `SECURITY.md` routes reports through GitHub private vulnerability reporting with a 72-hour acknowledgement target. There is no deployed service, no account, and no user data to breach; the incident this project can actually have is a wrong or mis-sourced figure on a school page, which is why masked cells are type-enforced to raise on read, why a number on a page that nothing counted fails the build, and why coverage is published beside the data. A severity ladder and a committed postmortem template are not yet in the repository |
| Data Governance | Applies: `PROVENANCE.md` is the register: every source is a named California Department of Education public file with its acquisition method, access date, and status, and a source that has not been acquired publishes nothing and says so in `coverage.json`. CDE small-cell masking is preserved as null, never zero and never interpolated; the CDS code is the only join key; no third-party or commercial data enters the pipeline. The artifacts are school-level public aggregates, not personal data, and the site has no account and no tracking. Raw source files are never committed and CI never fetches them |
| Release & Versioning | Applies |

## License

Apache 2.0. Source data is California open data; per-source terms in PROVENANCE.md.
