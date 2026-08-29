"""CI and the Makefile must be the same gate.

`AGENTS.md` says "`make verify` is the gate, byte-for-byte identical to CI",
and the Makefile's own comment said the two MUST stay identical. Until
2026-08-28 neither was true: `.github/workflows/ci.yml` ran three jobs, and
`make verify` covered one of them. The secret scan, the SAST scan, and the
twice-build determinism check existed only as inline script in the workflow,
with no target to run them by, so a tree CI would reject passed the local gate
and the difference was invisible from the repository.

The fix is not a longer comment. Every step in ci.yml runs one `make` target,
every one of those targets exists, and every one of them is reachable from
`verify`. Those three facts are checked here, so adding a stage to CI without a
local equivalent fails the build that adds it.

ci.yml is the merge gate and is the file held to this. `release.yml` runs a
signing and provenance pipeline whose steps are inherently one-off, and
`pages.yml` publishes a directory and builds nothing; neither gates a merge.

That fix had a hole of its own, closed here on 2026-08-29. "Every step in ci.yml
runs one `make` target" was checked by matching `run:` lines, and a step does not
have to be a `run:` line. Eight of ci.yml's eleven steps are `uses:` steps, and
the entire `secret-scan` job is one of them: it runs no command at all, so the
`run:`-only view of the workflow saw an empty job and reported success. A gate
that cannot see a job cannot notice a job being added. Every step is classified
now: a `run:` step must call a make target, and a `uses:` step must be either a
setup or reporting action named in `SETUP_AND_REPORTING` or a gating action
registered in `GATING_ACTIONS` against the make target that runs the same check
locally. An unrecognised action fails the build that adds it.

The workflow is read as text. `PyYAML` is not a dependency of this project, and
`tests/test_deploy_template.py` already records the same trade for the same
reason.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"

# A step's command. Anything that is not `run: <one line>` -- notably `run: |`,
# which opens an inline script -- is caught by the assertions below rather than
# skipped, because an inline script is exactly the thing that has no make target.
RUN_STEP = re.compile(r"^\s*(?:-\s+)?run:\s*(.*)$", re.M)
MAKE_CALL = re.compile(r"^make\s+([a-z][a-z0-9-]*)$")

# A `uses:` step. The action's identity is everything before the `@`; the pin and
# the trailing `# vX.Y.Z` comment are checked elsewhere and ignored here.
USES_STEP = re.compile(r"^\s*(?:-\s+)?uses:\s*([^@\s]+)@\S+", re.M)

# Actions that fetch the tree, install a toolchain, or upload a report. None of
# them decides whether the build passes, so none of them needs a local twin:
# `actions/checkout` is the checkout `make` already has, the two setup actions
# install what `make` then invokes, and `codecov/codecov-action` runs with
# `fail_ci_if_error: false` and uploads a file `make test` produced.
SETUP_AND_REPORTING = frozenset(
    {
        "actions/checkout",
        "astral-sh/setup-uv",
        "actions/setup-node",
        "codecov/codecov-action",
    }
)

# Actions that are gates, mapped to the target that runs the same check locally.
# `gitleaks/gitleaks-action` scans history; `make secret-scan` runs that pass and
# a second one over the working tree, which is the superset the Makefile explains.
# This is the registration an action-only job needs in order to be visible here.
GATING_ACTIONS = {"gitleaks/gitleaks-action": "secret-scan"}

# A job header: two spaces of indent under `jobs:`, a name, a colon, nothing else.
JOB_HEADER = re.compile(r"^  ([a-z][a-z0-9-]*):\s*$", re.M)


def ci_source() -> str:
    """The workflow with comment-only lines dropped.

    A comment naming `uses:` or `run:` is prose about the file, not a step in it.
    """
    return "\n".join(
        line
        for line in CI.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def ci_run_commands() -> list[str]:
    return [m.group(1).strip() for m in RUN_STEP.finditer(ci_source())]


def ci_actions() -> list[str]:
    return [m.group(1) for m in USES_STEP.finditer(ci_source())]


def ci_jobs() -> dict[str, str]:
    """Every job in ci.yml, by name, mapped to its own block of the file."""
    source = ci_source()
    body = source[source.index("\njobs:\n") :]
    headers = list(JOB_HEADER.finditer(body))
    return {
        m.group(1): body[
            m.end() : (headers[i + 1].start() if i + 1 < len(headers) else len(body))
        ]
        for i, m in enumerate(headers)
    }


def targets_a_job_runs(block: str) -> set[str]:
    """The make targets one job's steps reach, whether by `run:` or by action."""
    targets = {
        m.group(1)
        for command in (c.strip() for c in RUN_STEP.findall(block))
        if (m := MAKE_CALL.match(command))
    }
    targets |= {
        GATING_ACTIONS[action]
        for action in USES_STEP.findall(block)
        if action in GATING_ACTIONS
    }
    return targets


def makefile_targets() -> set[str]:
    targets: set[str] = set()
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-z][a-z0-9-]*)\s*:(?!=)", line)
        if match:
            targets.add(match.group(1))
    return targets


def prerequisites() -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-z][a-z0-9-]*)\s*:(?!=)(.*)$", line)
        if match:
            rules[match.group(1)] = match.group(2).split()
    return rules


def reachable_from(target: str) -> set[str]:
    rules = prerequisites()
    seen: set[str] = set()
    stack = [target]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(rules.get(current, []))
    return seen


def test_the_workflow_and_the_makefile_are_both_readable() -> None:
    """A floor: a renamed workflow would otherwise pass every check below."""
    assert CI.is_file(), CI
    assert MAKEFILE.is_file(), MAKEFILE
    assert len(ci_run_commands()) >= 3, ci_run_commands()
    assert "verify" in makefile_targets()


def test_every_ci_step_runs_a_make_target() -> None:
    """An inline script in CI is a gate the Makefile cannot reproduce."""
    offenders = [c for c in ci_run_commands() if not MAKE_CALL.match(c)]
    assert not offenders, (
        "every step in ci.yml must be `make <target>` so the local gate can run "
        f"it; these are not: {offenders}"
    )


def test_every_target_ci_runs_exists() -> None:
    targets = makefile_targets()
    called = {m.group(1) for c in ci_run_commands() if (m := MAKE_CALL.match(c))}
    assert called, "no make target found in ci.yml"
    missing = sorted(called - targets)
    assert not missing, missing


def test_every_target_ci_runs_is_reachable_from_verify() -> None:
    """`make verify` green must mean CI green, which means verify covers it all."""
    called = {m.group(1) for c in ci_run_commands() if (m := MAKE_CALL.match(c))}
    covered = reachable_from("verify")
    uncovered = sorted(called - covered)
    assert not uncovered, (
        "CI runs these targets, but `make verify` does not reach them, so the "
        f"local gate can be green on a tree CI rejects: {uncovered}"
    )


def test_verify_still_reaches_the_gates_that_used_to_be_ci_only() -> None:
    """Named so that dropping one from `verify` fails loudly rather than quietly."""
    covered = reachable_from("verify")
    for target in ("determinism", "secret-scan", "sast", "test", "pages", "audit"):
        assert target in covered, target


def test_the_workflow_is_read_as_jobs_and_steps_not_just_as_run_lines() -> None:
    """The floor under everything below: the parse has to see the whole file.

    ci.yml has three jobs and eleven steps, only three of which are `run:`
    lines. If this parse ever sees fewer jobs than the file has, every check
    below silently narrows.
    """
    jobs = ci_jobs()
    assert len(jobs) >= 3, sorted(jobs)
    assert "verify" in jobs and "secret-scan" in jobs and "sast" in jobs, sorted(jobs)
    assert len(ci_actions()) > len(ci_run_commands()), (
        ci_actions(),
        ci_run_commands(),
    )


def test_every_action_ci_uses_is_a_known_setup_step_or_a_registered_gate() -> None:
    """An unregistered action is a stage nothing local reproduces.

    This is the check that was missing: a gate can arrive in CI as a `uses:`
    step and never touch a `run:` line, which is exactly how the `secret-scan`
    job stayed invisible to this file.
    """
    unknown = sorted(
        action
        for action in ci_actions()
        if action not in SETUP_AND_REPORTING and action not in GATING_ACTIONS
    )
    assert not unknown, (
        "these actions run in ci.yml and this file does not know what they are; "
        "add each to SETUP_AND_REPORTING if it only fetches or reports, or to "
        f"GATING_ACTIONS against the make target that reproduces it: {unknown}"
    )


def test_every_gating_action_names_a_target_verify_reaches() -> None:
    covered = reachable_from("verify")
    targets = makefile_targets()
    for action, target in GATING_ACTIONS.items():
        assert target in targets, (action, target)
        assert target in covered, (action, target)


def test_every_ci_job_runs_something_the_local_gate_can_run() -> None:
    """A job with no locally runnable stage is a gate that exists only in CI."""
    covered = reachable_from("verify")
    for name, block in ci_jobs().items():
        targets = targets_a_job_runs(block)
        assert targets, (
            f"the `{name}` job in ci.yml runs no make target and no registered "
            "gating action, so `make verify` cannot reproduce it"
        )
        assert targets <= covered, (name, sorted(targets - covered))


def test_the_secret_scan_job_is_the_one_this_gate_used_to_miss() -> None:
    """Named so that losing sight of it again fails here rather than nowhere.

    The job runs a gitleaks action and no command. Under the old `run:`-only
    parse it contributed nothing and was indistinguishable from not existing.
    """
    block = ci_jobs()["secret-scan"]
    assert not [c for c in RUN_STEP.findall(block) if c.strip()], (
        "the secret-scan job now runs a command; check it calls a make target"
    )
    assert targets_a_job_runs(block) == {"secret-scan"}


# ----------------------------------------------------------------------------------
# The floor's own justification.
#
# `fail_under = 95` is argued for in a comment above it, and the argument rests on
# two measured numbers: "98.73% branch coverage over 515 tests (2026-08-29)". Both
# were typed by hand off one run and read back by nothing, and the suite had grown
# to 574 tests while the comment still said 515. A floor defended by a stale
# measurement is a floor nobody can check the reasoning of.
#
# The test count is re-derived here, from collection, which is the same thing pytest
# would report. The coverage percentage is not: measuring it means running the suite
# under coverage, which is what the `test` target already does, and re-running it
# inside itself would double the gate's cost to re-assert a number the gate already
# enforces. What is checked instead is the relationship the comment actually claims,
# that the floor sits below what is measured, which is the part a drifting figure
# would break.
# ----------------------------------------------------------------------------------

PYPROJECT = ROOT / "pyproject.toml"

MEASURED = re.compile(
    r"suite measures ([\d.]+)% branch coverage over\s+([\d,]+)\s*\n?#?\s*tests"
)
FAIL_UNDER = re.compile(r"^fail_under = (\d+)$", re.M)


def _collected_tests() -> int:
    """How many tests this suite actually collects."""
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"(\d+) tests? collected", completed.stdout)
    assert match is not None, f"pytest reported no collected count:\n{completed.stdout}"
    return int(match.group(1))


def test_the_coverage_floor_states_the_suite_it_was_measured_against() -> None:
    """The comment defending `fail_under` names a suite size; it must be this one."""
    body = PYPROJECT.read_text(encoding="utf-8")
    measured = MEASURED.search(" ".join(body.split()).replace("# ", ""))
    assert measured, "pyproject.toml no longer says what the floor was measured against"
    stated_coverage = float(measured.group(1))
    stated_tests = int(measured.group(2).replace(",", ""))

    collected = _collected_tests()
    assert stated_tests == collected, (
        f"pyproject.toml defends fail_under with a measurement over {stated_tests} "
        f"tests; the suite collects {collected}."
    )

    floor = FAIL_UNDER.search(body)
    assert floor, "pyproject.toml no longer sets fail_under"
    assert stated_coverage > int(floor.group(1)), (
        f"the comment says the floor sits under what is measured, but it states "
        f"{stated_coverage}% against a floor of {floor.group(1)}."
    )
