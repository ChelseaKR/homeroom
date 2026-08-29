# Responsible-Tech Audits: homeroom

Instantiates `STANDARDS/RESPONSIBLE-TECH-FRAMEWORK.md`.
Last reviewed: 2026-08-21 (ADR 0003: AI-EVAL and Governance activated; A, C, D, F re-audited for the ask layer).

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
- AI-EVAL:         applies as of ADR 0003 (2026-08-21). An optional runtime question-answering layer (`src/homeroom/ask/`) carries a prompt, a retrieval corpus, and a model version. AI-assisted development is separately disclosed in the README (see AI-EVAL)
- I18N:            applies. EN/ES is a launch requirement; every user-visible string exists in both, parity gated (see B)

Every `N/A` line above carries a reason. A missing audit section is a defect;
a justified `N/A` is conformance (RESPONSIBLE-TECH-FRAMEWORK.md, "How to apply
this framework to a repo", step 2).

## A. Ethics

- What could go wrong: the pages get read as a rating anyway; the data is used to
  shame schools or as a real-estate signal; masked students surface as fake zeros.
  Worst plausible failure: a wrong or dishonestly-framed number about a real
  school, trusted by a family.
- Commitments: the anti-ranking rule (ADR 0002): no composite score, no letter
  grade, no ordering. Non-goals: not a school picker, not a real-estate feed, no
  third-party or commercial data ever (PROVENANCE.md rules). Suppressed data
  renders null, never zero.
- Enforcement:
  - AUTO (in place): the `Measure` type makes masked cells unreadable as numbers;
    `tests/test_measures.py` covers it; `parse_cell` hard-fails unknown sentinels.
  - AUTO (designed, not built): a static check that no code path aggregates
    measures across domains into a single number. Until it exists, the guard is
    review plus ADR 0002's PR rule.
  - REVIEW (done, day-one form): this consequence scan, dated above, with ADR 0002
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

### Subprocessor record (ADR 0003 ask service)

The ask service sends data to exactly one subprocessor, and only when a reader
opts in by submitting a question on an ask page. Recorded here before any
family-facing exposure, per the deployment runbook (`deploy/ask/README.md`).

- **Subprocessor:** Amazon Web Services — Amazon Bedrock (region `us-west-2`),
  running an Anthropic Claude model. The model actually deployed is named in
  `deploy/ask/README.md` and in every evaluation results file; on the record
  date it is `global.anthropic.claude-sonnet-4-6` (the account's Sonnet 5
  entitlement had not cleared; see `evals/results/`).
- **What is sent, per request:** the reader's question text, and the published
  evidence bundle for the one school the page is about (already-public CDE
  aggregate figures, the same ones on the page). Nothing else.
- **What is never sent:** no name, no account, no email, no address (IP or
  postal), no cookie, no identifier of the reader; the service has none of
  these to send. The rate-limit key is a salted hash that never leaves the
  service process.
- **What is never stored:** the service keeps no request body, writes no
  question to disk or logs (the HTTP access log is silenced;
  `tests/test_ask_http.py` asserts the question appears in no output), and
  returns nothing it did not compute for that request.
- **Retention at the subprocessor:** per AWS's Amazon Bedrock service terms,
  Bedrock does not store or log prompts and completions for on-demand
  inference and does not use them to train models, and Anthropic does not
  receive them. The request exists at AWS for the duration of processing.
- **Basis:** the reader's explicit opt-in action (typing and submitting a
  question on a page labeled as AI, unofficial, and answered from published
  data). No question is sent on page load; `tools/ask-optin.mjs` proves it.
- **Recorded:** 2026-08-22. **Owner sign-off:** approved by Chelsea Kelly-Reif,
  2026-08-22 (deployment authorization, relayed with the site origin
  decision).

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
  - Model card: the ask layer uses a third-party model (default `claude-sonnet-5`
    via the public `anthropic` SDK; the model actually used for any committed
    evaluation is named in `evals/results/`). No model is trained here, so the
    provider's model card applies; Homeroom's own record is the prompt version,
    the verifier rules, and the evaluation results. PROVENANCE.md serves as the
    dataset record; a fuller datasheet is considered at M5 when all six sources
    are joined.

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
  - REVIEW (not yet done, still open at M3, 2026-08-21): a keyboard and
    screen-reader walkthrough of a built page in each language, and a look at
    reflow on a narrow screen. No headless gate settles those, README.md says
    so, and this line stays open until the walkthrough happens. Accountable
    owner: Chelsea Kelly-Reif. Registered as RR-05 in
    `docs/audits/residual-risk-register.md`. The measure tables grew from five
    columns to seven at M4 when district and statewide context landed, which
    makes the reflow half of this walkthrough more pressing, not less: the
    tables scroll inside a focusable region rather than reflowing, and whether
    that is comfortable on a phone is exactly what a headless gate cannot say.
    M3 (chronic absenteeism) deliberately keeps the same seven-column shape for
    its four new tables rather than adding columns, precisely because this gate
    was already open when M3 was built; a design that widened the tables further
    while the walkthrough was still outstanding would have made the eventual
    finding harder to act on. `make pages` was re-run with M3 present in the
    fixture build (`fixtures/chronicabsenteeism.sample.txt`, all four cell states
    on one school) and stayed at zero violations across the same six rule sets,
    so the automated half of this gate is confirmed to extend cleanly to the new
    content; that is not a substitute for the walkthrough, and no session that
    built M3 has had a browser available to attempt even a keyboard-only pass —
    stated here rather than left implicit, so automated coverage is never read
    as a stand-in for the human step it explicitly is not.
  - AUTO (in place, ADR 0003, 2026-08-22): the ask page is the first page with
    an interactive control. It is a native form (labelled textarea, submit
    button), a `noscript` note, an `aria-live="polite"` answer region, and a
    focusable answer heading that receives focus when an answer lands, so a
    screen reader is told an answer arrived. html-validate and axe-core run
    over the ask pages in both languages in `make pages` (zero violations),
    and `tools/ask-optin.mjs` exercises the form in a DOM. What this adds to
    the open walkthrough (RR-05, issue #6): whether the answer region reads
    sensibly with a screen reader, whether the citation links are usable by
    keyboard in practice, and how the form reflows on a phone. None of that
    has been tried by a person; no session that built it had a browser or a
    screen reader. Issue #6 stays open and now covers the ask page too.

## F. Security

- Surface: a local pipeline over locally acquired public files, plus two hosted
  things. The static pages are served by GitHub Pages; the ask service (ADR
  0003) has been deployed since 2026-08-22 as an AWS Lambda behind an
  unauthenticated Function URL in `us-west-2`, which is a real inbound surface
  and is modelled in `docs/audits/threat-model.md` boundary 5. This bullet read
  "No hosted service ... no inbound network surface" until 2026-08-29, a week
  after the deploy. There are no secrets in the data. The other real exposures
  are the supply chain (actions, dependencies) and the by-hand acquisition step.
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

## AI-EVAL

Applies as of ADR 0003 (2026-08-21).

- Surface: a reader on a school's ask page submits a question in English or
  Spanish; the service structures it with a model, looks up that one school's
  published records, narrates the answer with the model, verifies every claim
  against the records and the committed corpus of CDE definitions, and returns
  the verified claims plus the count of withheld ones. No other school's data is
  ever in the request.
- What could go wrong: the model invents a number the state never published,
  renders a withheld cell as zero, compares figures that do not share a basis,
  or judges the school ("good", "better", a grade). Each is the project's
  founding failure in a new costume.
- Commitments: every claim cites a record or a corpus passage and is verified
  programmatically before display; unverifiable claims are withheld and counted,
  never shown; the refusal text for ranking and judgment questions is a fixed
  reviewed string the model does not write; a second guard withholds any model
  sentence carrying ranking or judgment language; withheld cells are narrated as
  not published; comparisons only on the page's own basis; Spanish narration
  labeled AI-translated and unreviewed; all output labeled AI-generated,
  unofficial, not a ranking, not a recommendation.
- Enforcement:
  - AUTO (being built under ADR 0003): the verifier in `homeroom.ask`, unit
    tested against hand-written claims in every failure class.
  - AUTO (being built): five committed evaluation suites in `evals/` with a
    harness: ranking refusal (adversarial, target zero), suppression fidelity
    (target zero values rendered for withheld cells), citation grounding,
    comparability, and question structuring including refusal-to-guess.
    Results carry provider, model, prompt version, commit, and date; a test
    rejects a results file without them; a suite not run says `not_run`.
    The harness exit code is the run's result, and the same check runs in CI
    over every committed results file, so a suite that regressed cannot be
    committed green (ADR 0004). Until 2026-08-26 neither was true: the harness
    returned 0 unconditionally, and the only assertion CI made about the numbers
    was the bookkeeping identity `passed + failed + errors == cases`, which is
    equally true of a file recording that every case failed. The recorded run
    was and remains 157 of 157, so nothing was masked; nothing would have
    noticed if something had been.
  - REVIEW (open, and overtaken): a person reads a sample of real answers in
    each language. Nobody has. This read "before any deployment"; the service
    was deployed on 2026-08-22 without it, so what was written as a gate in
    front of the service is now an unmet obligation against a running one. The
    commitment is not withdrawn to match what happened. Accountable owner:
    Chelsea Kelly-Reif. See RR-07 in `docs/audits/residual-risk-register.md`.

## Governance (AI repos only)

Activated by ADR 0003 (2026-08-21); this section was N/A before that date.

- AI risk register: the rows RR-07 through RR-09 in
  `docs/audits/residual-risk-register.md` (ungrounded claim reaching a reader;
  Spanish narration unreviewed; cost and availability of a third-party model).
- Impact assessment, day-one form: the population affected is families reading
  about real schools; the harm is a confidently wrong or judgmental sentence
  about a real school; the mitigations are structural (one school per request,
  verifier before display, fixed refusals) rather than prompt-level, and the
  measurements are the committed evaluation suites. Non-goals restated: not a
  school picker, no composite, no recommendation.
- EU AI Act classification decision, recorded here per the framework: the ask
  layer is a general-purpose-model-backed information tool that explains
  already-public aggregate statistics and explicitly refuses to evaluate
  schools or recommend enrollment. It makes no decision about any person and
  is not used for admission or placement; it is not a high-risk use under
  Annex III as read today. Transparency obligations (labeling AI output as
  such) are met on the page. This classification is the maintainer's reading
  and is rechecked on the cadence below.
- ISO 42001 SoA and a red-team report: not owed at prototype status; the
  ranking-refusal suite is the adversarial test that exists, and its cases are
  committed so anyone can extend it.

---

Last verified: 2026-08-07. Recheck cadence: quarterly, and immediately on any
revision to NIST AI RMF, ISO 42001, EU AI Act enforcement phases, WCAG, or OWASP
ASVS / LLM Top 10. Last verified for the AI sections: 2026-08-21.
