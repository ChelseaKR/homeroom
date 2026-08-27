# 0004. The evaluation gate has to be able to fail

Status: Accepted
Date: 2026-08-26
Deciders: Chelsea Kelly-Reif
Relates to: ADR 0002 (refuse to rank schools) and ADR 0003 (grounded AI at the
edges). Neither is amended. This ADR makes the evaluation that enforces them
capable of reporting that they were broken.

## Context

ADR 0003 added five evaluation suites and a harness, and the repository has
been describing them as enforcement ever since. `docs/RESPONSIBLE-TECH-AUDITS.md`
lists them under AI-EVAL as "AUTO". `evals/README.md` publishes a target for
each suite, two of them "zero failures, always". The README states the recorded
run: 157 cases, all passing.

Two things were true at the same time, and only one of them was written down.

`main()` in `src/homeroom/ask/evalharness.py` ended in `return 0`, with no
branch above it that could produce anything else except the `return 2` for a
missing provider. The per-case verdicts were printed to stderr and the counts
were written into the results file, and then the process reported success. A
run in which every one of the 62 ranking-refusal cases was answered instead of
refused, which is the ask layer doing the single thing ADR 0002 exists to
forbid, exited 0 and was indistinguishable at the shell from a clean run.

The test that reads the committed results files, in `tests/test_ask_evals.py`,
was the only automated reader of those numbers, since the suites cannot run in
CI at all: they need a provider, a credential, and the acquired CDE files, and
CI has none of the three by design. Its only assertion about the results was:

```python
assert summary["passed"] + summary["failed"] + summary["errors"] == summary["cases"]
```

That is bookkeeping arithmetic. The harness computes those four numbers in one
loop, incrementing exactly one of three counters per case, so the identity is
true by construction and cannot be false while the loop is correct. It is
equally true of `{"cases": 62, "passed": 0, "failed": 62}`. Every provenance
assertion in that test bites; this one, the only one about whether the ask
layer actually behaved, did not.

So the number in the README was accurate, and nothing in the repository was
capable of noticing if it stopped being accurate. This is a guardrail that is
present, green, and cannot fail: it reports on itself rather than on the thing
it is supposed to be watching.

Nothing was masked. The recorded run at the time of this ADR is genuinely
5 suites and 157 of 157 cases passing, so turning the gate on changes no
verdict today. That is the reason to do it now rather than after a regression.

## Decision

One function, `regressions()`, decides whether a suite's result met its target,
and both readers of that verdict call it.

- The harness exit code is the run's result. `0` only when every suite ran and
  met its target, `1` when one did not with each shortfall named on stderr,
  `2` unchanged for no provider configured. The results file is written before
  the check and is written whatever it says: a run that fell short is the
  evidence that matters most, and the exit code reports it rather than
  replacing it.
- The committed-results test asserts `regressions(result) == []` for every
  results file in every model directory. A results file recording a regression
  cannot be committed through a green CI run.
- `SUITE_MAX_FAILURES` holds the ceiling per suite, in code, in one place. The
  first three entries are the targets `evals/README.md` already published. The
  other two, citation and structuring, have no published target, so their
  entries are a ratchet at the level the recorded run reached. Lowering the bar
  is permitted and is a diff: raise the number, in a PR, with the reason. It is
  not permitted quietly, by committing a worse results file.
- A suite absent from `SUITE_MAX_FAILURES` has no target, which `regressions()`
  reports as a shortfall. Adding a suite without a target is a failure, not a
  free pass.
- `regressions()` also refuses two shapes that would otherwise report clean
  without meaning anything. A summary whose counts disagree with the per-case
  records in the same file is refused, which is what a hand-edited results file
  looks like. A suite with zero cases is refused, because "no failures" over
  nothing is the same defect in a smaller costume.
- An error is a shortfall. An error means the case never ran, so it is neither
  a pass nor a failure but a hole in the evidence, and a run with holes is not
  a clean run.

The evaluation suites are still not wired into CI, and this ADR does not wire
them in. They cannot run there: `data/raw/` is never in git, CI never reaches
the network, and a real run costs model calls against a credential CI does not
hold. The CI-side gate is and remains the test over the committed results, and
that test now reads the same verdict the harness exits on, so the two cannot
disagree.

## Consequences

- A regression in the ask layer's behaviour now stops something. Before this,
  the only thing standing between a broken ranking refusal and a green build
  was a person reading stderr.
- The owner will occasionally see exit 1 from a run that is fine and a ceiling
  that needs raising, for citation in particular, whose published target is "as
  high as the model allows" rather than a number. That is the intended cost: it
  converts a silent slide into a decision with a name on it.
- A results file can no longer be edited by hand into agreement with itself.
  The per-case records and the summary have to tell the same story.
- Every new suite has to arrive with a recorded target, because arriving
  without one is now a failure rather than a default.
