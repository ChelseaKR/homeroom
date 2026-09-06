# Roadmap: homeroom

## Problem

California publishes rich public data about its schools that almost no family can
read. The download pages serve researchers, the state dashboard flattens everything
into color bands, and commercial raters fill the gap with composite scores that
carry documented equity harms. Families are left choosing between unreadable
files and a misleading single number, and Spanish-speaking families are left
with even less.

## Product

Bilingual (English/Spanish) plain-language school pages built entirely from CDE
public files, joined on CDS codes. One page per school, each measure shown on its
own terms beside district and statewide context, with suppression and coverage
stated. No composite score, no ranking, ever (ADR 0002). No account, no tracking.

## Architecture

- Python 3.12+, stdlib-only runtime parsers, `uv`-managed dev tooling. Rejected:
  pandas and friends, because the parsers need exact cell-level control, not a
  dataframe dependency surface.
- Source files are locally acquired inputs in `data/raw/`: acquisition is a
  documented browser step per file, the way CDE's download pages are meant to be
  used (PROVENANCE.md). Rejected: automated fetch at build time, which hides
  provenance behind a script and makes every page depend on a live endpoint.
- CI never fetches a source file: no build step reaches CDE, and committed
  fixtures exercise every parsing and rendering case, including suppression.
  CI is not offline, and this line said it was until 2026-08-29: `make verify-ci`
  reaches a package index and an advisory database at `uv sync`, `npm ci`,
  `pip-audit`, `npm audit`, and the pinned `uvx` runs of semgrep and zizmor. What
  never crosses the network is the data.
- The `Measure` type carries three statuses (reported, suppressed, not reported)
  and makes masked cells unreadable as numbers (ADR 0002).
- Rendering target is static bilingual pages. The toolchain was chosen at M4 (ADR
  0001): stdlib Python renders the markup, strings live in typed per-locale
  dictionaries with a parity gate, and the node checkers (html-validate, axe-core
  in jsdom) run over pages built from committed fixtures and never ship in one.
  Rejected: a static site generator and a template engine, both of which put a
  silent empty cell between a withheld figure and the reader.

## Observability

Tier C (library/CLI) per `STANDARDS/OBSERVABILITY-STANDARD.md` §0 for the
pipeline, which is where the work is. As of 2026-08-22 there is also a hosted
surface: a static site on GitHub Pages, which emits nothing because it is files,
and one Lambda, whose observability is deliberately thin -- the runtime's
START/END/REPORT lines and a 14-day retention, with no request body and no
question ever logged (that is a privacy requirement, not an oversight; see
`docs/RESPONSIBLE-TECH-AUDITS.md`). What is watched instead is spend and volume:
a CloudWatch alarm on daily invocations against the approved envelope. OTel
stays out of scope; opt-in `--log-format json` is the entry point if the
pipeline ever needs it.

## Quality targets

Rigor is cited to `STANDARDS/`, not restated. This repo's values: branch coverage
>= 85% (cli archetype), `mypy --strict` on `src`, ruff lint and format, pip-audit,
gitleaks and semgrep in CI, 100% SHA-pinned `uses:`. `make verify` is the single
gate, byte-for-byte identical locally and in CI.

## Implementation plan

| Phase | Deliverable | Acceptance criteria |
|-------|-------------|----------------------|
| M0 | Scaffold conformant with `STANDARDS/` | `make verify` green; README conformance table has zero blank/unjustified rows |
| M1 (done 2026-08-07) | D1 directory spine parser | Verified against the live file: 18,396 rows parsed with no drift errors |
| M2 (done 2026-08-07) | D2 Census Day enrollment parser and spine join | 2025-26 file parses end to end; school totals join the spine; statewide sum reconciles with the state's own row |
| M3a (done 2026-08-07) | School profiles, subgroup measures, deterministic artifacts | One profile per active school (10,534 emitted from acquired data); every reporting category carries a reviewed display name, unreviewed codes fail the build; artifacts are byte-identical across re-runs; coverage (per-measure statuses, join gaps both ways, access dates, `is_fixture`) published beside the data; no published value is ever derived from complements, enforced by test |
| M3 (done 2026-08-21) | D3 chronic absenteeism | First masked-heavy measure end to end; every masked cell null, counted in coverage output |
| M3 (done 2026-08-21) | Suppression showcase | A committed artifact demonstrating null-never-zero rendering: masked cells shown as "not published", coverage stats published beside the data (`docs/SUPPRESSION-SHOWCASE.md`) |
| M4 (done 2026-08-08) | First bilingual school page, with district and statewide context | One real school rendered EN/ES from acquired data (Birch Lane Elementary, Davis Joint Unified, CDS 57726786056246); a11y and EN/ES parity gates wired and merge-blocking from this milestone; each measure sits beside its district and statewide figure, read from CDE's own `Charter=ALL` aggregate rows and never summed from schools |
| D5a (rebuilt against the real file 2026-08-21) | D5 teacher assignment monitoring parser | Parser, spine join, artifact and coverage output built and verified against the real acquired 2023-24 file; every rendering case and the drift refusals covered. Acceptance said "no D5 number published on any page or in `make data`'s default invocation, and PROVENANCE says why", which held from 2026-08-21 to 2026-09-05 and is superseded by ADR 0005 (row D5b) |
| D5b (published 2026-09-05, ADR 0005) | D5 on the school pages | The owner's decision on issue #59, recorded as an ADR: CDE's own whole-school row rendered on every page in both languages -- total teaching FTE, seven outcome FTE counts, seven outcome shares, every one a copied cell -- beside CDE's own district and statewide rows and with coverage stated. No headline figure, no share divided out of a count, no total summed from the file's other rows, no cross-school comparison. Wired into `make data`, `make site`, `make publish` and `make site-offline`, so the a11y and EN/ES gates read the new markup |
| A1 (built and deployed 2026-08-22, ADR 0003) | Grounded ask layer | One school per request; structuring, narration, verifier; fixed bilingual refusals; corpus of CDE definitions with hashes and retrieval dates; five committed evaluation suites with provenance-stamped results (157/157 on Bedrock claude-sonnet-4-6, 2026-08-22, real data; 23 of 534 model sentences withheld by the verifier); opt-in ask page that makes no request until a question is submitted, proven in a DOM; school pages byte-identical to a build without it; deployed 2026-08-22 as CloudFormation stack `homeroom-ask` in us-west-2 on Bedrock `global.anthropic.claude-sonnet-4-6`, verified live (cited answer, ranking bait refused, foreign origin rejected) |
| M5 | D4, D6 | Dashboard indicators and per-pupil spending joined where published. (D5 was the other decision tracked this way; it was made on 2026-09-05 and is ADR 0005, so D5 is now published rather than pending. This is the shape M5's two remaining decisions take.) Both sources were surveyed 2026-09-05 and both exist and are readable, one of them at a different address than this project had recorded; neither is acquired and neither publishes a number. What M5 now waits on is not a file but two decisions, and they are recorded under "M5 source survey" below |

## Metrics ledger

Exact shape per `STANDARDS/QUALITY-AND-METRICS-STANDARD.md` "Metrics ledger
(per repo)". Project-specific *values* go here; the *rigor* is cited to the
owning standard.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Branch coverage | >= 95% | `pytest --cov` in CI | AUTO | Chelsea Kelly-Reif |
| SHA-pinned `uses:` | 100% | `zizmor` / Scorecard Pinned-Deps >=9 | AUTO | Chelsea Kelly-Reif |
| Fixed HIGH+CRITICAL vulns (deps) | 0 | `pip-audit` in CI | AUTO | Chelsea Kelly-Reif |
| Masked cells readable as numbers | 0 (type-enforced) | `Measure` raises on read; `tests/test_measures.py` | AUTO | Chelsea Kelly-Reif |
| Unrecognized source sentinels | build fails | `parse_cell` hard error; parser drift tests | AUTO | Chelsea Kelly-Reif |
| Sources publishing a number without a recorded acquisition | 0 | access-date constants tested against PROVENANCE.md; `tests/test_artifacts.py` | AUTO | Chelsea Kelly-Reif |
| WCAG 2.2 A/AA violations on built pages | 0 | axe-core in jsdom plus html-validate, every page in both languages (`make pages`) | AUTO | Chelsea Kelly-Reif |
| Keys present in one locale and not the other | 0 | `tests/test_i18n.py` over every catalog | AUTO | Chelsea Kelly-Reif |
| Withheld or unpublished figures rendering a digit | 0 | `tests/test_pages.py` | AUTO | Chelsea Kelly-Reif |
| Numbers on a page that nothing counted | 0 | `tests/test_pages.py` checks every data cell against the pipeline's own values | AUTO | Chelsea Kelly-Reif |
| AI answers carrying an ordering, grade, score, or better/worse judgment (ranking-refusal suite) | 0 (measured 0 of 62, 2026-08-22, Bedrock claude-sonnet-4-6) | `evals/` ranking-refusal suite, scored on displayed text; verifier withholds in production | AUTO (when run live; `not_run` otherwise) | Chelsea Kelly-Reif |
| AI sentences rendering a withheld or unpublished cell as a value (suppression suite) | 0 (measured 0 of 24, same run) | `evals/` suppression suite against real suppressed cells | AUTO (when run live; `not_run` otherwise) | Chelsea Kelly-Reif |
| AI claims shown without a resolved citation | 0 (verifier-enforced) | `homeroom.ask` verifier; citation suite in `evals/` | AUTO | Chelsea Kelly-Reif |

### Day-one measured values (2026-08-07)

Every number below was measured against the named acquired file, not estimated.
Access dates and acquisition rules live in PROVENANCE.md.

| Value | Measured | Source |
|-------|----------|--------|
| Directory rows parsed, no drift errors | 18,396 | D1 `pubschls.txt`, acquired 2026-08-07 |
| Active schools | 10,534 | D1 |
| Districts | 1,059 by CDS code (corrected; 1,048 was recorded here, which counts distinct district *names* and so loses eleven districts: ten names cover more than one district each, nine of them two apiece and "Jefferson Elementary" three) | D1 |
| Counties | 58 (all) | D1 |
| Charter schools | 1,238 | D1 |
| Enrollment rows parsed (2025-26 Census Day) | 269,090 | D2 |
| School-level all-students totals | 10,558 | D2 |
| School totals joined to the directory spine | 9,860 | D1 + D2 join on CDS code |
| Rows carrying at least one `*` masked cell | 117,946 (corrected; first recorded as 88,207) | D2 |
| Statewide enrollment (state's own row) | 5,731,260 (corrected; 5,692,490 was recorded here but is the joined-schools sum) | D2 |

The join gap (10,558 school totals vs 9,860 joined) is a finding, not a defect to
hide: it is published as coverage, and understanding it is part of M3.

### M3a measured values (2026-08-07)

Measured by running `make data` against the acquired files; the artifacts are
reproducible byte for byte (identical SHA-256 across re-runs). Two day-one D2
values above were corrected during this re-measurement, as marked.

| Value | Measured | Source |
|-------|----------|--------|
| School profiles emitted (one per active school) | 10,534 | `make data`, D1 + D2 |
| Subgroup measures reported / suppressed / not reported | 182,362 / 0 / 80,988 | `make data`, 25 subgroup codes x 10,534 profiles |
| Total-enrollment measures reported / suppressed / not reported | 9,860 / 0 / 674 | `make data` |
| Join gap: school totals without a directory match | 698 (68 closed in D1, 153 match nameless D1 rows, 477 absent from D1) | D1 + D2 |
| Join gap: active schools without enrollment rows | 674 | D1 + D2 |
| ReportingCategory codes observed, all with reviewed names | 33 | D2; names checked against CDE's file structure page |
| Masked cells in the 2025-26 file | 1,329,558, all in grade columns of school-level rows; `TOTAL_ENR` is never masked | D2 |
| School-level all-students totals, summed | 5,731,260, reconciling exactly with the state's own row | D2 |

Suppressed counts are zero in this table because CDE does not mask any cell M3a
publishes (subgroup totals and all-students grade spans) in this file. The
masking lives in subgroup-by-grade cells, which profiles do not carry. The
suppressed path is exercised by the committed fixtures and stays load-bearing
for M3, the first masked-heavy dataset.

### M3 measured values (2026-08-21)

Measured by running `make data` and `make site` against the acquired D1, D2 and
D3 files together (`chronicabsenteeism25.txt`, the 2024-25 file, acquired
2026-08-21; PROVENANCE.md D3). Unlike M3a, this is genuinely the masked-heavy
case the roadmap named at M3: CDE withholds a meaningful share of these cells,
not zero of them. `docs/SUPPRESSION-SHOWCASE.md` walks four real rows (one of
each of the four cell states) from source file to rendered markup.

| Value | Measured | Source |
|-------|----------|--------|
| Chronic absenteeism file rows parsed | 341,490 | D3 `chronicabsenteeism25.txt`, acquired 2026-08-21 |
| Reporting-category codes observed, all with reviewed names | 25 | D3; checked against CDE's file structure page (fsabd.asp) |
| Rows carrying a mask on at least one of the three numeric cells | 104,469 of 341,490 (30.6%); masking is always all three cells together, never a subset | D3 |
| Total chronic-absenteeism rate: reported / suppressed / not reported | 9,718 / 83 / 733 | `make data`, D1 + D2 + D3, across 10,534 active schools |
| Join gap: absenteeism rows without a directory match | 263 | D1 + D3 |
| Join gap: active schools without an absenteeism row | 733 | D1 + D3 |
| Subgroup category suppressed most often, of schools with any row for it | `GX` (Non-binary): 55 reported, 1,990 suppressed of 2,045 with any row (97.3%). A rendered subgroup, in the `gender` family. Its denominator is the small one: 8,489 active schools have no `GX` row at all, where `RI` has one at 9,801 of 10,534 | `make data` |
| Subgroup category suppressed most often among those with a row at nearly every school | `RI` (American Indian or Alaska Native): 451 reported, 9,350 suppressed of 9,801 with any row (95.4%). This row said `RI` was the maximum until 2026-08-29; `GX` above is | `make data` |
| Subgroup categories suppressed for over 94% of the schools with any row for them | 3 (`GX` 97.3%, `RI` 95.4%, `RP` 94.6%) | `make data`, `docs/SUPPRESSION-SHOWCASE.md` |
| Subgroup category suppressed least often, of schools with any row for it | `TA` (all students): 9,718 reported, 83 suppressed (0.8%) | `make data` |
| Chronic-absenteeism section rendered on Birch Lane Elementary's page | 4 tables (total, race/ethnicity, gender, student groups), 19 rows total, three of the four cell states present in that section (published figure, withheld, no figure published). The fourth, a published zero, is on the same page in the grade-span table; this row claimed all four were in the D3 section until 2026-08-29 | `make site`, CDS 57726786056246 |
| D3 figures computed rather than copied | 0 (the rate is read from `ChronicAbsenteeismRate`, never divided out of the count and eligible-enrollment columns) | `tests/test_absenteeism.py`, `tests/test_artifacts.py` |
| WCAG violations with M3 present, axe-core A/AA plus best-practice | 0 across 6 rule sets, both languages | `tools/a11y.mjs`, fixture build with `--absenteeism` |
| Page re-runs with D3 present producing different bytes | 0 | `tests/test_pages.py::test_absenteeism_reruns_are_byte_identical` |

Grade-span categories (`GRTKKN`...`GR912`, 6 codes) are recognized so the real
file parses without drift but are not rendered as a subgroup, the same choice D2
makes for its own `AR_*` age-range codes; they are not counted in the table above.

### D5a values (rebuilt against the real file, 2026-08-21)

D5 was "awaiting acquisition" through M4; it has since been acquired and its
schema verified against the real file (issue #5), and every figure below is
measured against `tamo2324.txt` (the 2023-24 Teacher Assignment Monitoring
Outcome file, 234,206,408 bytes, 1,528,796 rows, acquired 2026-08-21;
PROVENANCE.md D5), not the synthetic fixture the parser was originally written
against. The provisional contract did not survive contact with the real file:
five outcomes should have been seven, one row per school should have been up to
150, and the column names were wrong in every particular (PROVENANCE.md D5 has
the full list). `src/homeroom/assignments.py` and `fixtures/tamo.sample.txt`
were rewritten to match what follows. Acquired was not published: from
2026-08-21 to 2026-09-05 no D5 number about a real school reached `make data`'s
default invocation or any page, because publishing was a separate decision this
roadmap had not made. It was made on 2026-09-05 (ADR 0005, issue #59), and the
rows below are the acquisition's own measurements, unchanged; what publishing
measured is under "D5b published values".

| Value | Measured | Source |
|-------|----------|--------|
| D5 files acquired | 1 (`tamo2324.txt`, 2023-24) | PROVENANCE.md D5 |
| D5 numbers published about a real school, 2026-08-21 to 2026-09-05 | 0 | not wired into `make data`'s or `make site`'s default invocation, by design, until ADR 0005 |
| Rows in the acquired file | 1,528,796, across 10,064 distinct schools (up to 150 rows per school: one per subject/grade-span/experience/credential combination) | D5 `tamo2324.txt` |
| The one whole-school total row per school | Experience Level = Credential Level = `ALL`, Subject Area = `TA`; verified present exactly once for all 10,064 schools | D5, `src/homeroom/assignments.py` `school_outcomes` |
| Assignment outcomes carried per school | 7 (`clear`, `out_of_field`, `intern`, `ineffective`, `incomplete`, `unknown`, `na`), not the 5 the provisional contract carried | `src/homeroom/assignments.py`, verified against the acquired header |
| Masked cells found anywhere in the acquired file | 0 of 1,528,796 rows x 15 numeric columns; unlike D2 and D3, this file's own file-structure page states no small-cell suppression rule | D5, scanned 2026-08-21 |
| Values computed rather than copied | 0 (shares are read from the file, never divided out of counts; the whole-school row is CDE's own aggregate, never summed here from the other ~149 rows) | `tests/test_assignments.py`, `tests/test_artifacts.py` |
| Rendering cases covered by the fixture | 4 (reported, genuine zero, masked, missing) plus a wholly-withheld school and a distractor row proving the selector ignores non-total rows | `fixtures/tamo.sample.txt` |
| Drift refusals covered | 14 (missing column, renamed column, unreviewed aggregate level, unreviewed charter value, unreviewed DASS value, unreviewed grade span, unreviewed experience level, unreviewed credential level, unreviewed subject area, non-numeric CDS, overlong CDS, unknown sentinel, percent-sign format, duplicate whole-school-total row) | `tests/test_assignments.py` |

### D5b published values (ADR 0005, 2026-09-05)

The decision on issue #59, and what it put on the page. Every figure below was
measured by building the fixture site and running the gates over it, which is
what runs with no acquired file and no network. The acquired-file coverage
numbers are deliberately absent from this table: `make site` runs on the machine
that holds `data/raw/`, and this row would rather say nothing than state a count
nobody measured -- the same rule that kept D5 unpublished until it was decided.

| Value | Measured | Source |
|-------|----------|--------|
| Tables added to each school page | 3 (whole-school total, FTE count per outcome, published share per outcome) | `src/homeroom/render.py` `_assignments_section` |
| Measures added to each school page | 15 rows (1 total + 7 outcome counts + 7 outcome shares), each in three columns: this school, its district, California; 45 cells | `make site-offline` |
| Cell states present in the D5 section of one fixture page | 4 of 4 (5 published numbers, 6 genuine zeros, 2 withheld, 2 nothing published, on Example Elementary's English page) | `build/site-offline/01100170112345.en.html` |
| Coverage rows added to each page's coverage section | 3 (schools publishing a teaching assignment total, withholding it, publishing none) | `src/homeroom/render.py` `_coverage_section` |
| Fixture-build assignment coverage across 3 active schools | reported=1, suppressed=1, not_reported=1 | `make site-offline` |
| D5 values computed rather than copied | 0 (shares are read from CDE's percent columns, never divided out of the counts; the whole-school row is CDE's own aggregate; district and statewide rows are CDE's own, never summed from schools) | `tests/test_pages.py::test_every_assignment_cell_is_exactly_what_the_pipeline_holds` |
| Dimensions that must all read their aggregated value for a row to be a district's own | 6 (charter status, DASS, grade span, experience level, credential level, subject area) | `src/homeroom/context.py` `load_assignment_context` |
| D5 context drift refusals covered | 7 (a slice on any of the six dimensions taken as the entity, a summed alternative, a masked aggregate cell, an absent district, duplicate whole-entity rows, a missing statewide row, aggregate rows spanning two years) | `tests/test_context.py` |
| Other schools named anywhere in a school page's D5 section | 0 (ADR 0002: the section is about one school, beside CDE's own district and statewide rows, and nothing else) | `tests/test_pages.py::test_the_assignment_section_names_no_other_school` |
| New bilingual strings | 19 per locale (12 interface, 7 outcome names), 38 total | `src/homeroom/i18n.py` |
| WCAG violations with D5 present, axe-core A/AA plus best-practice | 0 across 6 rule sets, 17 pages, both languages | `make pages` |
| html-validate errors with D5 present | 0 | `make htmlvalidate` |
| Page re-runs with D5 present producing different bytes | 0 | `tests/test_pages.py::test_assignment_reruns_are_byte_identical`, and `make determinism` |
| Suite size and branch coverage after D5b | 646 tests, 98.68% (floor is 95%); 621 and 98.69% before | `make test` |

The three sections a page can now carry report on three different school years --
D2's 2025-26, D3's 2024-25, D5's 2023-24 -- and each names its own in its own
captions. A build given no D5 file renders no section at all and says so in
words, which is a different page from one whose D5 cells are all empty and a
different fact from a school the file does not mention.

### M4 measured values (2026-08-07)

Measured by running `make site` against the acquired files and `make pages`
against the committed fixtures. At M4 the page build read D1 and D2 and nothing
else, so no D5 figure could reach a page and the pages said that in words
instead; D3 joined at M3 and D5 at ADR 0005, and a build given neither still says
so in words rather than leaving a gap.

| Value | Measured | Source |
|-------|----------|--------|
| Real school rendered EN and ES from acquired data | 1 school, 2 pages | `make site`, Birch Lane Elementary (CDS 57726786056246) |
| Figures published on that school's English page | 36 (corrected; recorded here as "30 numbers, 6 of them genuine published zeros", but the 6 are beside the 30, not among them: 30 `m-number` cells plus 6 `m-zero` cells, and 30 + 6 + 4 never published is the 40 below) | D2, 2025-26 |
| Figures on that page the state withheld / never published | 0 withheld, 4 never published | D2, 2025-26 |
| Measures per page | 40 (1 total, 14 grade spans, 25 subgroups), each in three columns: this school, its district, California | `src/homeroom/render.py` |
| Coverage published beside each figure | 3 columns per row (publishing, withholding, publishing nothing), counted across 10,534 active schools | D1 + D2 |
| Total-enrollment coverage stated on every page | 9,860 publishing, 0 withheld, 674 publishing nothing | D1 + D2 |
| Pages the accessibility gate checks | 17 (`build/site-offline`: 3 fixture schools x 2 languages plus the landing page; `build/site-offline/ask`: 3 x 2 ask pages; `build/site-offline/county` and `build/site-offline/district`: 1 x 2 each, added 2026-09-05 with the browse hierarchy). `tools/a11y.mjs` is run once per directory and does not recurse, so counting one of them reported 6, and a directory with no run of its own is covered by nothing | `make pages` |
| WCAG violations, axe-core A/AA plus best-practice | 0 across 6 rule sets, both languages | `tools/a11y.mjs` |
| html-validate errors, conformance plus a11y presets | 0 | `make htmlvalidate` |
| User-visible strings carried in both languages | 217 keys per locale, 434 strings total (134 interface, 33 reporting categories, 14 grade spans, 4 subgroup families, 25 chronic-absenteeism categories, 7 teacher-assignment outcomes); 122 keys and 71 interface at M4, before D3 added its own 25-code catalog and 10 interface strings, 157 before the ask layer (ADR 0003) added 33 fixed interface strings (its labels, every refusal, and the ask page's own copy, none of which the model writes), 190 before the landing page added the two strings its front door needs, and 192 before the ask page stopped using a refusal as its help text and needed a help string of its own, 193 before publishing all 10,534 schools made a flat front door unusable and the county/district browse traded the landing page's schools heading for five of its own, and 198 before ADR 0005 published D5 and needed a seven-outcome catalog plus twelve interface strings for its section, its captions, its coverage rows and its source entry | `src/homeroom/i18n.py` |
| Keys present in one locale and not the other | 0 | `tests/test_i18n.py` |
| Spanish strings left identical to their English original | 3, all reviewed and named (the project's own name; CDE's two different Filipino category codes, `RE_F` in D2 and `RF` in D3, each the same word in Spanish) | `tests/test_i18n.py` |
| D5 numbers on any page, before ADR 0005 | 0, including when a profile carrying parsed assignment outcomes was handed to the renderer. A build given no D5 file still publishes none and says so in words, which is the half of that claim that is still live and still tested | `tests/test_pages.py` |
| Page re-runs producing different bytes | 0 | `tests/test_pages.py`, plus a double build compared by hash in CI |
| Branch coverage after M4 | 98.73% (floor is 95%) | `make test` |

The withheld count on the real page is zero for the same reason the M3a table
records: CDE does not mask the cells M4 publishes in this file. The withheld
rendering path is load-bearing anyway, and the fixture pages exercise it, because
D3 is a masked-heavy dataset and these are the pages it will land on.

### M5 source survey (2026-09-05)

M5 is the one unshipped milestone in the table above, and it had never been
established that its two sources exist in the shape the milestone assumes. They
were surveyed on 2026-09-05: every figure below was measured by opening the real
published files, not read off a description of them. Neither source is acquired.
The files are not in `data/raw/`, no access date is recorded, and no number from
either reaches an artifact or a page; PROVENANCE.md D4 and D6 carry the full
record and say why *surveyed* is a weaker word than *acquired*.

Two things were found that a plan written from the download pages would have got
wrong, and one of them was already written down here as fact.

| Value | Measured | Source |
|-------|----------|--------|
| D4 files behind "the Dashboard indicators", 2025 | 9 (eight state indicators -- ELA, Math, Science, Chronic Absenteeism, Suspension, Graduation, College/Career, English Learner Progress -- plus a Growth Model file), not one file | D4 download pages under `/ta/ac/cm/` |
| D4 bytes and data rows across those nine | 153,581,873 bytes, 1,104,219 rows | D4, surveyed 2026-09-05 |
| D4 column counts | 17 (Growth) to 109 (College/Career); 22 columns common to all eight indicator files | D4 |
| D4 files spelling the change-level column `changelevel` / `changeLevel` | 7 / 1 (Chronic Absenteeism is the one); a parser matching a single spelling drops the column on the other file without failing | D4 |
| D4 cells masked with `*`, the sentinel D2 and D3 use | 0 of all nine files. Suppression here is a *blank cell*: 37,763 of the 114,225 chronic rows carry a blank `currnumer` and `currstatus` while `currdenom` is populated | D4 |
| D4 rows where `color` is `0`, which CDE's layout defines as "No Color" rather than a value | 55,651 of 114,225 (chronic). `statuslevel`, `changelevel` and `box` use `0` the same way | D4 record layout `/ta/ac/cm/chronic24.asp` |
| D4 `studentgroup` codes needing reviewed display names | 21 across the nine files (2 in ELPI, 20 in ELA/Math/Science); a third vocabulary, sharing codes with neither D2's nor D3's | D4 |
| D4 school coverage | 2,551 schools (College/Career, Graduation) to 9,969 (Suspension); 9,971 distinct schools across all nine | D4 |
| D4 context available from CDE's own aggregate rows | Yes: `rtype` carries `D` (district) and `X` (state) rows, so district and statewide figures are read, never summed | D4 |
| D6 school-level rows in the source this roadmap had recorded (SACS / Current Expense of Education) | 0. Both are LEA-level; Current Expense of Education says on its own page it "is calculated at a school district level", and SACS ships as self-extracting Windows `.exe` archives for Microsoft Access | https://www.cde.ca.gov/ds/fd/ec/, https://www.cde.ca.gov/ds/fd/fd/ |
| Distinct values in `STEXP`, the per-pupil column of the SARC file that is school-grained | 1 (11146.18) across all 10,274 school rows: the statewide figure repeated, not the school's. CDE's note on that page: "The CDE provides State Expenditures Per Pupil (Unrestricted) ... The remaining data is to be provided by the LEA" | `sarc2425/expend.txt`, surveyed 2026-09-05 |
| D6 source that does publish a school figure | ESSA Per-Pupil Expenditure, https://www.cde.ca.gov/fg/ac/es/essappedata.asp -- required by ESEA sections 1111(h)(1)(C)(x) and 1111(h)(2)(C), and at a different address than this project had recorded | D6 |
| D6 school rows, columns, and CDS shape | 10,065 rows over 11 columns (header on row 7), every CDS code 14 characters, none duplicated | `essappe2425data.xlsx`, 1,035,042 bytes |
| D6 district context rows | 1,980, on the workbook's second sheet and a different 7-column layout: CDE's own LEA aggregate, never a sum of schools. It is not column-comparable to the school sheet, which has no counterpart to its `Expenditures-Excluded ($)` column | D6 |
| D6 withheld rows, and the sentinel | 187 of 10,065, marked `DNR` ("Did Not Report") rather than `*`, and always all four expenditure columns together, never a subset | D6 |
| D6 genuine zeros, which are not the same thing | 1,352 / 842 / 817 / 140 across the four expenditure columns, so zero-versus-withheld is live in this file rather than theoretical | D6 |
| D6 published totals | 0. The file publishes four per-pupil components (School-Federal, School-State & Local, Central-Federal, Central-State & Local) and no total, so a single "per-pupil spending" figure would have to be summed rather than copied | D6 |
| D6 denominators in use | 3: `Student Membership Type` is Census Day Enrollment on 9,767 rows, Cumulative Enrollment on 203, Annual ADA on 95, so two schools' figures are not necessarily per the same count | D6 |

What M5 waits on is therefore not a file. It is two decisions, and both are the
kind this project makes explicitly rather than in a parser:

1. **May a Dashboard band be shown at all?** `color`, `statuslevel`,
   `changelevel` and `box` are an ordered, state-assigned performance band
   (1=Red through 5=Blue; `box` is a position in a 5x5 grid). Rendering one is
   rendering an ordering of schools, which is what ADR 0002 refuses. The plain
   figures in the same files -- `currstatus`, `currnumer`, `currdenom`, `change`
   -- are copyable cells and raise no such question, and D4 without the bands is
   a coherent, smaller deliverable. This is the same shape of decision as the
   one about publishing D5, which was open when this was written and was made on
   2026-09-05 (ADR 0005). D5's answer does not settle this one: D5's outcomes are
   counts the state published and a band is an ordering the state assigned, which
   is the distinction ADR 0002 turns on. It needs an ADR either way.
2. **What number is "per-pupil spending"?** There is no published total, so the
   honest options are to show CDE's four components as four measures or to show
   none. Summing them is a computed cell, and on a `DNR` row a sum would read a
   withheld component as zero -- the exact failure the no-derived-values rule
   exists to prevent. The mixed denominators are a second reason not to let one
   number stand alone.

A third item is smaller but real: D6 publishes XLSX only, with no TXT or CSV, so
reading it needs a stdlib XLSX reader (`zipfile` plus `xml.etree` over the shared
string table). That stays inside ADR 0001's stdlib-only rule -- no new dependency
-- but it is new surface, and worth naming before it is written rather than after.

**That reader now exists: `src/homeroom/xlsx.py`, written 2026-09-05, and it
changes none of the above.** It reads a file format -- bytes of an .xlsx in, rows
of cells out -- and nothing else. It does not know what `DNR` means, which
columns hold per-pupil dollars, or that CDS codes exist; it publishes no number,
adds no page, and touches no artifact. D6 remains **unacquired**: it is not in
`data/raw/`, no access date is recorded for it, nothing in the build or the gate
fetches it, and both decisions above are still open. What the reader buys is that
when one of them is made, the file's format is not also an open question. It is
covered by `tests/test_xlsx.py`, whose fixtures are assembled in the tests from
hand-written XML rather than committed as binary, over the hazards the format
actually has -- the shared string table, inline strings, cells with no value,
skipped cells and skipped rows (column position comes from the `r` attribute, so
a sparse row cannot shift left), numbers held as text and as numbers, and
formula results -- and over its refusals, which follow `DirectoryDriftError` and
`parse_cell`: a missing sheet, an unresolvable shared-string index, an
unparseable cell reference, an unreviewed cell type, or a zip that would expand
absurdly all raise rather than return an empty answer.

## Scoping: N/A declarations

Mirrors the README Standards Conformance table; never a silent skip.

- Accessibility: applies as of M4, gates wired and merge-blocking (html-validate
  and axe-core over every built page in both languages, plus structure and
  contrast checks in `make test`). Re-verified at M3 (2026-08-21) with the four
  new chronic-absenteeism tables present in the fixture build: zero violations,
  same six rule sets. What no headless gate settles is named in README.md and
  tracked as RR-05 in `docs/audits/residual-risk-register.md`: layout, reflow,
  focus visibility in practice, and a screen-reader walkthrough in both
  languages still need a person, and that walkthrough is not yet done. M3
  deliberately kept its new tables at the same seven columns as the existing
  ones, rather than widening them, while this gate is open. Since 2026-09-05
  the open half has a procedure and an empty record rather than only a
  sentence: `docs/accessibility-walkthrough.md` covers all five published page
  types -- landing, county, district, school and ask -- in both languages, and
  its results table reads UNMET in every cell with no date and no name against
  any of them. `tests/test_accessibility_review.py` derives the page types from
  the published site, so a sixth one added without a walkthrough section fails
  the suite, and holds this bullet, README.md, RR-05 and
  `docs/RESPONSIBLE-TECH-AUDITS.md` §E to what that record says.
- Internationalization: applies, and the parity gate is wired as of M4. Every
  user-visible string exists in English and Spanish, a missing key raises instead
  of falling back, and CDE's English-only school and district names are marked
  `lang="en"` on Spanish pages. What the gate cannot check is whether the Spanish
  is good; CONTRIBUTING.md asks for review.
- AI Evaluation: applies as of ADR 0003 (2026-08-21). `src/homeroom/ask/` is
  a prompt, retrieval, and model-version surface, evaluated by the five suites
  in `evals/`; results carry provider, model, prompt version, commit, and date.
  AI-assisted development is separately disclosed in the README.
- Observability Tiers A/B: partially applicable since 2026-08-22, when the site
  and the ask service were deployed. What is in place is the invocation alarm and
  the cost envelope; what is not is a latency or error-rate objective, a dashboard,
  or any tracing. The constraint that shapes it is that the one hosted route must
  not log what it is asked, so the usual request-level telemetry is unavailable by
  design and anything added has to work from counts alone.
  The ask service (ADR 0003) becomes a Tier A/B surface if and when it is
  deployed; the prepared deployment shape names the counters it would emit.
