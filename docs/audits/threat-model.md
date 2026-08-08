# Threat model — homeroom (data-pipeline / static-site archetype)

<!-- Methodology: RESPONSIBLE-TECH-FRAMEWORK.md §F; gates:
     SECURITY-AND-SUPPLY-CHAIN-STANDARD.md. Refresh on architecture change and
     at least annually. -->

- **Date:** 2026-08-08
- **Owner:** Chelsea Kelly-Reif
- **System diagram / data-flow reference:** a person downloads CDE public files in
  a browser into `data/raw/` (gitignored). A local CLI parses them, joins them on
  CDS codes, and writes deterministic JSON artifacts and static bilingual HTML.
  CI never reads `data/raw/`; it builds the same code paths over committed
  fixtures. No server, no database, no inbound network surface, no credentials in
  the pipeline, no personal data at any point: every input is already-published
  aggregate counts, masked at source by CDE.
- **ASVS target level:** L1. There is no authentication surface, no session, no
  stored PII, and no network listener. L2 would be required if Homeroom ever
  hosted the pages itself with any dynamic behaviour; it does not.

## Trust boundaries

1. **CDE's website → the maintainer's browser → `data/raw/`.** A file crosses from
   an outside publisher into the pipeline. Nothing authenticates it beyond TLS to
   cde.ca.gov and the maintainer's own attention.
2. **`data/raw/` → parsers.** Untrusted-by-default text crosses into code that
   assigns meaning to cells. This is where a wrong number would be born.
3. **GitHub Actions → the repository.** CI runs third-party code with a token.
4. **The repository → readers.** Published artifacts and pages cross out to people
   who will believe what they say. For this project that is the boundary that
   matters most, because the harm here is a confidently wrong figure, not a breach.

## STRIDE table

| STRIDE category | Threat (component + scenario) | Mitigation (control / gate) | Residual risk |
|---|---|---|---|
| Spoofing | A file that is not CDE's is placed in `data/raw/` (wrong download, man-in-the-middle, a copy edited by hand) and is parsed as authoritative | Access date, byte count and row count for every acquired file recorded in PROVENANCE.md and asserted in `tests/test_artifacts.py`; the parser refuses unreviewed columns, `AggregateLevel` values, `Charter` values and reporting-category codes, so a differently-shaped file stops the build rather than being read | RR-01 |
| Spoofing | A published page is mistaken for an official CDE or district product | Every page carries an unaffiliated notice in both languages, and `tests/test_pages.py` asserts it on every page in every locale | None |
| Tampering | A dependency or pinned action is replaced and alters published numbers | Every `uses:` pinned to a full 40-char SHA (zizmor in CI); `uv.lock` committed and installed with `--frozen`; pip-audit and npm audit at `--audit-level=high`; semgrep SAST; `make verify` byte-identical locally and in CI | RR-02 |
| Tampering | A source file is silently truncated or re-saved by a spreadsheet, changing cells | Row and byte counts recorded per file and checked; `parse_cell` hard-errors on any cell that is neither a number, the `*` mask, nor empty, so a mangled cell cannot become a guess | RR-01 |
| Repudiation | A published figure cannot be traced back to what produced it | Every artifact carries its source file names, access dates and `is_fixture`; fixture builds are stamped and say so on the page; artifacts are byte-identical across re-runs, so any output can be reproduced from its commit | None |
| Information disclosure | A masked small cell is reconstructed, re-identifying a student | `Measure` makes the numeric value of a non-reported cell unreadable at the type level; no published value is derived from complements, enforced by test; no arithmetic is performed across cells at all, and district and statewide context is read from CDE's own aggregate rows rather than summed from schools, so no Homeroom-computed total can leak a masked cell by subtraction | RR-03 |
| Information disclosure | Acquired raw files, which are large and unreviewed, are committed | `data/raw/` is gitignored; gitleaks runs in pre-commit and in CI; CI builds only from committed fixtures | None |
| Denial of service | Not applicable in the usual sense: no listener, no shared runtime. The degenerate case is a build that never finishes on a large file | Parsers stream row by row and hold only joined aggregates in memory; the full 269,090-row file parses in seconds | None |
| Elevation of privilege | A workflow gains write scope and pushes to the default branch or publishes | Least-privilege `GITHUB_TOKEN`, `permissions: {}` at workflow root with per-job grants; zizmor gate on permissions creep; no deploy workflow exists in this repo at all, so no workflow can publish anything | RR-04 |

## What this model deliberately treats as the primary risk

For most systems the worst outcome is unauthorised access. Here it is a number
that is wrong and looks right. A district figure fifteen times too small, taken
from the charter-only aggregate row instead of the `ALL` row, would pass every
security control in the table above: it is a real number, published by the state,
parsed from an authentic file, by unmodified code, in a reproducible build. The
controls that catch that class of failure are the drift refusals, the three-state
measure type, the coverage output, and the tests that assert every number on a
page was read or counted rather than computed. They are security controls in this
threat model even though they would not be in most.
