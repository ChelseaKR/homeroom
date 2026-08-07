# Roadmap — homeroom

## Problem

<!-- fill in: what problem this repo solves and for whom -->

## Product

<!-- fill in: the shape of the solution -->

## Architecture

<!-- fill in: the chosen stack, data source(s), and a one-line rationale each.
     Alternatives appear only as a short "rejected because" note
     (DOCUMENTATION-STANDARD §6.1). -->

## Quality targets

Rigor is cited to `STANDARDS/`, not restated. This repo's *values* only.

## Implementation plan

| Phase | Deliverable | Acceptance criteria |
|-------|-------------|----------------------|
| M0 | This scaffold conformant with `STANDARDS/` | `make verify` green; README conformance table has zero blank/unjustified rows |
| M1 | <!-- fill in --> | <!-- fill in --> |

## Metrics ledger

Exact shape per `STANDARDS/QUALITY-AND-METRICS-STANDARD.md` "Metrics ledger
(per repo)". Project-specific *values* go here; the *rigor* is cited to the
owning standard.

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| Branch coverage | >= 85% | `pytest --cov` in CI | AUTO | — |
| SHA-pinned `uses:` | 100% | `zizmor` / Scorecard Pinned-Deps >=9 | AUTO | — |
| Fixed HIGH+CRITICAL vulns (deps) | 0 | `pip-audit` in CI | AUTO | — |

## Scoping: N/A declarations

<!-- Any standard not applicable here is recorded with a reason, mirroring the
     README Standards Conformance table (never a silent skip). -->
