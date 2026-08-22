# Working in this repository

Read this before changing anything. It applies to people and to AI coding
agents alike; the project is built AI-assisted and says so in the README, and
these rules are what keep that honest.

## What this is

California public school data, joined from CDE's own published files into
plain-language bilingual school pages. It refuses to rank schools (ADR 0002).
A suppressed measure renders as *not published*, never as zero. A number that
cannot be shown honestly is not shown at all. Unofficial; not affiliated with
the State of California or any district. In development; nothing is hosted.

As of ADR 0003 it also carries an optional, opt-in AI question-answering layer
(`src/homeroom/ask/`). Everything below binds that layer first.

## Rules that are enforced in code, and that you must not route around

1. **No ranking, scoring, grading, or ordering of schools.** No code path may
   combine measures into a single number or compare one school to another. The
   AI layer sees one school per request and a verifier withholds any sentence
   that carries better/worse, grade, score, rank, or recommendation language.
   A PR touching `Measure`, suppression handling, the verifier, the refusal
   strings, or the ranking-refusal evaluation must link an ADR.
2. **Three states, never collapsed.** `reported`, `suppressed`, `not_reported`
   are distinct. `Measure.number()` raises unless the state published a number.
   Never write a default of `0`, never `or 0`, never `.get(key, 0)` for a cell.
3. **Copy cells; never compute them.** No sums across schools, no subtraction
   from totals, no rate divided out of a count. District and statewide figures
   come from CDE's own aggregate rows only.
4. **Unrecognized upstream values stop the build.** `parse_cell`, the category
   maps, and the drift errors are load-bearing. Do not add a fallback branch.
5. **Every AI claim is verified before display.** A claim must cite a record
   (`CDS | measure | year`) or a corpus passage, every number in it must be a
   number that record publishes, and a claim about a withheld cell must say so
   without a digit. Unverifiable claims are withheld and counted, never shown.
   Do not weaken the verifier to make an evaluation pass.
6. **The refusal text is fixed.** Ranking, outside-the-data, unknown-school,
   and measure-not-published answers are reviewed strings in `i18n.py`, in both
   languages. The model does not author them.
7. **The school pages carry no script and reach nowhere.** Only the ask page
   carries a script, and it makes no request until a question is submitted.
   `tests/test_pages.py` asserts both.
8. **EN/ES parity.** Every user-visible string exists in both locales; the
   parity gate fails on a missing key, an untranslated string, or a lost
   placeholder. The README, CHANGELOG, and ROADMAP state the key count and a
   test checks it; adding a key means updating those numbers.

## Data and provenance

- Real data only. Tests run over committed fixtures shaped like the real files;
  evaluations run over the real acquired files in `data/raw/` (gitignored, never
  fetched by CI). Never present a synthetic school record as real.
- Every source is a named CDE public file with an access date in
  `PROVENANCE.md`. The corpus of CDE definitions in `corpus/` records URL,
  retrieval date, and SHA-256 per page. Do not paraphrase a definition as a
  quote.
- Do not study or borrow from commercial school raters. The repo exists in
  opposition to that model.

## AI layer specifics

- Provider: public `anthropic` SDK only. Default model `claude-sonnet-5`,
  configurable by environment. Credentials from the environment only; never
  write a key to any file, log, fixture, or results file.
- Clean room: write the AI layer fresh on the SDK and the standard library.
  Never vendor or copy source from another repository, public or private.
- Cost: the service rate-limits per client and enforces a hard daily cap; a
  refused request must leave the page intact.
- Evaluation results are committed only from a live run and carry provider,
  model, prompt version, commit, and date. A suite that did not run says
  `not_run`. Never fabricate a number.
- Deployment is an owner decision. Prepare templates; never apply them.

## Workflow

- `make verify` is the gate, byte-for-byte identical to CI. Run it before
  opening a PR.
- Stage explicit paths. Never `git add -A`.
- Never force-push `main`. Never delete a branch without confirming it is a
  pure merge leftover.
- Keep the non-affiliation notice on every page, including the ask page.
- Issue #6 (keyboard and screen-reader walkthrough) needs a person with a
  browser and a screen reader. Any new UI must be keyboard-accessible and must
  say what it could not test.
