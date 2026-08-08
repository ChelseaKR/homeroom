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
stated. No composite score, no ranking, ever (ADR 0000). No account, no tracking.

## Architecture

- Python 3.12+, stdlib-only runtime parsers, `uv`-managed dev tooling. Rejected:
  pandas and friends, because the parsers need exact cell-level control, not a
  dataframe dependency surface.
- Source files are locally acquired inputs in `data/raw/`: acquisition is a
  documented browser step per file, the way CDE's download pages are meant to be
  used (PROVENANCE.md). Rejected: automated fetch at build time, which hides
  provenance behind a script and makes every page depend on a live endpoint.
- CI never touches the network; committed fixtures exercise every parsing and
  rendering case, including suppression.
- The `Measure` type carries three statuses (reported, suppressed, not reported)
  and makes masked cells unreadable as numbers (ADR 0000).
- Rendering target is static bilingual pages. The toolchain was chosen at M4 (ADR
  0001): stdlib Python renders the markup, strings live in typed per-locale
  dictionaries with a parity gate, and the node checkers (html-validate, axe-core
  in jsdom) run over pages built from committed fixtures and never ship in one.
  Rejected: a static site generator and a template engine, both of which put a
  silent empty cell between a withheld figure and the reader.

## Observability

Tier C (library/CLI) per `STANDARDS/OBSERVABILITY-STANDARD.md` §0: a local
pipeline with no hosted service or frontend. OTel is documented out of scope for
this tier; opt-in `--log-format json` is the entry point if a service surface ever
appears. Tiers A/B: N/A until something is hosted.

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
| M3 | D3 chronic absenteeism | First masked-heavy measure end to end; every masked cell null, counted in coverage output |
| M3 | Suppression showcase | A committed artifact demonstrating null-never-zero rendering: masked cells shown as "not published", coverage stats published beside the data |
| M4 (done 2026-08-07) | First bilingual school page | One real school rendered EN/ES from acquired data (Birch Lane Elementary, Davis Joint Unified, CDS 57726786056246); a11y and EN/ES parity gates wired and merge-blocking from this milestone |
| D5a (parser built 2026-08-07, awaiting acquisition) | D5 teacher assignment monitoring parser | Parser, spine join, artifact and coverage output built and tested against a synthetic fixture matching the documented file structure; every rendering case and the drift refusals covered; no D5 number published and PROVENANCE says why |
| M5 | D4-D6 | Dashboard indicators, teacher assignment (CalSAAS) with a file in hand, and per-pupil spending joined where published |

## Metrics ledger

Exact shape per `STANDARDS/QUALITY-AND-METRICS-STANDARD.md` "Metrics ledger
(per repo)". Project-specific *values* go here; the *rigor* is cited to the
owning standard.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Branch coverage | >= 85% | `pytest --cov` in CI | AUTO | Chelsea Kelly-Reif |
| SHA-pinned `uses:` | 100% | `zizmor` / Scorecard Pinned-Deps >=9 | AUTO | Chelsea Kelly-Reif |
| Fixed HIGH+CRITICAL vulns (deps) | 0 | `pip-audit` in CI | AUTO | Chelsea Kelly-Reif |
| Masked cells readable as numbers | 0 (type-enforced) | `Measure` raises on read; `tests/test_measures.py` | AUTO | Chelsea Kelly-Reif |
| Unrecognized source sentinels | build fails | `parse_cell` hard error; parser drift tests | AUTO | Chelsea Kelly-Reif |
| Sources publishing a number without a recorded acquisition | 0 | access-date constants tested against PROVENANCE.md; `tests/test_artifacts.py` | AUTO | Chelsea Kelly-Reif |
| WCAG 2.2 A/AA violations on built pages | 0 | axe-core in jsdom plus html-validate, every page in both languages (`make pages`) | AUTO | Chelsea Kelly-Reif |
| Keys present in one locale and not the other | 0 | `tests/test_i18n.py` over every catalog | AUTO | Chelsea Kelly-Reif |
| Withheld or unpublished figures rendering a digit | 0 | `tests/test_pages.py` | AUTO | Chelsea Kelly-Reif |
| Numbers on a page that nothing counted | 0 | `tests/test_pages.py` checks every data cell against the pipeline's own values | AUTO | Chelsea Kelly-Reif |

### Day-one measured values (2026-08-07)

Every number below was measured against the named acquired file, not estimated.
Access dates and acquisition rules live in PROVENANCE.md.

| Value | Measured | Source |
|-------|----------|--------|
| Directory rows parsed, no drift errors | 18,396 | D1 `pubschls.txt`, acquired 2026-08-07 |
| Active schools | 10,534 | D1 |
| Districts | 1,048 | D1 |
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

### D5a values (2026-08-07)

This table has no acquired-data column, and that absence is the point. D5 was not
acquired, so there is nothing to measure about California's teachers here yet.
What follows is measured against the committed synthetic fixture, which is what
the parser was built against.

| Value | Measured | Source |
|-------|----------|--------|
| D5 files acquired | 0 | PROVENANCE.md D5, "awaiting acquisition" |
| D5 numbers published about a real school | 0 | no acquired file exists to publish from |
| Assignment outcomes carried per school | 5, each as a count and a published share | `src/homeroom/assignments.py` |
| Values computed rather than copied | 0 (shares are read from the file, never divided out of counts) | `tests/test_assignments.py`, `tests/test_artifacts.py` |
| Rendering cases covered by the fixture | 4 (reported, genuine zero, masked, missing) plus a wholly-withheld school | `fixtures/tamo.sample.txt` |
| Drift refusals covered | 8 (missing column, renamed column, unreviewed aggregate level, non-numeric CDS, overlong CDS, unknown sentinel, percent-sign format, duplicate school row) | `tests/test_assignments.py` |

### M4 measured values (2026-08-07)

Measured by running `make site` against the acquired files and `make pages`
against the committed fixtures. The page build reads D1 and D2 and nothing else,
so no D5 figure can reach a page; the pages say that in words instead.

| Value | Measured | Source |
|-------|----------|--------|
| Real school rendered EN and ES from acquired data | 1 school, 2 pages | `make site`, Birch Lane Elementary (CDS 57726786056246) |
| Figures published on that school's English page | 30 numbers, 6 of them genuine published zeros | D2, 2025-26 |
| Figures on that page the state withheld / never published | 0 withheld, 4 never published | D2, 2025-26 |
| Measure cells per page | 40 (1 total, 14 grade spans, 25 subgroups) | `src/homeroom/render.py` |
| Coverage published beside each figure | 3 columns per row (publishing, withholding, publishing nothing), counted across 10,534 active schools | D1 + D2 |
| Total-enrollment coverage stated on every page | 9,860 publishing, 0 withheld, 674 publishing nothing | D1 + D2 |
| Pages the accessibility gate checks | 6 (3 fixture schools x 2 languages) | `make pages` |
| WCAG violations, axe-core A/AA plus best-practice | 0 across 6 rule sets, both languages | `tools/a11y.mjs` |
| html-validate errors, conformance plus a11y presets | 0 | `make htmlvalidate` |
| User-visible strings carried in both languages | 120 keys per locale, 240 strings (69 interface, 33 reporting categories, 14 grade spans, 4 subgroup families) | `src/homeroom/i18n.py` |
| Keys present in one locale and not the other | 0 | `tests/test_i18n.py` |
| Spanish strings left identical to their English original | 2, both reviewed and named (the project's own name; CDE's Filipino category, the same word in Spanish) | `tests/test_i18n.py` |
| D5 numbers on any page, including when the parsed file is loaded into the renderer | 0 | `tests/test_pages.py` |
| Page re-runs producing different bytes | 0 | `tests/test_pages.py`, plus a double build compared by hash in CI |
| Branch coverage after M4 | 99% (floor is 85%) | `make test` |

The withheld count on the real page is zero for the same reason the M3a table
records: CDE does not mask the cells M4 publishes in this file. The withheld
rendering path is load-bearing anyway, and the fixture pages exercise it, because
D3 is a masked-heavy dataset and these are the pages it will land on.

## Scoping: N/A declarations

Mirrors the README Standards Conformance table; never a silent skip.

- Accessibility: applies as of M4, gates wired and merge-blocking (html-validate
  and axe-core over every built page in both languages, plus structure and
  contrast checks in `make test`). What no headless gate settles is named in
  README.md: layout, reflow, focus visibility in practice, and a screen-reader
  walkthrough in both languages still need a person, and that walkthrough is not
  yet done.
- Internationalization: applies, and the parity gate is wired as of M4. Every
  user-visible string exists in English and Spanish, a missing key raises instead
  of falling back, and CDE's English-only school and district names are marked
  `lang="en"` on Spanish pages. What the gate cannot check is whether the Spanish
  is good; CONTRIBUTING.md asks for review.
- AI Evaluation: N/A. No LLM, prompt, retrieval, or model-version surface.
  AI-assisted development is disclosed in the README; it is a build-time practice,
  not a product surface.
- Observability Tiers A/B: N/A, no hosted service or frontend (Tier C declared
  above).
