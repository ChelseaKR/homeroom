# Responsible-Tech Audits: homeroom

Instantiates `STANDARDS/RESPONSIBLE-TECH-FRAMEWORK.md`.
Last regenerated: 2026-08-07 (M4, first pages; sections B and E re-audited).

This record is honest about its age: the repo is one day old. Each section states
what is designed and enforced today versus what has not yet been audited. Nothing
below claims an audit that did not happen.

## Applicability

- A Ethics:        applies
- B Bias:          applies (the product exists to refuse a biased ranking practice; EN/ES is a first-class segment)
- C Privacy:       applies, narrowly (no PII collected; the duty is suppression fidelity for the students inside CDE's aggregates)
- D Transparency:  applies
- E Accessibility: applies as of M4; gates wired and merge-blocking (see E)
- F Security:      applies (threat model not yet written; see F)
- AI-EVAL:         N/A. No LLM, prompt, retrieval, or model surface. AI-assisted development is disclosed in the README; it is a build-time practice, not a product surface
- I18N:            applies. EN/ES is a launch requirement; every user-visible string exists in both, parity gated (see B)

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
  - AUTO (in place as of M4): EN/ES key parity per
    `STANDARDS/INTERNATIONALIZATION-STANDARD.md`, enforced over every catalog by
    `tests/test_i18n.py`, which also fails on a Spanish string left identical to
    its English original and on a translated template that lost a placeholder.
  - AUTO (in place as of M4): coverage is rendered beside every measure on every
    page, so a school whose data is sparse reads as sparsely published rather
    than as a school with nothing to show.
  - REVIEW (first pass done 2026-08-07, M4): page copy and measure framing were
    written and read against this risk. CDE's "Not Reported" and "Missing"
    category labels are expanded in both languages so neither reads as a
    judgment; a withheld figure is explained as protection for a student rather
    than as something the school failed to supply; and no page compares one
    school with another. Not yet reviewed by a Spanish-speaking reader who is
    not the author, which is what CONTRIBUTING.md asks for.

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
  - AUTO (in place, extended 2026-08-07 for D5): teacher assignment outcomes are
    the smallest cells the project has touched. A school with a handful of
    teachers can have most of that table withheld, so a published share is read
    from the file's own percent column and never divided out of counts, and no
    outcome is recovered as the total minus its visible siblings. Tests assert
    the complements of the fixture's masked outcomes appear nowhere, in the
    profiles and again in the artifact (`tests/test_assignments.py`,
    `tests/test_artifacts.py`).
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
  - AUTO (in place since D5a, 2026-08-07): a parser may be built ahead of its
    file, but a number may not. A source marked "awaiting acquisition" in
    PROVENANCE.md carries a null access date, publishes nothing, and is recorded
    in `coverage.json` as unsupplied rather than rendered as a field of zeros;
    the code constant and the provenance row are tested for agreement, so a
    build cannot stamp a date nobody recorded (`tests/test_artifacts.py`).
  - REVIEW (not yet audited): honesty-of-framing pass on page copy, due at M4.
    D5 adds a specific item to that pass: these outcomes describe which
    credential an assignment sat on, which is a fact about staffing and the
    state's own monitoring, and the page copy must not let a family read it as
    an evaluation of a teacher.
  - Model card: N/A, no model. PROVENANCE.md serves as the dataset record; a
    fuller datasheet is considered at M5 when all six sources are joined.

## E. Accessibility

Applies as of M4 (2026-08-07). The pages exist, so the deferral has ended.

- What could go wrong: the family this is written for cannot read it. A screen
  reader announces a withheld figure as a bare number with no row header; a table
  scrolls sideways on a phone with no way to reach it from a keyboard; a cell's
  state is carried by colour alone, so the difference between a withheld figure
  and a zero is invisible to a colour-blind reader; the English page is good and
  the Spanish page is an afterthought.
- Commitments: WCAG 2.2 AA on every page in both languages, semantic HTML with
  real landmarks and real table headers, no reliance on colour alone, no script
  and no external asset, and equal capability in both languages.
- Enforcement:
  - AUTO (in place): `make pages`, inside `make verify` and merge-blocking in CI,
    builds the pages from committed fixtures and runs `html-validate` (with
    `scope` required on every table header) and `axe-core` in a headless jsdom DOM
    over the WCAG 2.0/2.1/2.2 A and AA rule sets plus best-practice, on every page
    in both languages. Zero violations at M4.
  - AUTO (in place): `tests/test_pages.py` checks what axe cannot in a DOM that
    paints nothing: colour contrast for every pair the pages use, in light and in
    dark, and the document structure a screen reader depends on. It also asserts
    each cell state carries its own words, so colour is never the only signal
    (SC 1.4.1).
  - REVIEW (not yet done): a keyboard and screen-reader walkthrough of a built
    page in each language, and a look at reflow on a narrow screen. No headless
    gate settles those, README.md says so, and this line stays open until the
    walkthrough happens. Accountable owner: Chelsea Kelly-Reif. Registered as
    RR-05 in `docs/audits/residual-risk-register.md`. The measure tables grew
    from five columns to seven at M4 when district and statewide context landed,
    which makes the reflow half of this walkthrough more pressing, not less: the
    tables scroll inside a focusable region rather than reflowing, and whether
    that is comfortable on a phone is exactly what a headless gate cannot say.

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
  - REVIEW (done 2026-08-08): STRIDE threat model written to
    `docs/audits/threat-model.md` and the residual-risk register to
    `docs/audits/residual-risk-register.md`, both owed before the first tagged
    release. The threat model names the primary risk for this archetype as a
    figure that is wrong and looks right rather than unauthorised access, and
    treats the drift refusals and the three-state measure type as security
    controls on that basis. Six residual risks carry an owner and a decision;
    RR-05 and RR-06 are tracked rather than accepted, and RR-04 closed
    2026-08-17.
  - REVIEW (done 2026-08-17): `.github/signing-allowed-signers` now carries the
    maintainer's signing principal and public key, verified against the key
    registered on the maintainer's GitHub account before being committed, and
    the unread duplicate `.github/allowed_signers` is removed so the trust root
    has one home. The tag signature itself still needs the maintainer's private
    key, which no tooling holds (RR-04, closed).

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
