# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **`make verify` was green on trees CI rejects** (2026-08-28). `AGENTS.md` said
  "`make verify` is the gate, byte-for-byte identical to CI" and the Makefile
  said the two "MUST stay byte-for-byte identical". CI ran three jobs and
  `make verify` covered one. `secret-scan`, `sast`, and the twice-build
  determinism check existed only as steps inside
  `.github/workflows/ci.yml`, with no target to run them by, so nobody could
  run the gate the documentation described.
  - Every CI stage is now a `make` target, `verify` reaches all of them, and
    every step in `ci.yml` invokes one. `tests/test_ci_parity.py` checks those
    three facts by reading the workflow, so a stage added to CI as inline
    script fails the build that adds it. Demonstrated failing by adding a
    CI-only `run: echo` step, and again by removing `sast` from `verify`'s
    prerequisites.
  - **The determinism check could pass having hashed nothing.** It wrote two
    `find | xargs shasum` files and diffed them; over an empty directory that
    is two empty files and a successful diff. Confirmed by running the old
    command pair against an empty tree: exit 0. The target now fails if the
    first hash file is empty, and prints how many files it compared.
  - **The secret scan could not see an uncommitted key.** `gitleaks` in history
    mode reads commits, not the working tree. Confirmed on this repository with
    a high-entropy GitHub token in an untracked file: history mode reported
    "68 commits scanned, no leaks found" and exited 0. `make secret-scan` keeps
    that pass and adds a working-tree pass, which exits 1 on the same file. The
    working-tree pass is scoped to what `git ls-files -co --exclude-standard`
    lists, which is where an uncommitted key lives and which keeps the scan off
    `node_modules/` and `.venv/`: 1.3 MB in 0.3 s rather than 577 MB in 72 s.
    The two passes are two commands with two exit statuses, not a `for` loop,
    which would report only its last iteration's.
  - **Semgrep silently skipped every test.** Its built-in ignore list drops
    `tests/`, so a job whose stated scope was the whole repository read 30 of
    55 tracked Python files and said so only as "Files matching .semgrepignore
    patterns: 25". A repository-root `.semgrepignore` replaces that list;
    scope is now 55 of 55, still 0 findings. This project's tests are gates,
    not scratch code.
  - **zizmor was cited as a control in three documents and existed nowhere.**
    `docs/audits/threat-model.md` named it twice, once for `uses:` pinning and
    once as the "gate on permissions creep", and `docs/ROADMAP.md`'s metrics
    ledger named it as the measurement for 100% SHA-pinned actions. It was not
    in the Makefile, the workflows, or the dependencies. It runs now, pinned,
    in `make workflow-audit`.
    - Its default configuration could not have backed the claim it was cited
      for: `unpinned-uses` accepts a tag by default, so `actions/setup-node@v7`
      passes it. Verified by unpinning that action and watching the default
      configuration report clean. `.github/zizmor.yml` sets the `hash-pin`
      policy; with it, the same unpinned action is a High finding and the gate
      exits 14.
    - One finding is ignored: `dangerous-triggers` on `pages.yml`'s
      `workflow_run`. The reasoning is written at the line it applies to, and
      it is the only suppression.

### Changed
- `RR-02`'s mitigation text said dependencies are installed `--frozen`; the
  Makefile has run `--locked` since 2026-08-26. `docs/audits/threat-model.md`
  carried the same stale word and is corrected too.
- The README's Accessibility conformance row named only the automated half of
  the gate. It now names the open review half -- the keyboard and screen-reader
  walkthrough and the 320px reflow check -- and links issue #6 and RR-05, which
  is what `DOC-13` asks of a declared conformance gap. The row previously read
  as fully satisfied. The Security & Supply-Chain row now says what actually
  runs.
- **The project's most important claim cited the wrong document** (2026-08-28,
  issue #35). The anti-ranking and suppression-fidelity rule was cited as
  "ADR 0000" in eight places across code, docs and tests. ADR 0000 is
  `0000-record-architecture-decisions.md`, the MADR process ADR: it says
  nothing about ranking or suppression. The decision is
  `0002-refuse-to-rank-schools.md`, `Status: Accepted`, dated 2026-08-07. The
  numbering is a leftover from the release that split the two ADRs that were
  both numbered 0000; the file moved and these citations did not.
  - Fixed at all eight sites: `src/homeroom/render.py`,
    `src/homeroom/absenteeism.py`, `src/homeroom/profiles.py`,
    `docs/ROADMAP.md` (two), `docs/RESPONSIBLE-TECH-AUDITS.md` (three). The
    issue listed seven; `tests/test_profiles.py` was the eighth and is fixed
    too. `src/homeroom/ask/guards.py` and `src/homeroom/ask/evalharness.py`
    already cited 0002 correctly, which is what confirms 0002 is the target.
  - CHANGELOG entries that mention the old number are left alone. Two of them
    are *about* the renumbering, and rewriting history to look tidy would
    falsify the record this project keeps citations for.
  - **ADR 0000 shipped with `Date: TODO - set to today's date at generation
    time`**, an unfilled generator placeholder, for three weeks. Set to
    2026-08-07, the date the file was added (commit `4cd542b`), which is the
    date the other day-one ADRs carry.
  - `tests/test_adr_citations.py` (new) keeps the trail honest, because fixing
    eight strings by hand is not a control. It checks that every ADR cited
    anywhere in `src/`, `tests/`, `docs/`, `evals/` and `tools/` resolves to a
    file that exists; that no ADR carries a placeholder where its date should
    be; that the Accepted decision ADRs are still Accepted; and that the
    process meta-ADR is never cited as the reason for a behaviour. Each of the
    three was run against a deliberately reintroduced fault (an `ADR 0000`
    citation, an `ADR 0099` citation, the restored `TODO` date) and observed
    failing before being observed passing. A first test asserts the ADR series
    and the scanned file list are both non-empty, so a renamed directory
    reports zero files instead of passing over nothing.
- **The verifier licensed a number by proximity, not by the fact it came from**
  (2026-08-28, issue #34, ADR 0003 point 4). `_allowed_numbers` in
  `src/homeroom/ask/verifier.py` built one flat set of "numbers seen anywhere
  near this record" and then asked only whether each number in a claim appeared
  somewhere in it. Into that set went the record's statewide coverage tally
  (`{"reported": N, "suppressed": M, "not_reported": K}`, a count of how many
  *other* schools' cells landed in each status), the size of the build, and the
  digits of the school's grade span. None of those is the school's own
  published figure, and ADR 0003 promises that "every number in the sentence is
  a number one of its cited records actually publishes".
  - The collision is not hypothetical. In the committed fixture, Example
    Elementary's chronic absenteeism rate is 12.5% and its coverage tally is
    `{"not_reported": 1, "reported": 1, "suppressed": 1}`, so the sentence
    "the rate for all students was 1%" verified clean and was shown to the
    reader as a cited figure about that school. The repro in issue #34 was
    executed against the fixture bundle and reproduced exactly; it now returns
    the claim withheld with reason `unverifiable_number`.
  - The suppression invariant was never at risk: `_check_absence` is a separate
    check and a withheld cell is still never narrated as a value. What could be
    swapped was a *reported* cell's own number.
  - Numbers are now licensed by the kind of claim making them.
    `CONTEXT_CLAIM_KINDS` holds the one kind whose subject is context about the
    data rather than a cell's value: `note`, already described to the model as
    "context about the data (which year, why a figure is withheld)". A `note`
    may still state a coverage tally, the build size, and the grade span. A
    `figure` or a `comparison` gets only what its own cited cells publish, plus
    years, measure-label digits, and the numbers inside a verified quote.
  - The same construction was duplicated in the independent eval scorer,
    `_cell_numbers` in `src/homeroom/ask/evalharness.py`, so the `citation` and
    `comparability` suites shared the blind spot and could not have caught it.
    That scorer exists to disagree with the service; it is narrowed the same
    way and by its own code path.
  - Both guards are demonstrated failing before they are demonstrated passing.
    `test_a_figure_may_not_state_the_coverage_tally_as_the_school_own_value`
    and `test_a_figure_may_not_borrow_the_build_size_as_the_school_own_value`
    fail against the old flat set; `test_a_note_may_still_state_the_coverage_tally_it_cites`
    and `test_a_figure_still_shows_the_value_its_own_cell_publishes` prove the
    narrowing did not withhold the sentences it exists to protect.
  - The committed results files still pass the gate `make verify` holds them
    to. They could not be re-scored under the narrowed rule, and this says so
    rather than implying they were: a results file records each shown claim's
    *text* but not its kind or its citations, and re-running the suites needs
    the acquired files in `data/raw/`, which are never in git. So the recorded
    157-case run is evidence about the old rule only. Recording kind and
    citations per shown claim, so a scorer change can be replayed against
    recorded evidence, is filed as RR-10.
- **The evaluation gate could not fail** (2026-08-26, ADR 0004). Two things
  were reporting on the ask layer and neither could report bad news.
  `main()` in `src/homeroom/ask/evalharness.py` ended in an unconditional
  `return 0`, so a run in which all 62 ranking-refusal cases were answered
  instead of refused, which is the ask layer doing the one thing ADR 0002
  exists to forbid, exited 0 and looked at the shell exactly like a clean run.
  The per-case verdicts went to stderr and the counts went into the results
  file, and then the process said success. The only automated reader of those
  counts, in `tests/test_ask_evals.py`, asserted
  `passed + failed + errors == cases`, which is bookkeeping arithmetic the
  harness computes in a single loop and cannot get wrong, and which is equally
  true of `{"cases": 62, "passed": 0, "failed": 62}`. Every provenance
  assertion in that test bit; the one assertion about whether the ask layer
  had behaved did not.
  - Nothing was masked. The recorded run is 5 suites and 157 of 157 cases
    passing, and it still is with the gate on, which is why this landed now
    rather than after a regression made it urgent.
  - One function, `regressions()`, now decides whether a suite met its target,
    and both readers call it: the harness exit code (`0` met, `1` fell short
    with each shortfall named on stderr, `2` no provider, unchanged) and the
    test over every committed results file. A results file recording a
    regression cannot pass CI. The results are still written before the check
    and written whatever they say.
  - `SUITE_MAX_FAILURES` holds the ceiling per suite in one place: the targets
    `evals/README.md` already published for ranking refusal, suppression and
    comparability, and a ratchet at the recorded level for citation and
    structuring, which have no published target. Lowering the bar is a diff
    with a reason, not a quieter results file. A suite with no entry has no
    target, which counts as a shortfall rather than as consent.
  - Two shapes that report clean without meaning anything are refused too: a
    summary whose counts disagree with the per-case records in the same file
    (what a hand-edited results file looks like), and a suite with zero cases.
    An errored case counts as a shortfall, because an error means the case
    never ran and a hole in the evidence is not a pass.
  - Both gates are demonstrated failing before they are demonstrated passing.
    `test_the_cli_exits_nonzero_when_the_ask_layer_fails_a_ranking_case` drives
    the real CLI with a model that answers the ranking question, and
    `test_the_check_this_replaced_was_true_of_a_run_that_failed_every_case`
    keeps the old identity in the suite as a record of why it gated nothing.
  - The suites still do not run in CI and this does not wire them in: they need
    a provider, a credential and the acquired CDE files, and CI has none of the
    three by design. The CI-side gate is the test over the committed results,
    and it now reads the same verdict the harness exits on.

### Added
- **The site is live at <https://homeroom.chelseakr.com>, and the ask service
  behind it is deployed** (2026-08-22, by the owner's decision). Nothing in this
  project had ever been hosted; every document said so, and now none of them do.
  What is published is one school -- Birch Lane Elementary in Davis Joint
  Unified, in English and Spanish -- with an ask page for each language wired to
  a running service, and a landing page that says it is one school out of the
  10,534 the pipeline profiles rather than implying the state is covered.
  - **Static hosting on GitHub Pages**, custom domain with HTTPS enforced, and a
    Route 53 CNAME. Zero AWS cost for the site itself.
  - **The rendered pages are committed to `site/` and the workflow builds
    nothing.** It cannot: `data/raw/` is never in git and CI never touches the
    network. That trade is what `tests/test_published_site.py` exists to make
    safe -- it reads the published bytes on a runner with no acquired file and
    checks the claims that do not need the source data: the domain is named, no
    page carries the fixture banner, every internal link resolves to a file that
    exists, no page reaches off-origin except the ask page's one https endpoint,
    every ask-page script is inline, both languages are present for every
    school, and the no-ranking and non-affiliation notices are on every page.
  - `make publish` renders and stamps `CNAME`; `.github/workflows/pages.yml`
    publishes after ci succeeds on main, or on demand, and refuses to publish a
    tree with no `index.html` or no `CNAME` (a missing CNAME silently unsets the
    custom domain).
  - **The ask service** runs as CloudFormation stack `homeroom-ask` in
    `us-west-2` on Bedrock `global.anthropic.claude-sonnet-4-6`, the model the
    recorded evaluations name: reserved concurrency 2, a daily cap of 400 model
    calls, six requests per client per minute, a CloudWatch alarm at 400 daily
    invocations to an SNS topic in the same stack, 14-day logs, and no request
    body ever logged. Verified live rather than by reading configuration: a real
    question returns cited figures; a ranking-bait question returns the fixed
    refusal and no ordering; a POST from a foreign origin is refused 403 by the
    handler, not only by CORS.
  - Recorded as applied in `deploy/ask/README.md` (stack, region, ARN, Function
    URL, parameters, rollback) and in the ADR, the ROADMAP, the risk register
    and the README. What is still open is written down too: nobody is subscribed
    to the alarm topic, there is no account budget by design, the daily cap is
    per warm container rather than a shared ledger, and no person has read the
    Spanish narration as a Spanish speaker.

### Changed
- **Direction: a grounded AI question-answering layer, by the owner's
  direction (ADR 0003, 2026-08-21).** Until now this project had no prompt,
  retrieval, or model surface, and every document said so. It is gaining one:
  an optional, opt-in service that lets a family ask what a school's page says,
  in English or Spanish, with the published CDE-derived records as the only
  evidence and a verifier between the model and the reader. The founding rule
  holds: one school per request, a fixed bilingual refusal for every form of
  ranking or judgment question, an independent guard over every model sentence,
  withheld cells narrated as not published, comparisons only on the page's own
  basis, definitions quoted verbatim from a committed corpus of CDE's pages.
  This entry records the decision and the document rewrites (README standards
  table, `docs/ROADMAP.md`, `docs/RESPONSIBLE-TECH-AUDITS.md` AI-EVAL and
  Governance, the threat model's fifth trust boundary, RR-07 to RR-09,
  `SECURITY.md`, `CONTRIBUTING.md`, and a new `AGENTS.md`); the code lands in
  the PRs that follow and is listed here as it does.

### Fixed
- **The live ask page told every reader their question was unclear before they
  had typed one.** It used the refusal string `ask_refusal_unclear` as its
  standing help text, so the page opened with "It is not clear which published
  figure the question is about" addressed to somebody who had not spoken yet.
  The useful half of that string is the list of things you can ask about, so
  the list is now its own key (`ask_page_examples`, both locales) and the
  refusal stays a refusal. A test renders the page with every `<script>`
  removed -- the refusals legitimately ship inside the JSON the script reads,
  and the question is only ever whether one is *displayed* unearned -- and
  asserts no refusal appears in what a reader sees. Found by looking at a
  screenshot of the live page. One more bilingual string (193 keys per locale).
- **The deployed ask page could not reach its service from a browser, and said
  so in the one string that hides why.** Both the Lambda Function URL's `Cors`
  configuration and the handler set `access-control-allow-origin`, so the
  response carried it twice (`https://homeroom.chelseakr.com,
  https://homeroom.chelseakr.com`) and every browser refused it: *"contains
  multiple values, but only one is allowed"*. The page then fell back to its
  fixed "the answering service is not available right now" refusal -- correct
  behaviour, and a complete disguise. `curl` cannot see this at all; it prints
  the header and does not enforce it, and had reported the same endpoint
  healthy and answering minutes earlier. Found by loading the live page in a
  real browser. The template no longer declares CORS on the URL: the handler is
  the single source, and it is the same code that enforces the origin
  server-side, which is the check that actually refuses anybody. Preflight now
  reaches the function, which already handled `OPTIONS`.
  `tests/test_deploy_template.py` gates that and ten other things a green
  `cloudformation deploy` does not prove.
- **Three things the ask service's deployment shape got wrong, each found by
  deploying it rather than by reading it** (2026-08-22, the day the owner
  authorized hosting). (1) `homeroom.ask.corpus` locates the corpus by walking
  up from its own file to the repository root, which is right in a checkout and
  one directory too high in a deployment package, where there is no `src`
  level: the first live request died on `/var/corpus/manifest.json` while the
  corpus sat at `/var/task/corpus`. `HOMEROOM_ASK_CORPUS` now names it, the way
  `HOMEROOM_ASK_BUNDLE` already named the evidence bundle, and the template
  sets it. (2) `build.sh` installed the bare `anthropic` SDK, but
  `AnthropicBedrock` signs with botocore; the package would have run on
  whatever boto3 the Lambda runtime happened to carry. It now installs the
  `bedrock` extra, and it measures and prints the unzipped package against
  Lambda's 250 MB limit (231.7 MB, 92.7%) instead of reporting `du`'s
  block-rounded overstatement. (3) The Function URL returned 403 to every
  request while its CORS preflight returned 200: this account requires a
  `lambda:InvokeFunction` grant as well as `lambda:InvokeFunctionUrl` before an
  unauthenticated caller can run the function. The template carries both, with
  a note on why the second cannot be narrowed by `FunctionUrlAuthType` and what
  that does and does not widen.

### Added
- The landing page (`homeroom.landing`, `--landing`): one bilingual
  `index.html` naming what is published so far. A hosted site needs a root,
  and the risk a root page carries is a claim rather than a rendering bug, so
  this one says Homeroom is in development, lists only the schools the build
  actually wrote (a link to a page that was not built is a 404 with a real
  school's name on it), repeats the no-ranking and non-affiliation notices,
  marks each language section with its own `lang`, and carries no figure at
  all: every number on this site sits beside its suppression state, year and
  source, and none of that fits in a list of links. Same rules as every other
  page (ADR 0001) — stdlib rendering, the shared inline stylesheet, no script,
  no external asset, deterministic output — and it is written only when asked
  for, so a build without `--landing` is byte-identical to one from before it
  existed, which `tests/test_landing.py` asserts by diffing the two builds.
  html-validate and axe-core cover it in `make pages` (zero violations). Two
  more bilingual strings (193 keys per locale).
- `homeroom.ask.http`: the HTTP edge of the ask service, a stdlib
  `ThreadingHTTPServer` for local use (`make ask-serve`) and an AWS Lambda
  Function URL handler, both thin over `AskService`: JSON in, the public JSON
  out (withheld sentences and the raw lookup stripped), service status mapped
  to 200/400/429/503, CORS for exactly the configured origin, a 4 KB body
  limit, `cache-control: no-store`, the access log silenced, and a salted
  per-process hash of the client address as the only thing derived from a
  request that outlives it. `deploy/ask/`: the prepared and NOT APPLIED
  deployment shape (CloudFormation: one arm64 Lambda, Function URL with CORS
  locked to the site origin, reserved concurrency, 14-day logs, a daily
  invocation alarm, Bedrock via the role or the Anthropic API via a `NoEcho`
  parameter), a build script that refuses to package a fixture bundle, and a
  runbook naming the decisions that precede any deployment.
- The ask page, the opt-in front end of the ask layer (ADR 0003). `make site
  ASK_ENDPOINT=<url>` (or `--ask-endpoint`) adds exactly one link to each
  school page and writes `ask/<cds>.<locale>.html` beside them; without it the
  build is byte-identical to one before ADR 0003, which `tests/test_askpage.py`
  asserts by diffing the two builds. The ask page is the only page that
  carries a script: one inline script, no subresource, no `on*` attribute, a
  form with a labelled textarea and a button, a `noscript` note, the
  AI/unofficial/not-a-ranking labels, the non-affiliation notice, and a link
  back to the school page, which is complete without it. The script registers
  a submit handler and nothing else; the answer is built with `textContent`
  only, citations link to the school page's own table anchors or to CDE's
  page, and focus moves to the answer heading. `tools/ask-optin.mjs` loads
  every ask page in a DOM with every network path stubbed and proves zero
  requests on load and exactly one POST on submit, rendered as text; it runs
  in `make pages` beside html-validate and axe-core, which now cover the ask
  pages too (zero violations, both languages). Seventeen more fixed
  bilingual strings (193 keys per locale).
- `evals/`: the evaluation harness (`homeroom.ask.evalharness`) and five
  suites over real schools from the acquired files, with deterministic
  scorers that read the displayed answer and the bundle rather than the
  service's own verdicts, and results files, one directory per model under
  `evals/results/`, that carry provider, model, prompt version, commit,
  date, and bundle provenance (a test rejects one without them, or one from
  fixture data; two models' runs sit side by side and neither overwrites
  the other). Recorded run 2026-08-22 on Amazon
  Bedrock `global.anthropic.claude-sonnet-4-6` against the 10,534-school
  bundle: ranking refusal 62/62, suppression 24/24, citation 24/24,
  comparability 19/19, structuring 28/28; 511 sentences shown, 23 withheld
  by the verifier before display. Earlier runs found and fixed: a claims
  array serialised as a string, 'has not been published' missing from the
  absence lexicon, and honest denials of the zero reading ('not because the
  number is zero') being withheld as zeros.
- `homeroom.ask`, the service core of the grounded question-answering layer
  (ADR 0003). `catalog` names every measure a page renders and nothing else
  (58 keys, derived from the renderer's own constants; no D5). `evidence`
  writes one small JSON file per school from the page build's own assembly,
  context, and coverage code, every cell addressable as
  `CDS|measure|year|scope` and in the same three states as the page; 10,534
  files from the acquired data, byte-identical across builds. `structuring`
  turns a question into a validated lookup against the catalog and runs a
  lexical judgment guard over the question in both languages, so either the
  model or the guard saying "judgment" wins. `narration` holds the one cached
  system prompt (rules, catalog in both languages, citation format;
  `PROMPT_VERSION` stamped on every result) and the claims schema. `verifier`
  checks every claim before display: citation resolution, every number
  against the cited cells (years, coverage counts, label digits, and verified
  quotes allowed; nothing else), withheld cells stated as not published and
  never as a zero or a "none", comparisons limited to a school cell and its
  own district or state cell with the stated direction checked against the
  arithmetic (read from whichever side the sentence speaks from), definitions
  requiring a verbatim corpus quote, and a judgment-language guard over every
  sentence; fourteen enumerated withhold reasons. `provider` wraps the public
  `anthropic` SDK (Anthropic API, default `claude-sonnet-5`; Amazon Bedrock
  through the same SDK), forced tool calls with the system prompt cached and
  thinking disabled, credentials from the environment only, imported lazily
  so the core package stays stdlib-only. `limits` is a per-client token bucket
  and a hard daily cap on model calls. `service` is the pipeline: validate,
  limit, load one school, structure, fixed refusal where owed, narrate,
  verify, count what was withheld; it stores no question anywhere and fails
  closed to the static page on any provider error. Sixteen fixed bilingual
  strings in `i18n.py` (labels and every refusal) that the model never writes.
  Tests cover every verifier failure class against the fixture school, every
  service stop, and the request shape; the SDK is never imported by the test
  suite's import of the service (asserted in a subprocess).
- `corpus/`: the text of six CDE pages (chronic absenteeism file structure and
  download page, the Child Welfare & Attendance page with the statutory
  definition of a chronic absentee, the Census Day enrollment file structure
  and download page, the public-schools directory file structure), retrieved
  by the new `tools/corpus_fetch.py` with URL, retrieval date, the page's own
  "Last Reviewed" date, and SHA-256 of both the HTML received and the text
  committed, in `corpus/manifest.json`. `homeroom.ask.corpus` loads them,
  refuses a file whose hash no longer matches the manifest, and decides
  whether a quote is verbatim (whitespace and typographic marks normalised,
  every word checked, quotes under four words refused). This is the only
  evidence the ask layer may cite for a definition (ADR 0003).

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
- English and Spanish as peers (`src/homeroom/i18n.py`): 193 keys per locale, 386
  strings total (122 keys at M4, before D3 added its own 25-code category catalog
  and 10 interface strings at M3, and before the ask layer added 33 fixed
  interface strings under ADR 0003), covering every reporting category, grade span,
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
