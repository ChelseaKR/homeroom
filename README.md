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

CDE's download endpoints sit behind a bot-protection layer that challenges non-browser
clients. The pipeline therefore treats source files as **locally acquired inputs**: fetch
them in a browser session (documented per-file in PROVENANCE.md), drop them in `data/raw/`,
and `make data` validates and builds from there. CI never touches the network; a small
committed fixture exercises every rendering case. This mirrors the Afterward project's
answer to the same problem with federal endpoints.

## Status

Day one. The school-directory parser (the spine every other dataset joins against, via
CDS codes) is built, tested against a fixture, and verified against the live file
(acquired 2026-08-07): 18,396 directory rows parsed with no drift errors, yielding
10,534 active schools across 1,048 districts and all 58 counties, 1,238 of them
charters. Everything else is a plan recorded in PROVENANCE.md.

## License

Apache 2.0. Source data is California open data; per-source terms in PROVENANCE.md.
