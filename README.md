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
10,534 active schools across 1,048 districts and all 58 counties, 1,238 of them
charters. The 2025-26 Census Day enrollment file (269,090 rows, acquired the same
day) parses end to end and joins that spine, and `make data` now assembles one
profile per active school, with total, grade-span, and subgroup enrollment as
three-status measures, and emits deterministic JSON artifacts: 10,534 profiles,
byte-identical across re-runs, coverage published beside the data (9,860 school
totals joined, the 698-plus-674 join gap counted in both directions, masks kept
as nulls).

Teacher assignment monitoring (D5) has a parser and no data yet. CDE publishes
these files from the Commission on Teacher Credentialing's CalSAAS system: by
school, how many teaching assignments were held on a clear credential and
appropriately matched to the assignment, and how many sat in one of the other
authorization states the state tracks. The parser, its coverage output, and its
join to the spine are built and tested against a synthetic fixture, because no D5
file has been acquired here. So no D5 number about a real school is published
anywhere, the column names the parser expects are provisional until the file is
in hand, and PROVENANCE.md says both in as many words. The remaining datasets are
a plan recorded there too.

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
| Accessibility | N/A at day one (no HTML surface); applies from the first school page (ROADMAP M4) |
| Internationalization | Applies (EN/ES is a launch requirement; parity gate wired at ROADMAP M4) |
| AI Evaluation | N/A (no prompt, retrieval, or model-version surface) |
| Documentation | Applies |
| Quality & Metrics | Applies (see `docs/ROADMAP.md` metrics ledger) |
| Release & Versioning | Applies |

## License

Apache 2.0. Source data is California open data; per-source terms in PROVENANCE.md.
