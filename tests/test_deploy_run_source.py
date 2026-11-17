"""The publishing workflows only follow a ci run that was a push to this repository.

`workflow_run` with `branches: [main]` matches a head branch by name, whichever
repository it lives in. Both publishing workflows therefore also require the ci
run's event to be `push` and its head repository to be this one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
REQUIRED = (
    "github.event.workflow_run.conclusion == 'success'",
    "github.event.workflow_run.event == 'push'",
    "github.event.workflow_run.head_repository.full_name == github.repository",
)


def _conditions(name: str) -> list[str]:
    """Every folded `if:` block in the workflow that mentions the ci run."""
    lines = (WORKFLOWS / name).read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if line.strip() != "if: >-":
            continue
        indent = len(line) - len(line.lstrip())
        body: list[str] = []
        for following in lines[i + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following.strip())
        block = " ".join(body)
        if "workflow_run" in block:
            blocks.append(block)
    return blocks


@pytest.mark.parametrize("name", ["pages.yml", "site-publish.yml"])
def test_publishing_follows_only_a_push_to_this_repository(name: str) -> None:
    blocks = _conditions(name)
    assert blocks, f"{name} has no condition on the ci run"
    for block in blocks:
        for term in REQUIRED:
            assert term in block, f"{name}: missing {term!r}"


def test_the_check_notices_a_missing_term() -> None:
    """Control: the same reading of a condition without the two new terms fails."""
    weak = "github.event_name == 'workflow_dispatch' || " + REQUIRED[0]
    assert not all(term in weak for term in REQUIRED)
