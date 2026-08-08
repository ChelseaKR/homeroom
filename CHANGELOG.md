# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- First bilingual school pages (M4): `src/homeroom/render.py` renders one static
  HTML page per school per language from the existing profiles, and `make site` /
  `make site-offline` build them. Birch Lane Elementary in Davis Joint Unified
  renders from the acquired files in English and Spanish; the fixture build
  renders every committed school in both languages and says on the page that the
  data is not real. Pages carry no script, no external asset, no account, and no
  tracking, and nothing is deployed or hosted.
- Four cell states that never collapse into each other: a published figure prints
  as published, a published zero prints as `0` and says it is one, a figure CDE
  withheld prints the words "withheld to protect privacy" with no digit anywhere,
  and a figure the state never published prints "no figure published". Withheld
  and missing cells are tested to contain no digit at all, so nothing on a page
  can be skimmed or scraped as a zero.
- Coverage published beside the data, row by row: every measure table carries how
  many active schools publish that figure, withhold it, and publish nothing,
  counted across all 10,534 active schools on the acquired build (9,860 publish a
  total enrollment figure, 674 publish none).
- English and Spanish as peers (`src/homeroom/i18n.py`): 120 keys per locale, 240
  strings, covering every reporting category, grade span, and subgroup family
  name. A missing key raises rather than falling back to English, and CDE's
  English-only school and district names are marked `lang="en"` on Spanish pages
  (WCAG 2.2 SC 3.1.2).
- The accessibility gate the README promised from the first page, inside
  `make verify` and merge-blocking in CI: `html-validate` (conformance, document,
  and a11y presets, with `scope` required on every table header) and `axe-core` in
  a headless jsdom DOM over the WCAG 2.0/2.1/2.2 A and AA rule sets plus
  best-practice, on every built page in both languages. Zero violations.
- The EN/ES parity gate the roadmap wired at M4 (`tests/test_i18n.py`): fails on a
  key present in one language and absent in the other, on a Spanish string left
  identical to its English original outside a short reviewed list, and on a
  translated template that lost a `{placeholder}`.
- Page checks that need no browser (`tests/test_pages.py`): one `h1`, no skipped
  heading level, a caption and scoped headers on every table, landmarks, unique
  ids, a focusable named region around every scrollable table, WCAG 2.2 contrast
  measured off both palettes in light and dark, and every number in a data cell
  checked against the values the pipeline actually counted.
- Every page states, in both languages, that teacher assignment data has not been
  acquired and that no figure about this school's teachers is shown. The page
  build takes only the D1 and D2 files, so it has no argument by which a D5 figure
  could arrive, and a test renders a profile that does carry parsed assignment
  outcomes to prove none of them reaches the markup.
- Deterministic pages: re-rendering is byte-identical, asserted in the test suite
  and again in CI by building the offline site twice and diffing the hashes.
- ADR 0001 records the page toolchain chosen at M4: stdlib Python rendering, typed
  per-locale string dictionaries, and node checkers that never ship in a page.
- Teacher assignment monitoring (D5), parser only: `src/homeroom/assignments.py`
  reads CDE's Teacher Assignment Monitoring Outcome files, published from the
  Commission on Teacher Credentialing's CalSAAS system, and carries five
  authorization outcomes per school as counts and published shares. Shares are
  copied, never divided out of counts; no outcome is ever recovered as the total
  minus its visible siblings. Profiles gain an optional `teacher_assignments`
  block joined on the 14-digit CDS code, artifacts gain the block and its
  coverage, and `--assignments` is a new optional input to `make data`.
  **No D5 file has been acquired**, so no D5 number about a real school is
  published anywhere. The parser was built against `fixtures/tamo.sample.txt`, a
  synthetic fixture, and the column contract is provisional until the real file
  is in hand; the drift errors are what make that safe, because a contract that
  turns out wrong stops the build instead of mis-reading a file.
- Each source now keeps its own school year. Assignment monitoring reports on a
  different cycle than Census Day enrollment, and a profile carries both years
  rather than putting one label over data from two calendars.
- Unacquired sources state their absence rather than rendering as zeros: with no
  D5 file, `coverage.json` records the source as unsupplied and no school carries
  an assignment block at all. A build cannot stamp an acquisition date nobody
  recorded, and the code constant and PROVENANCE.md are tested for agreement.
- School profiles (M3a): one `SchoolProfile` per active school joining directory
  identity, academic year, total enrollment, TK-12 grade spans, and subgroup
  enrollment for the four families the 2025-26 file carries (race/ethnicity,
  gender, English language acquisition, student groups), every value a `Measure`.
  All 33 observed ReportingCategory codes carry display names reviewed against
  CDE's file structure page; an unreviewed code fails the build.
- Deterministic artifacts and `make data` / `make data-offline`: `schools.json`
  and `coverage.json` in `data/out/` (gitignored), byte-identical across re-runs;
  a Measure serializes with a `value` key only when the state published a number.
  Coverage is first class: per-measure status counts, join gaps in both
  directions (698 school totals without a directory match, 674 active schools
  without enrollment rows, from the acquired files), PROVENANCE access dates, and
  an `is_fixture` flag.
- Suppression-fidelity guarantee, the rule owed before M3: published values are
  exactly CDE-published cells, and tests assert no artifact value can be a
  complement of a masked cell (`tests/test_profiles.py`,
  `tests/test_artifacts.py`).
- Fixture growth: a committed enrollment fixture exercising every rendering case
  (reported, suppressed, not reported, genuine zero, unjoined enrollment row,
  closed school, active school with no enrollment), so CI covers profiles and
  artifacts without any acquired data.

- CDS-code spine: parser for the CDE public school directory (`pubschls.txt`)
  with header-addressed columns and hard drift errors; verified against the live
  file acquired 2026-08-07 (18,396 rows, 10,534 active schools, 1,048 districts).
- Census Day enrollment: parser for the 2025-26 file (269,090 rows) with TK-12
  grade columns, aggregate-level separation, and CDS join to the spine (10,558
  school totals, 9,860 joined; school totals sum to the state's own row at
  5,731,260).
- Null-never-zero machinery: the `Measure` type distinguishes reported,
  suppressed, and not reported; a masked cell (CDE's `*`; 117,946 rows carry at
  least one in the 2025-26 enrollment file) cannot be read as a number; unknown
  sentinels fail the build; coverage is a first-class output.
- Provenance record (PROVENANCE.md) for sources D1-D6, including the
  browser-acquisition rule that keeps every file's origin and date on the record.
- Founding ADR 0000: the anti-ranking rule as an architectural decision.
- Conformance scaffold from `standards-init` (STANDARDS EXP-09), conformant with
  `STANDARDS/` `v1.0.1` at birth: CI with fully SHA-pinned actions, signed-tag
  release pipeline with SBOM and provenance, roadmap with metrics ledger,
  responsible-tech audit record, security policy, and citation metadata.

### Fixed
- Two D2 values recorded at M2 were corrected by M3a re-measurement: rows
  carrying at least one masked cell are 117,946 (first recorded as 88,207), and
  the state's own statewide row is 5,731,260 (5,692,490, first recorded as that
  row, is the joined-schools sum; the 698 unjoined school totals carry the
  38,770-student difference). The corrections are also marked in the ROADMAP
  metrics ledger.
- PROVENANCE now records the D2 acquisition itself (2025-26 file, acquired
  2026-08-07 as `cdenroll2526.txt`), which the coverage artifact stamps.
