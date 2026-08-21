# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- A cell that is not a published number could become one. `parse_cell` handed
  anything that was not `*` or empty straight to `float`, and `float` accepts a
  great deal a data file never means as a number. `nan` is the one that matters:
  it is how an export writes a value it does not have, and it was classified as
  *reported*, so it rendered on a school page inside `<span class="num">`, in a
  cell whose own legend says "the state published this figure", styled and
  captioned exactly like a real count. The page-level gate that checks every
  number in a data cell was counted did not catch it, because `nan` has no digits
  in it. `1_0` read as ten through PEP 515 digit separators, `1e3` as a thousand,
  `1,23` as one hundred and twenty-three once the commas were stripped, and
  fullwidth or Arabic-Indic digits as numbers nobody typed. `parse_cell` now
  checks the cell against `PUBLISHED_NUMBER`, an explicit statement of the shape
  CDE publishes, before converting, and refuses everything else as the drift it
  is. Measured against the acquired 2025-26 D2 file: no change to any real figure
  (10,534 profiles, 182,362 / 0 / 80,988 subgroup measures, join gaps 698 and 674,
  all unchanged).
- A figure too large to hold became infinity in silence. A digit run long enough
  to overflow a float converted without complaint, and `inf` reached the page the
  same way `nan` did. `parse_cell` now refuses a value that is not finite.
- `schools.json` could stop being JSON. A `nan` or overflowed cell serialized as
  the bare literal `NaN` or `Infinity`, which RFC 8259 does not have: Python
  writes and reads both without complaint, so the project's own round trip could
  not see it, while a browser's `JSON.parse` and a Go or Rust decoder reject the
  whole document over one of them, taking all 10,534 schools down with one bad
  cell. `tests/test_artifacts.py` now reads the artifacts back through
  `parse_constant`, which fires on exactly those tokens, so the gate holds for any
  future path into the artifact and not only for this one.
- Two measured figures in the docs were wrong, and are corrected in place in the
  `docs/ROADMAP.md` ledger the way its earlier corrections are. Districts were
  recorded as 1,048, which is the count of distinct district *names*: ten names
  cover two districts each and "Jefferson Elementary" covers three, so counting by
  name loses eleven, and the count by CDS code, the only key this project joins
  on, is 1,059. And Birch Lane's page was recorded as "30 numbers, 6 of them
  genuine published zeros" when the 6 are beside the 30 rather than among them:
  the page publishes 36 of its 40 figures. The second is this project's own rule
  read backwards, since a published zero is a figure the state published and is
  the reason the four cell states exist.
- **The lockfile gate did not gate.** `make sync`, the first stage of `make verify`
  and therefore of CI, ran `uv sync --frozen`. That flag installs from `uv.lock`
  without reading `pyproject.toml`, so by construction it cannot notice the two
  disagree, and it exits 0 on a drifted lock: a dependency added or bumped in
  `pyproject.toml` without relocking would have passed the full gate. Now
  `uv sync --locked`, which re-resolves and exits 1 on drift, with the reasoning
  in a comment beside the line. The release job in `.github/workflows/release.yml`
  gets the same substitution.
- **Two ADRs were both numbered 0000**, making a citation to "ADR 0000" ambiguous.
  `0000-record-architecture-decisions.md` keeps the seed number by convention;
  refuse-to-rank-schools moves to `0002-refuse-to-rank-schools.md` with its
  heading updated. No accepted ADR was renumbered out from under an existing
  citation, and nothing referenced the moved file by number.

### Added
- **M3: chronic absenteeism (D3), the first masked-heavy measure, end to end**
  (`src/homeroom/absenteeism.py`, new). The 2024-25 file (`chronicabsenteeism25.txt`,
  33,781,100 bytes, 341,490 rows) was acquired 2026-08-21 and its header read
  directly: identity columns are spaced (`Academic Year`, `Charter School`, ...)
  while the three measure columns are concatenated
  (`ChronicAbsenteeismEligibleCumulativeEnrollment`, `ChronicAbsenteeismCount`,
  `ChronicAbsenteeismRate`), and `Charter School`/`DASS` are two independent
  `All`/`Yes`/`No` dimensions rather than D2's one. Joins the D1 spine and D2's
  academic year stays separate from D3's own (`homeroom.profiles`); district and
  statewide context reads CDE's own `Charter School = All, DASS = All` rows,
  never a sum over schools (`homeroom.context.load_absenteeism_context`, mirroring
  `load_context`'s existing rule for D2). Renders on every school page as a total
  rate plus race/ethnicity, gender, and student-group tables, each in the same
  four states and the same seven-column shape as every other measure table
  (`homeroom.render._absenteeism_section`); wired into `make data` and
  `make site`'s default invocation. Measured against the acquired files: total
  rate reported for 9,718 of 10,534 active schools, withheld for 83, not
  published for 733; the most-withheld subgroup (American Indian or Alaska
  Native) is withheld for 95.4% of the schools that have any row for it.
  `docs/SUPPRESSION-SHOWCASE.md` is the committed artifact walking four real rows,
  one of each cell state, from the source file to the rendered markup.
- **D5's provisional column contract, checked against the real file and rewritten
  to match it** (issue #5). The 2023-24 Teacher Assignment Monitoring Outcome
  file (`tamo2324.txt`, 234,206,408 bytes, 1,528,796 rows) was acquired
  2026-08-21. Every part of the provisional contract disagreed with it: real
  column names are spaced and some carry CDE's own typo (`Unknown FTE FTE
  (percent)`, read verbatim); there are seven outcomes, not five (`incomplete`
  and `na` were missing); values are fractional FTE, not integer counts; and the
  file's grain is one row per (school, charter, DASS, grade span, teacher
  experience level, teacher credential level, subject area) -- up to 150 rows per
  school, not one -- of which exactly one row per school (experience = credential
  = `ALL`, subject = `TA`) is CDE's own already-aggregated whole-school total,
  verified present for all 10,064 schools in the file. Scanning every numeric
  cell in the file found zero masked cells anywhere, unlike D2 and D3.
  `src/homeroom/assignments.py` and `fixtures/tamo.sample.txt` are rewritten to
  match; acquired is still not published, and `make data`/`make site`'s default
  invocation are unchanged.
- `.github/dependabot.yml`: weekly `uv`, `npm` and `github-actions` updates,
  keeping the pinned Python set, the Node page-gate toolchain, and the
  SHA-pinned action set current at a weekly PR volume one maintainer can
  review. The CodeQL action set is grouped into one PR because init, analyze,
  autobuild and upload-sarif must run the same version.
- Four standards missing from the README conformance table (Performance, AI
  Development Measurement, Incident Response, Data Governance) are now
  declared **Applies**, each naming what exists and what does not.

## [0.1.0] - 2026-08-18

First tagged release: the CDS-code directory spine, Census Day enrollment, the
teacher-assignment parser (no D5 file acquired), one school profile per active
school as deterministic JSON artifacts, and static bilingual school pages built
from those profiles. Nothing is deployed or hosted; pages render locally from
files a person downloaded from CDE's public data pages.

### Added
- `.github/dependabot.yml`: weekly `uv`, `npm` and `github-actions` updates.
  `pip-audit` in `make verify` catches a dependency that is already
  known-vulnerable; this covers the other half, keeping the pinned set current.
  The CodeQL action set is grouped into one PR because init, analyze, autobuild
  and upload-sarif must always run the same version.
- Four standards that the README conformance table had left undeclared are now
  declared with their current state: Performance, AI Development Measurement,
  Incident Response, and Data Governance. Each row says what exists and what
  does not, rather than asserting a posture the repo has not built.
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
- English and Spanish as peers (`src/homeroom/i18n.py`): 157 keys per locale, 314
  strings total (122 keys at M4, before D3 added its own 25-code category catalog
  and 10 interface strings at M3), covering every reporting category, grade span,
  and subgroup family name. A missing key raises rather than falling back to
  English, and CDE's English-only school and district names are marked
  `lang="en"` on Spanish pages (WCAG 2.2 SC 3.1.2).
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
- **The release trust root pointed at a file nothing read.** The maintainer's
  signing key was committed 2026-08-07 to `.github/allowed_signers`, while
  `release.yml` reads `.github/signing-allowed-signers`, which still held the
  scaffold placeholder, so no tag could ever have verified. The signing
  principal and public key, checked against the key registered on the
  maintainer's GitHub account, now live in the file the workflow reads,
  restricted to the `git` signature namespace, and the unread duplicate file is
  removed so the trust root has one home (RR-04, closed).
- **The hosted-ruleset binding check could never run.** The release workflow
  called `check_release_ruleset.py` with `--tag "${TAG}"-message`, a mangled
  spelling of `--tag "${TAG}" --verify-tag-message`: argparse accepted the
  garbage tag value, no message operation was selected, and the step passed on
  ruleset parity alone while the signed-tag-message binding it exists to
  enforce silently never executed. The flag is now spelled correctly, so a
  release tag must carry the exact message binding the hosted tag ruleset's id
  and `updated_at` (`--print-tag-message` prints it for the tag command).
- Two D2 values recorded at M2 were corrected by M3a re-measurement: rows
  carrying at least one masked cell are 117,946 (first recorded as 88,207), and
  the state's own statewide row is 5,731,260 (5,692,490, first recorded as that
  row, is the joined-schools sum; the 698 unjoined school totals carry the
  38,770-student difference). The corrections are also marked in the ROADMAP
  metrics ledger.
- PROVENANCE now records the D2 acquisition itself (2025-26 file, acquired
  2026-08-07 as `cdenroll2526.txt`), which the coverage artifact stamps.
- **The release workflow could never extract its own release notes.** The
  CHANGELOG section pattern in `.github/workflows/release.yml` is built in an
  f-string, where `{4}` is a replacement field rather than a regex quantifier,
  so `\d{4}-\d{2}-\d{2}` had silently become `\d4-\d2-\d2` and matched no date
  ever written. Every release would have aborted at "matching dated CHANGELOG
  section is missing". The braces are doubled and the reason is in a comment
  beside the line. It fails closed, so nothing was ever published wrongly; the
  workflow simply could not run to completion.
- **A test that could not fail.** The D5 acquisition-date test compared the
  access date in `coverage.json` against `ASSIGNMENTS_ACCESS_DATE`, the constant
  that writes that field, so the assertion could not fail whatever either one
  said: setting the constant to a date PROVENANCE.md does not record still
  passed. The expectation is now read from PROVENANCE.md, which is where a
  person records an acquisition, so that mutation fails.
- **The catalog figures in the prose were two short.** README, CHANGELOG and the
  ROADMAP ledger all still gave the M4 figure of 120; the district and statewide
  columns added two interface keys and none of the three was updated.
  `tests/test_i18n.py` now reads the true count (stated correctly, and kept
  current, everywhere else in these three documents) out of all three and
  compares it to the catalogs, failing when a document drops the claim as well
  as when it states it wrongly.
- The ROADMAP row "measure cells per page" gave 40, which is the number of
  measures; each is rendered in three columns, so the row now says so.
- **"No script, no external asset, no tracking" had no gate.** Neither
  html-validate nor axe-core has an opinion about it: a page that loads a CDN
  font or a tracking pixel is conformant and accessible. `tests/test_pages.py`
  now checks every built page for script and subresource elements, fetching
  attributes, inline event handlers, `@import`, `url(`, and `javascript:`, and
  requires the stylesheet to still be present and inline so the check cannot be
  met by a page that stopped rendering.
- A CDS code the enrollment parser cannot assemble into 14 digits raises, and
  now has a test; the guard was previously the only uncovered branch in that
  module. Removed `context._empty`, which no caller ever used.
