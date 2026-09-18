"""The declarations in tools/config_audit.py must describe the real workflows.

The defect this guards is the one #116 shipped: a workflow merged with a
repository variable it cannot run without, recorded nowhere except inside the
file that needed it, so the only report was a scheduled red build the next
morning. The tool is what notices; these are the ways it could stop noticing
while still exiting 0.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `tools/` is not a package and pytest's pythonpath is `src`, so the module is
# loaded by path -- the same way tests/test_alarm_relay.py loads its subject.
# `from tools.config_audit import ...` appears to work under `python -m pytest`,
# which puts the working directory on sys.path, and fails under the `pytest`
# console script that `make test` actually runs.
_SPEC = importlib.util.spec_from_file_location(
    "config_audit", ROOT / "tools" / "config_audit.py"
)
assert _SPEC and _SPEC.loader
config_audit = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = config_audit
_SPEC.loader.exec_module(config_audit)

REQUIRED_VARIABLES = config_audit.REQUIRED_VARIABLES
_workflow_source = config_audit._workflow_source
declaration_problems = config_audit.declaration_problems
referenced_variables = config_audit.referenced_variables
unset_required_variables = config_audit.unset_required_variables


def test_every_variable_the_workflows_read_is_declared() -> None:
    """The live check: workflows and declarations agree right now."""
    assert declaration_problems() == []


def test_the_workflows_still_read_the_variables_this_repository_has() -> None:
    """A canary on the reader itself.

    If `referenced_variables` ever silently stopped matching -- a changed
    expression syntax, a renamed directory -- every other assertion here would
    pass on an empty set. So one known reference is named outright.
    """
    referenced = referenced_variables()
    assert "ASK_ALARM_RELAY_ROLE_ARN" in referenced, (
        "the reader found no reference to the relay's role ARN; either the "
        "workflow changed or the reader has stopped reading"
    )
    assert "ask-alarm-relay.yml" in referenced["ASK_ALARM_RELAY_ROLE_ARN"]


def test_a_variable_named_only_in_a_comment_is_not_a_dependency() -> None:
    """Prose about `vars.X` is not a use of it.

    ask-alarm-relay.yml contains the literal text `if: vars.X != ''` inside a
    comment arguing against that shape. A checker that reads comments as code
    would treat `X` as a required variable and then demand somebody configure
    it. Four conformance checks elsewhere in this portfolio passed by matching
    tool names in comments; this is the same mistake with the sign flipped.
    """
    relay = ROOT / ".github" / "workflows" / "ask-alarm-relay.yml"
    raw = relay.read_text(encoding="utf-8")
    assert "vars.X" in raw, (
        "this test is anchored on a comment in ask-alarm-relay.yml that no "
        "longer exists; re-anchor it rather than deleting it"
    )
    assert "vars.X" not in _workflow_source(relay)
    assert "X" not in referenced_variables()


def test_an_undeclared_variable_is_reported(tmp_path: Path) -> None:
    """A workflow that needs configuration nothing explains fails the build."""
    audit = config_audit

    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "new.yml").write_text(
        "jobs:\n  go:\n    if: vars.SOMETHING_NOBODY_WROTE_DOWN != ''\n",
        encoding="utf-8",
    )
    original = audit.WORKFLOWS
    try:
        audit.WORKFLOWS = workflows
        problems = audit.declaration_problems()
    finally:
        audit.WORKFLOWS = original

    assert any("SOMETHING_NOBODY_WROTE_DOWN" in p for p in problems)
    assert any("can be merged unable to run" in p for p in problems)


def test_a_declaration_no_workflow_uses_is_reported(tmp_path: Path) -> None:
    """The other direction: this file must not outlive the need it records."""
    audit = config_audit

    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "empty.yml").write_text("jobs: {}\n", encoding="utf-8")
    original = audit.WORKFLOWS
    try:
        audit.WORKFLOWS = workflows
        problems = audit.declaration_problems()
    finally:
        audit.WORKFLOWS = original

    assert len(problems) == len(REQUIRED_VARIABLES)
    assert all("no workflow reads it any more" in p for p in problems)


def test_every_declaration_says_what_to_do_about_it() -> None:
    """An entry that cannot be acted on is a note, not a check."""
    for name, requirement in REQUIRED_VARIABLES.items():
        assert requirement.when_unset in {"fails", "skips"}, name
        assert len(requirement.purpose) > 20, name
        # Long enough to be a procedure rather than a shrug.
        assert len(requirement.how_to_set) > 40, name


def test_an_empty_variable_counts_as_unset() -> None:
    """Because that is how every `if: vars.X != ''` in this repository reads it."""
    every = {name: "set" for name in REQUIRED_VARIABLES}
    assert unset_required_variables(every) == []

    blanked = dict(every, SITE_S3_BUCKET="   ")
    assert unset_required_variables(blanked) == ["SITE_S3_BUCKET"]

    del every["ASK_ALARM_RELAY_ROLE_ARN"]
    assert unset_required_variables(every) == ["ASK_ALARM_RELAY_ROLE_ARN"]


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    import os

    env = dict(os.environ)
    env.pop("REPO_VARIABLES", None)
    env.update(env_extra or {})
    completed = subprocess.run(  # noqa: S603 - this interpreter, on a tracked file
        [sys.executable, "tools/config_audit.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return completed.returncode, completed.stdout + completed.stderr


def test_reconcile_without_the_repositorys_variables_refuses_to_pass() -> None:
    """A run that could not look is never a run that found nothing.

    This is the fail-open the alarm relay was written to remove, and it would be
    an easy one to rebuild here: `--reconcile` with nothing to reconcile against
    could plausibly exit 0 and report every variable fine.
    """
    code, output = _run(["--reconcile"])
    assert code == 1
    assert "could not read the repository's variables" in output

    code, output = _run(["--reconcile"], {"REPO_VARIABLES": ""})
    assert code == 1


def test_reconcile_fails_on_a_variable_whose_workflow_fails_without_it() -> None:
    """Nothing set at all -- the repository's actual state on 2026-09-13."""
    code, output = _run(["--reconcile"], {"REPO_VARIABLES": json.dumps({})})
    assert code == 1
    assert "1 of 5 required repository variables are unset behind a workflow" in output
    assert "FAILS every run" in output
    assert "ASK_ALARM_RELAY_ROLE_ARN" in output
    assert "AlarmRelayRoleArn" in output, "the report must carry the owner's step"
    # The four deliberate ones are still reported, just not fatal.
    assert "deliberate unarmed state" in output
    assert "SITE_S3_BUCKET" in output


def test_a_deliberate_unarmed_state_is_reported_but_does_not_fail() -> None:
    """This check has to be able to go green, or nobody will read it.

    Four of the five variables are site-publish.yml's, unset on purpose behind an
    `if:` that skips because an unarmed deploy is not a broken build. A check that
    fails on those is red on a state nobody intends to change, and a permanently
    red workflow is read exactly as often as a silent one.
    """
    only_the_blocking_one_set = json.dumps(
        {
            name: "value"
            for name, requirement in REQUIRED_VARIABLES.items()
            if requirement.when_unset == "fails"
        }
    )
    code, output = _run(["--reconcile"], {"REPO_VARIABLES": only_the_blocking_one_set})
    assert code == 0, output
    assert "no workflow is failing for want of a repository variable" in output
    # Still said out loud, because unarmed and idle look identical from outside.
    assert "deliberate unarmed state" in output
    assert "SITE_S3_BUCKET" in output


def test_reconcile_passes_only_when_every_variable_is_set() -> None:
    """The positive control: this check is capable of going green."""
    everything = json.dumps({name: "value" for name in REQUIRED_VARIABLES})
    code, output = _run(["--reconcile"], {"REPO_VARIABLES": everything})
    assert code == 0, output
    assert "all 5 required repository variables are set" in output
