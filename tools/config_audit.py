"""Every repository variable a workflow depends on, declared in one place.

On 2026-09-12 #116 merged `ask-alarm-relay.yml`, a daily workflow that reads the
ask service's CloudWatch alarm through an OIDC role named by the repository
variable `ASK_ALARM_RELAY_ROLE_ARN`. The variable was never set, because setting
it needs a stack redeploy the merge could not perform. The workflow did exactly
what it was written to do -- it failed loudly, with a message naming both owner
steps -- and it has done so every night since, in an eight-second run.

Nothing in the repository noticed. The requirement was created by a merge and
recorded only inside the file that needed it, so the only signal that a merge had
shipped a workflow which *cannot run* was a scheduled red build arriving by email
the next morning. A gate that reports a finding nobody connects back to the
change that caused it is a gate at half strength.

`site-publish.yml` is the same condition in its quieter form. It needs four
variables, none of them set, and it is written to *skip* rather than fail when
they are missing -- deliberately, and the comment there argues it well: an
unarmed deploy is not a broken build. The cost is that being unarmed looks
exactly like having nothing to do. Every run of it has skipped.

So there are two shapes of the same fact in this repository, one shouting nightly
and one silent, and no single place that says which repository variables the
workflows need or what happens when each is missing. This is that place.

Two checks, and the split between them is deliberate.

The first is offline and is a merge gate (`make config-audit`, reached from
`verify-ci`). It reads the workflows and this file and holds them to each other:
a `vars.X` no entry here explains fails the build that introduces it, and an
entry here that no workflow uses any more fails too. It decides nothing about the
live repository, needs no token, and so it can sit inside `make verify` without
making the local gate weaker than CI.

The second reconciles this file against the repository's actual variables and
needs to be told what they are, which means reading settings this repository
cannot read from a test. It runs in `.github/workflows/required-configuration.yml`
under `toJSON(vars)`, and like the live-integrity sentinel, the source-freshness
check and the alarm relay it is NOT a required check and `make verify` does not
call it -- the same reason those three give: a stage that reads outside the
repository cannot be part of a gate that claims to be reproducible offline.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# `vars.NAME`, in an expression or an `if:`. Restricted to the shape GitHub
# actually accepts for a variable name so that prose in a comment cannot be
# mistaken for a reference -- though comments are stripped before this runs
# anyway, for the reason `_workflow_source` gives.
VARS_REFERENCE = re.compile(r"\bvars\.([A-Z][A-Z0-9_]*)\b")


@dataclass(frozen=True)
class Requirement:
    """One repository variable, and what the repository loses without it."""

    purpose: str
    # "fails" or "skips": what the workflow does when this variable is unset.
    # The distinction is the whole point of recording it. A workflow that fails
    # is telling somebody; a workflow that skips is not, and an unset variable
    # behind a skip can stand for months looking like an idle repository.
    when_unset: str
    how_to_set: str


# Every repository variable referenced by any workflow. Adding a `vars.X` to a
# workflow without adding it here fails `make config-audit`, which is the point:
# the requirement becomes visible in the diff that creates it instead of in a
# scheduled build the following morning.
REQUIRED_VARIABLES: dict[str, Requirement] = {
    "ASK_ALARM_RELAY_ROLE_ARN": Requirement(
        purpose=(
            "the read-only OIDC role ask-alarm-relay.yml assumes to read the ask "
            "service's CloudWatch alarm state and its SNS topic's subscriber count"
        ),
        when_unset="fails",
        how_to_set=(
            'Add {"ParameterKey": "AlarmRelayRepository", "ParameterValue": '
            '"ChelseaKR/homeroom"} to the gitignored deploy/ask/params.json and '
            "redeploy deploy/ask/template.yaml, which creates AlarmRelayRole; then "
            "set this variable to the stack's AlarmRelayRoleArn output. "
            "deploy/ask/README.md, 'Still open', carries both steps."
        ),
    ),
    "SITE_S3_BUCKET": Requirement(
        purpose="the bucket site-publish.yml syncs the committed site/ tree into",
        when_unset="skips",
        how_to_set=(
            "Set to the SiteBucketName output of the deploy/site stack. "
            "deploy/site/README.md carries the deploy."
        ),
    ),
    "SITE_CLOUDFRONT_DISTRIBUTION_ID": Requirement(
        purpose="the distribution site-publish.yml invalidates after a sync",
        when_unset="skips",
        how_to_set="Set to the DistributionId output of the deploy/site stack.",
    ),
    "SITE_PUBLISH_ROLE_ARN": Requirement(
        purpose="the OIDC role site-publish.yml assumes to write to the bucket",
        when_unset="skips",
        how_to_set="Set to the PublishRoleArn output of the deploy/site stack.",
    ),
    "SITE_AWS_REGION": Requirement(
        purpose="the region site-publish.yml addresses the bucket in",
        when_unset="skips",
        how_to_set="Set to the region the deploy/site stack was applied in.",
    ),
}


def _workflow_source(path: Path) -> str:
    """One workflow with comment-only lines dropped.

    A comment that mentions `vars.X` is prose about the file, not a dependency of
    it -- `ask-alarm-relay.yml` contains exactly that, arguing against the
    `if: vars.X != ''` shape -- and a checker that reads comments as code is a
    checker that passes on a mention. `tests/test_ci_parity.py` strips comments
    before reading ci.yml for the same reason.
    """
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def referenced_variables() -> dict[str, set[str]]:
    """Every `vars.NAME` any workflow reads, mapped to the files reading it."""
    found: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for name in VARS_REFERENCE.findall(_workflow_source(path)):
            found.setdefault(name, set()).add(path.name)
    return found


def declaration_problems() -> list[str]:
    """Where the workflows and this file disagree about what is needed."""
    referenced = referenced_variables()
    problems = []

    for name in sorted(set(referenced) - set(REQUIRED_VARIABLES)):
        where = ", ".join(sorted(referenced[name]))
        problems.append(
            f"{where} reads vars.{name}, which REQUIRED_VARIABLES in "
            f"tools/config_audit.py does not explain. A workflow that depends on "
            f"repository configuration nobody has written down is a workflow that "
            f"can be merged unable to run: add an entry saying what it is for, "
            f"whether the workflow fails or skips without it, and the exact steps "
            f"that set it."
        )

    for name in sorted(set(REQUIRED_VARIABLES) - set(referenced)):
        problems.append(
            f"REQUIRED_VARIABLES declares {name}, but no workflow reads it any "
            f"more. Remove the entry, so this file cannot start asking the owner "
            f"to configure things the repository stopped needing."
        )

    for name, requirement in sorted(REQUIRED_VARIABLES.items()):
        if requirement.when_unset not in {"fails", "skips"}:
            problems.append(
                f"{name} records when_unset={requirement.when_unset!r}; it must be "
                f"'fails' or 'skips', because the difference between a workflow "
                f"that tells somebody and one that quietly does nothing is the "
                f"thing this file exists to keep visible."
            )

    return problems


def unset_required_variables(configured: dict[str, str]) -> list[str]:
    """Which declared variables the live repository has not got.

    `configured` is `toJSON(vars)` as GitHub renders it: every repository
    variable visible to the workflow, by name. A variable set to the empty
    string counts as unset, because that is how every `if: vars.X != ''` in this
    repository already reads it.
    """
    return [
        name
        for name in sorted(REQUIRED_VARIABLES)
        if not configured.get(name, "").strip()
    ]


def _report_unset(unset: list[str]) -> str:
    lines = []
    for name in unset:
        requirement = REQUIRED_VARIABLES[name]
        consequence = (
            "its workflow fails every run until this is set"
            if requirement.when_unset == "fails"
            else "its workflow skips silently, so nothing reports this"
        )
        lines.append(f"  {name} -- {requirement.purpose}.")
        lines.append(f"    Unset: {consequence}.")
        lines.append(f"    To set: {requirement.how_to_set}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    problems = declaration_problems()
    if problems:
        for problem in problems:
            print(f"::error::{problem}", file=sys.stderr)
        return 1
    print(
        f"config-audit: {len(REQUIRED_VARIABLES)} repository variables declared, "
        f"and every vars.* the workflows read is one of them."
    )

    if "--reconcile" not in argv:
        return 0

    # Reconciliation is opt-in and, when asked for, refuses to be silent. An
    # empty or absent REPO_VARIABLES is not "nothing is unset": it is a run that
    # could not look, which is the failure mode the alarm relay was written to
    # remove and is not going to be rebuilt here.
    raw = os.environ.get("REPO_VARIABLES")
    if raw is None or not raw.strip():
        print(
            "::error::--reconcile was asked for but REPO_VARIABLES is not in the "
            "environment, so this run could not read the repository's variables "
            "and is not evidence that they are set. In a workflow, pass "
            "REPO_VARIABLES: ${{ toJSON(vars) }}.",
            file=sys.stderr,
        )
        return 1
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"::error::REPO_VARIABLES is not JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(configured, dict):
        print(
            f"::error::REPO_VARIABLES is {type(configured).__name__}, not the "
            f"object toJSON(vars) produces.",
            file=sys.stderr,
        )
        return 1

    unset = unset_required_variables({k: str(v) for k, v in configured.items()})
    if not unset:
        print(
            f"config-audit: all {len(REQUIRED_VARIABLES)} required repository "
            f"variables are set."
        )
        return 0

    # Only a variable whose workflow FAILS without it turns this run red.
    #
    # The obvious version of this check fails on any unset variable, and it would
    # be wrong here for a reason worth writing down: four of the five are
    # site-publish.yml's, deliberately unset, behind an `if:` that skips because
    # an unarmed deploy is not a broken build. Failing on those makes this check
    # red on a state nobody intends to change, which is a check that cannot pass
    # -- and a permanently red workflow is read exactly as often as a silent one,
    # which is the failure the alarm relay's own comments describe when they
    # refuse to file a duplicate issue every night.
    #
    # So the deliberate ones are reported and not fatal, and the ones burning a
    # scheduled run every day are fatal. This check can go green, and the day it
    # does will be the day the relay can reach somebody.
    blocking = [n for n in unset if REQUIRED_VARIABLES[n].when_unset == "fails"]
    unarmed = [n for n in unset if n not in blocking]

    if unarmed:
        print(
            f"config-audit: {len(unarmed)} of {len(REQUIRED_VARIABLES)} required "
            f"repository variables are unset behind a workflow that skips rather "
            f"than fails. That is a deliberate unarmed state, not a fault, and it "
            f"is reported here because unarmed and idle look identical from "
            f"outside:\n" + _report_unset(unarmed)
        )

    if blocking:
        print(
            f"::error::{len(blocking)} of {len(REQUIRED_VARIABLES)} required "
            f"repository variables are unset behind a workflow that FAILS every "
            f"run until they are set:\n" + _report_unset(blocking),
            file=sys.stderr,
        )
        return 1

    print("config-audit: no workflow is failing for want of a repository variable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
