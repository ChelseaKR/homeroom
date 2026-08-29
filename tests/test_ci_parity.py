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


def ci_run_commands() -> list[str]:
    return [
        m.group(1).strip() for m in RUN_STEP.finditer(CI.read_text(encoding="utf-8"))
    ]


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
