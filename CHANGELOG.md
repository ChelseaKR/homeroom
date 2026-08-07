# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CDS-code spine: parser for the CDE public school directory (`pubschls.txt`)
  with header-addressed columns and hard drift errors; verified against the live
  file acquired 2026-08-07 (18,396 rows, 10,534 active schools, 1,048 districts).
- Census Day enrollment: parser for the 2025-26 file (269,090 rows) with TK-12
  grade columns, aggregate-level separation, and CDS join to the spine (10,558
  school totals, 9,860 joined; statewide sum reconciles at 5,692,490).
- Null-never-zero machinery: the `Measure` type distinguishes reported,
  suppressed, and not reported; a masked cell (CDE's `*`; 88,207 rows carry at
  least one in the 2025-26 enrollment file) cannot be read as a number; unknown
  sentinels fail the build; coverage is a first-class output.
- Provenance record (PROVENANCE.md) for sources D1-D6, including the
  browser-acquisition rule forced by CDE's bot challenge.
- Founding ADR 0000: the anti-ranking rule as an architectural decision.
- Conformance scaffold from `standards-init` (STANDARDS EXP-09), conformant with
  `STANDARDS/` `v1.0.1` at birth: CI with fully SHA-pinned actions, signed-tag
  release pipeline with SBOM and provenance, roadmap with metrics ledger,
  responsible-tech audit record, security policy, and citation metadata.
