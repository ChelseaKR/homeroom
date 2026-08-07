# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
  browser-acquisition rule forced by CDE's bot challenge.
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
