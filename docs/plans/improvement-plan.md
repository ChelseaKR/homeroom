# Improvement plan, 2026-08-28

An audit of the open issues and of the gates themselves, on the principle that
**a check that cannot fail is worse than no check**: it spends the reader's
trust without earning it. Everything below was executed in this pass except
where marked blocked, and every guard added or repaired was run against a
deliberately introduced fault before being trusted green.

## What the audit found

The project works. `uv sync --locked` installs, 501 tests passed at the start of
the pass, `make verify` exited 0, and the pipeline, the page build, both node
gates and the published-site checks all do what the README says they do. The
README's factual claims about the data were spot-checked and hold. What follows
is not a broken project; it is a set of gates that were weaker than the
documents describing them.

Three of the traps found were live, not theoretical, and each was confirmed by
running it:

| Gate | Stated scope | Real scope |
|------|--------------|-----------|
| semgrep (CI `sast` job) | the repository (`.`), 55 tracked Python files | 30 files; `tests/` dropped by the built-in ignore list |
| gitleaks (CI `secret-scan` job) | "secret scan" | git history only; an uncommitted key exits 0 |
| determinism check (CI, inline) | two builds are byte-identical | passes having hashed zero files |

And two claimed controls that did not exist or could not fire:

- `make verify` was documented, twice, as byte-for-byte identical to CI. CI ran
  three jobs; `make verify` covered one.
- zizmor was named in three documents as the control for SHA-pinned actions and
  permissions creep. It was not in the repository. When wired, its default
  configuration accepted `actions/setup-node@v7`, so even present it could not
  have backed the claim without a `hash-pin` policy.

## Issue classification

| Issue | Class | Disposition |
|-------|-------|-------------|
| #34 ask-layer verifier accepts a number matching any nearby figure | **Real defect**, safety-critical. Repro executed verbatim and reproduced exactly | Fixed |
| #35 anti-ranking rule cites ADR 0000 instead of ADR 0002 | **Real defect** in the audit trail. Correctly attributed, but undercounted: it lists seven sites, there are eight | Fixed, plus the eighth, plus a guard |
| #6 keyboard and screen-reader walkthrough is untracked | **Real gap, correctly described.** Needs a person with a browser and a screen reader | **Blocked.** Documentation half done |

## Phases

### Phase 1 -- the verifier licenses numbers per fact (issue #34) -- DONE

`_allowed_numbers` pooled every number near a cited record and asked only
whether a claim's numbers appeared somewhere in the pool. The pool included the
record's statewide coverage tally, the build size and the grade span. In the
committed fixture a school's absenteeism rate is 12.5% and its coverage tally
contains 1, so "the rate was 1%" verified clean and was shown to a reader as a
cited figure. Numbers are now licensed by claim kind: `note` keeps the context
numbers, `figure` and `comparison` get only what their own cited cells publish.
The independent eval scorer carried the identical construction and is narrowed
the same way, by its own code path.

Narrowing by kind reached the coverage tally, the build size and the grade span.
It could not reach the third sort of number in the pool: the digit inside a
measure's own label. "Grade 4" has to be sayable in a `figure` claim, because
naming the row is half the sentence, so the label's digits stayed licensed as
bare tokens for every kind -- and in the same committed fixture Grade 4 enrols
9 students, so "Example Elementary enrolled 4 students in Grade 4" verified
clean and was shown, with the number it borrowed sitting in the same sentence.
That one is narrowed by position instead (`strip_label_references`, 2026-09-02):
the digits written against the label's word come out of the claim before the
check, in either language and in the shapes narration writes ("Grade 4", "4th
grade", "Grades 7 and 8", "Grados 7 y 8"), and every other digit is matched
against the cited cell as before. Both the verifier and the eval scorer.

The fourth sort of number in that pool was the last one licensed as a bare
token: the digits inside a verified CDE quote (issue #64). `_allowed_numbers`
ended by adding every number anywhere in the quote, for any claim kind, and
`_check_quote` required a quote for a `definition` without ever restricting one
to a `definition` -- so a `figure` could carry a corpus quote and spend its
digits on the school. CDE's definition of a chronic absentee contains the
number 10; the fixture school's published rate is 12.5; `narration_prompt` puts
that passage and that cell in the same model turn whenever the question names
both, which the committed eval case `cit-006` does. "At Example Elementary, 10
percent of students were chronically absent in 2024-25" verified clean beside a
real citation of the cell it contradicts. Narrowed by position and by kind
together (2026-09-05): the quotation comes out of the claim before the check,
so CDE's digits are licensed where the sentence quotes them, and only for the
kind the `quote` field is documented for. A quote on another kind stays legal
and stays displayed; it licenses nothing. Both the verifier and the eval
scorer, and the scorer's rule this time names no kind at all, so a widened
`QUOTE_CLAIM_KINDS` would still be caught by its double-check.

### Phase 2 -- the ADR citation trail (issue #35) -- DONE

Eight sites retargeted from the process meta-ADR to ADR 0002, the Accepted
decision. ADR 0000's `Date:` placeholder, committed unfilled for three weeks, is
set to the date the file was added. `tests/test_adr_citations.py` makes the trail
checkable rather than checked once.

### Phase 3 -- the gate is the gate (no issue; found by audit) -- DONE

Every CI stage is a `make` target, `verify` reaches all of them, and
`tests/test_ci_parity.py` fails if that stops being true. The determinism check
gained a floor under its hash comparison. The secret scan gained a working-tree
pass. Semgrep gained `tests/`. zizmor exists, pinned, with a hash-pin policy and
exactly one documented suppression.

### Phase 4 -- a gate that could vanish over the tree that needed it -- DONE

`tests/test_published_site.py` skipped its whole module when `site/` was
absent. `site/` is committed and is what GitHub Pages serves, and `make publish`
starts with `rm -rf`, so absence means an interrupted publish, not "nothing to
check". Hiding `site/` and running the old file gives 10 skipped, exit 0. It now
fails, starting with a floor naming what is missing.

### Phase 5 -- documents that did not match behaviour -- DONE

`RR-02` and the threat model said `--frozen`; the Makefile has said `--locked`
since 2026-08-26. `AGENTS.md`'s identical-to-CI claim is now true and checked.
The README's Accessibility row named only the automated half of a two-half gate;
it names both and links issue #6 and RR-05, which is what `DOC-13` asks. The
Security row says what actually runs.

### Phase 6 -- the accessibility walkthrough (issue #6) -- BLOCKED

Not doable from here, and saying otherwise would be the same failure this plan
is about. It needs a person driving a real browser and a real screen reader over
a built page in each language: tab order through the seven-column measure
tables, focus visibility on the scrolling region, the four cell states
distinguishable by voice alone, and reflow at 320 CSS pixels. `tools/a11y.mjs`
already names the two rules a headless DOM cannot decide, and jsdom does no
layout, so no gate in this repository can close it.

What was done instead: the README conformance row now states the open half
rather than describing only the automated one, and links the issue and the risk
register entry. The claim is honest even though the work is outstanding.

## Open, and deliberately not closed here

- **RR-10 (new).** A committed evaluation results file records each shown
  claim's text but not its kind or its citations, so the Phase 1 change could
  not be replayed against the recorded 157-case run. Closing it means recording
  `kind` and citation ids per shown claim, which is additive.
- **ADR 0000's Decision section** still lists guardrails from a sibling project
  ("no-outing/grounding/consent/identity-inference") that are not this
  project's. It is scaffold text from `standards-init`. ADRs here are immutable
  once Accepted, so correcting a Decision section is an owner's call and was not
  made unilaterally; the unfilled date was a generator placeholder rather than a
  decision and was filled.
- **`release.yml` and `pages.yml` are not held to the CI parity rule.** Their
  steps are inline scripts by nature (signing, SBOM, provenance) and neither
  gates a merge. Extending the rule to them is possible and was not attempted.
- **The four Dependabot PRs (#38-#41)** are all green and mergeable and were
  left alone; merging is not this pass's to do.
