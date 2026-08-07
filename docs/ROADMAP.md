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
- Source files are locally acquired inputs in `data/raw/`: CDE bot-challenges
  non-browser clients, so acquisition is a documented browser step per file
  (PROVENANCE.md). Rejected: automated fetch, which fights the bot wall and hides
  provenance.
- CI never touches the network; committed fixtures exercise every parsing and
  rendering case, including suppression.
- The `Measure` type carries three statuses (reported, suppressed, not reported)
  and makes masked cells unreadable as numbers (ADR 0000).
- Rendering target is static bilingual pages; the page toolchain is chosen at M4,
  with accessibility and i18n gates wired in the same milestone.

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
| M3 | D3 chronic absenteeism | First masked-heavy measure end to end; every masked cell null, counted in coverage output |
| M3 | Suppression showcase | A committed artifact demonstrating null-never-zero rendering: masked cells shown as "not published", coverage stats published beside the data |
| M4 | First bilingual school page | One real school rendered EN/ES from acquired data; a11y and EN/ES parity gates wired from this milestone |
| M5 | D4-D6 | Dashboard indicators, teacher assignment (CalSAAS), and per-pupil spending joined where published |

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
| Rows carrying at least one `*` masked cell | 88,207 | D2 |
| Statewide enrollment (state's own row) | 5,692,490 | D2 |

The join gap (10,558 school totals vs 9,860 joined) is a finding, not a defect to
hide: it is published as coverage, and understanding it is part of M3.

## Scoping: N/A declarations

Mirrors the README Standards Conformance table; never a silent skip.

- Accessibility: N/A at day one (no HTML surface); applies from M4, gates wired
  before the first page ships.
- Internationalization: applies. EN/ES is a launch requirement for the pages; no
  user-facing strings exist yet, and the parity gate is wired at M4.
- AI Evaluation: N/A. No LLM, prompt, retrieval, or model-version surface.
  AI-assisted development is disclosed in the README; it is a build-time practice,
  not a product surface.
- Observability Tiers A/B: N/A, no hosted service or frontend (Tier C declared
  above).
