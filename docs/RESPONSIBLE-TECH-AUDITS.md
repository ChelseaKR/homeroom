# Responsible-Tech Audits: homeroom

Instantiates `STANDARDS/RESPONSIBLE-TECH-FRAMEWORK.md`.
Last regenerated: 2026-08-07 (day one).

This record is honest about its age: the repo is one day old. Each section states
what is designed and enforced today versus what has not yet been audited. Nothing
below claims an audit that did not happen.

## Applicability

- A Ethics:        applies
- B Bias:          applies (the product exists to refuse a biased ranking practice; EN/ES is a first-class segment)
- C Privacy:       applies, narrowly (no PII collected; the duty is suppression fidelity for the students inside CDE's aggregates)
- D Transparency:  applies
- E Accessibility: N/A at day one (no HTML surface); applies from the first school page (ROADMAP M4), gates wired before it ships
- F Security:      applies (threat model not yet written; see F)
- AI-EVAL:         N/A. No LLM, prompt, retrieval, or model surface. AI-assisted development is disclosed in the README; it is a build-time practice, not a product surface
- I18N:            applies from M4. EN/ES is a launch requirement; no user-facing strings exist yet

Every `N/A` line above carries a reason. A missing audit section is a defect;
a justified `N/A` is conformance (RESPONSIBLE-TECH-FRAMEWORK.md, "How to apply
this framework to a repo", step 2).

## A. Ethics

- What could go wrong: the pages get read as a rating anyway; the data is used to
  shame schools or as a real-estate signal; masked students surface as fake zeros.
  Worst plausible failure: a wrong or dishonestly-framed number about a real
  school, trusted by a family.
- Commitments: the anti-ranking rule (ADR 0000): no composite score, no letter
  grade, no ordering. Non-goals: not a school picker, not a real-estate feed, no
  third-party or commercial data ever (PROVENANCE.md rules). Suppressed data
  renders null, never zero.
- Enforcement:
  - AUTO (in place): the `Measure` type makes masked cells unreadable as numbers;
    `tests/test_measures.py` covers it; `parse_cell` hard-fails unknown sentinels.
  - AUTO (designed, not built): a static check that no code path aggregates
    measures across domains into a single number. Until it exists, the guard is
    review plus ADR 0000's PR rule.
  - REVIEW (done, day-one form): this consequence scan, dated above, with ADR 0000
    as the committed non-goals statement. Accountable owner: Chelsea Kelly-Reif.

## B. Bias

- What could go wrong: composite scores reproduce demographic and property-wealth
  bias; that is the harm this project refuses at the architecture level (ADR
  0000). Subtler residual risks: coverage differs across communities, so pages for
  some schools look emptier than others; English pages could quietly become better
  than Spanish pages.
- Commitments: no composite scoring; coverage is a published first-class output so
  absence is visible rather than silently unequal; EN/ES parity of capability from
  the first page; never infer attributes about students or families; demographic
  breakdowns appear only as CDE publishes them, masks intact.
- Enforcement:
  - AUTO (in place): `coverage()` counts every measure status; masked cells cannot
    leak into computed values.
  - AUTO (from M4): EN/ES key parity per `STANDARDS/INTERNATIONALIZATION-STANDARD.md`.
  - REVIEW (not yet audited): representational-harm pass on page copy and measure
    framing, due at M4 when copy exists. No rendering exists yet to audit.

## C. Privacy

- Data inventory: CDE public aggregate files only, listed with acquisition rules
  in PROVENANCE.md. No PII is collected or stored; no accounts, no tracking, no
  telemetry. The people at risk are the students inside the aggregates, protected
  upstream by CDE's small-cell suppression.
- What could go wrong: undermining that suppression, either by rendering a mask as
  a value or by re-deriving a masked cell (for example, subtracting published
  grade counts from a published total). Joining third-party data could sharpen
  re-identification; PROVENANCE.md forbids third-party data outright.
- Commitments: a masked cell is null in every artifact, never zero, never
  interpolated, never back-calculated. No data leaves the local pipeline.
- Enforcement:
  - AUTO (in place): `Measure.number()` raises on suppressed/not-reported cells;
    parser tests; gitleaks in pre-commit and CI.
  - AUTO (in place, closed 2026-08-07 at M3a): the derived-value rule owed
    before M3 is now written down and enforced. Profile assembly copies
    CDE-published cells and never computes one (`src/homeroom/profiles.py`
    module contract); tests assert no profile or artifact value equals the
    complement of a masked cell and that every reported value appears verbatim
    in the source file (`tests/test_profiles.py`, `tests/test_artifacts.py`).
  - A formal DPIA artifact is not maintained: the repo processes no personal data.
    PROVENANCE.md is the data inventory. This becomes wrong, and a DPIA becomes
    owed, if any non-public or individual-level data ever enters scope.

## D. Transparency

- Commitments: every figure traces to a named public file with an access date
  (PROVENANCE.md); coverage is published beside the data; "not reported" and
  "reported as zero" stay visually distinct; non-affiliation with the State of
  California is stated in the README; AI-assisted development is disclosed in the
  README.
- Enforcement:
  - AUTO (in place): drift errors stop the build when upstream layouts change, so
    a page can never silently render from a file the parser no longer understands.
  - AUTO (in place since M3a, 2026-08-07): the pipeline stamps PROVENANCE.md
    acquisition dates into `coverage.json`, with an `is_fixture` flag and null
    dates for fixture builds; tested for sync with the provenance record
    (`tests/test_artifacts.py`).
  - REVIEW (not yet audited): honesty-of-framing pass on page copy, due at M4.
  - Model card: N/A, no model. PROVENANCE.md serves as the dataset record; a
    fuller datasheet is considered at M5 when all six sources are joined.

## E. Accessibility

N/A at day one: there is no HTML or UI surface. This is a deferral, not an
exemption. The product's whole point is family-readable pages, so from M4 the
audit applies in full: axe/Lighthouse gates wired before the first page ships,
manual keyboard and screen-reader walkthroughs per release, in both languages.
An inaccessible or English-only-accessible page would fail the project's own
thesis.

## F. Security

- Surface: a local pipeline over locally acquired public files. No hosted
  service, no secrets in the data, no inbound network surface. The real exposure
  is the supply chain (actions, dependencies) and the by-hand acquisition step.
- What could go wrong: a compromised action or dependency alters published
  numbers or exfiltrates credentials from CI; a tampered or mis-saved source file
  changes what pages say; workflow permissions creep.
- Enforcement:
  - AUTO (in place at scaffold): least-privilege `GITHUB_TOKEN`; every `uses:`
    pinned to a full 40-char SHA (completed 2026-08-07); gitleaks in pre-commit
    and CI; semgrep SAST; pip-audit; `make verify` identical locally and in CI.
  - AUTO (release path, in place): signed-tag verification against a committed
    allowed-signers file, reproducible double build with byte comparison,
    CycloneDX SBOM validated against schema, cosign keyless signing, provenance
    attestation, and byte-recheck of published assets (`.github/workflows/release.yml`).
  - REVIEW (open, not yet audited): STRIDE threat model and residual-risk
    register (`STANDARDS/templates/stride-threat-model.md`,
    `residual-risk-register.md`) are not yet written; both are owed before the
    first tagged release. `.github/signing-allowed-signers` still holds the
    scaffold placeholder and must carry the maintainer's real signing key before
    the first release; release.yml fails closed until it does.

## Governance (AI repos only)

N/A: no AI system ships in this repo, so no AI risk register, impact assessment,
ISO 42001 SoA, or red-team report is owed. EU AI Act classification decision,
recorded here per the framework: homeroom contains no AI feature; there is
nothing to classify. This section activates if an AI surface is ever added, and
the anti-ranking rule (ADR 0000) would bind any such feature first.

---

Last verified: 2026-08-07. Recheck cadence: quarterly, and immediately on any
revision to NIST AI RMF, ISO 42001, EU AI Act enforcement phases, WCAG, or OWASP
ASVS / LLM Top 10.
