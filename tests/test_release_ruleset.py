"""The committed tag ruleset must not be a lockout waiting to be applied.

`.github/rulesets/tags.json` is a tag ruleset with `update` and `deletion` over
`refs/tags/v*`. It is committed and never applied, and that combination is what
made it dangerous: nothing live has ever contradicted it, and until 2026-08-29
nothing in this repository contradicted it either, because the one thing that
read it required the defect.

`automation/check_release_ruleset.py` demanded `"bypass_actors": []` and the
profile carried the empty list to match. Applied as committed, that leaves
nobody -- the repository owner included -- able to delete or re-point a release
tag, including a bad one, and no break-glass path to undo it with. GitHub
answers 201 to such an apply, so nothing warns you; the same mistake elsewhere
in this portfolio took a sweep across eighteen repositories to unwind. Both
files had to move together, because correcting either one alone turns the build
red or leaves the profile wrong.

Correcting them once is not the fix, because they can regress. This module is
the fix: the empty list, and the four shapes an edit meant to correct it could
plausibly land in, are now test failures.

The checks run against the shipped validator, not a re-implementation of it, so
what is proved here is what the release workflow will actually enforce. Every
one is written to fail closed. The two ways a check like this passes vacuously
are a missing subject and an unparseable one, so a missing file and a malformed
file are both asserted to fail -- through `load_ruleset`, which returns errors
rather than raising, and again through `main`, so neither can be reported as
valid anywhere in the chain. A guard that passes when its subject is absent is
the defect it exists to catch.

CICD-15 and CI-CD-STANDARD §5.1 prescribe "empty bypass actors" and, where a
bypass exists, `bypass_mode: "pull_request"`. That standard is not vendored in
this repository, so there is nothing upstream to rewrite; the divergence from it
is deliberate and is recorded here and in the guard's own docstring. A bypass
that only works inside a pull request is no use when the pull request is what is
wedged, and a tag is neither updated nor deleted through one, so
`bypass_mode: "pull_request"` is one of the shapes rejected below.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "automation" / "check_release_ruleset.py"
RULESET = ROOT / ".github" / "rulesets" / "tags.json"


def _load_guard() -> Any:
    """Import the guard by path.

    `automation/` is not a package and is not on `pythonpath`, and the point of
    these tests is that the shipped script is what gets exercised.
    """
    spec = importlib.util.spec_from_file_location("check_release_ruleset", GUARD)
    assert spec is not None and spec.loader is not None, f"cannot load {GUARD}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()

OWNER_BYPASS = {
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "always",
}
"""The repository owner's standing bypass, confirmed against the live API.

`RepositoryRole` 5 is admin. `bypass_mode: always` rather than CICD-15's
`pull_request`, for the reason in this module's docstring. Restated here rather
than imported so that an edit to the guard's own constant is a test failure and
not a silently agreed change.
"""

VALID: dict[str, Any] = {
    "name": "protect-release-tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "rules": [{"type": "update"}, {"type": "deletion"}],
    "bypass_actors": [OWNER_BYPASS],
}
"""A profile the validator must accept, written out rather than read from disk.

Every rejection case below is this document with one field replaced, so a
rejection can only be attributed to that field.
"""


def bypass_errors(document: dict[str, Any]) -> list[str]:
    """The validator's complaints about `bypass_actors`, and nothing else."""
    return [e for e in guard.validate_ruleset(document) if "bypass_actors" in e]


def with_bypass(value: Any) -> dict[str, Any]:
    return {**VALID, "bypass_actors": value}


def without_bypass() -> dict[str, Any]:
    return {k: v for k, v in VALID.items() if k != "bypass_actors"}


def test_the_committed_profile_carries_the_owner_bypass_and_nothing_else() -> None:
    """The assertion the empty list has to fail.

    Read from disk with the guard's own loader, so a missing or unparseable file
    is reported here rather than skipped past.
    """
    document, errors = guard.load_ruleset(RULESET)
    assert errors == [], f"{RULESET} could not be read: {errors}"
    assert document is not None
    assert document["bypass_actors"] == [OWNER_BYPASS], (
        "applying .github/rulesets/tags.json as committed must leave the owner a "
        "break-glass path over refs/tags/v*, and exactly one actor may hold it; "
        f"it carries {document['bypass_actors']!r}"
    )


def test_the_committed_profile_passes_the_shipped_validator() -> None:
    """End-to-end positive control: the real file, the real guard, no errors."""
    document, errors = guard.load_ruleset(RULESET)
    assert errors == []
    assert document is not None
    assert guard.validate_ruleset(document) == []


def test_the_committed_profile_passes_the_command_line_entry_point() -> None:
    """`main` is what CI calls. It must agree with the functions tested above."""
    assert guard.main([str(RULESET)]) == 0


@pytest.mark.parametrize(
    "document",
    [
        with_bypass([]),
        without_bypass(),
        with_bypass({}),
        with_bypass(
            [{"actor_id": 1, "actor_type": "Integration", "bypass_mode": "always"}]
        ),
        with_bypass([{**OWNER_BYPASS, "bypass_mode": "pull_request"}]),
    ],
    ids=["empty", "absent", "wrong-type", "wrong-actor", "wrong-mode"],
)
def test_the_validator_rejects_every_losing_bypass_shape(
    document: dict[str, Any],
) -> None:
    """Five ways to lose the bypass, each of which GitHub would answer 201 to.

    `empty` is the one that was committed, and that this guard used to require.
    `wrong-mode` is CICD-15's prescription. The rest are the shapes a correcting
    edit could plausibly land in. The demand is exact equality, so a second
    actor alongside the owner fails here too; membership would have let it pass.
    """
    assert bypass_errors(document), f"{document['name']} profile should be refused"


def test_the_validator_accepts_the_correct_shape() -> None:
    """A positive control, so the test above cannot pass by refusing everything."""
    assert bypass_errors(with_bypass([OWNER_BYPASS])) == []
    assert guard.validate_ruleset(VALID) == []


def test_a_second_bypass_actor_is_refused() -> None:
    """The owner being present is not enough; the list is matched, not searched."""
    extra = {"actor_id": 2, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    assert bypass_errors(with_bypass([OWNER_BYPASS, extra]))


def test_a_missing_file_is_an_error_and_not_an_empty_document(
    tmp_path: Path,
) -> None:
    """`load_ruleset` returns errors rather than raising, so absence must be caught.

    A caller that ignored the error tuple would go on to validate `None`. The
    entry point is checked separately below for exactly that reason.
    """
    missing = tmp_path / "tags.json"
    document, errors = guard.load_ruleset(missing)
    assert document is None
    assert errors


def test_a_malformed_file_is_an_error_even_though_it_mentions_bypass_actors(
    tmp_path: Path,
) -> None:
    """The shape a `grep` for the string would have waved through.

    The bytes contain `bypass_actors` and the owner's actor id, and are not
    JSON. Nothing may read that as an answer.
    """
    malformed = tmp_path / "tags.json"
    malformed.write_text(
        '{"bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole",',
        encoding="utf-8",
    )
    assert "bypass_actors" in malformed.read_text(encoding="utf-8")
    document, errors = guard.load_ruleset(malformed)
    assert document is None
    assert errors


@pytest.mark.parametrize("case", ["missing", "malformed", "empty-bypass"])
def test_the_entry_point_refuses_what_the_loader_refuses(
    tmp_path: Path, case: str
) -> None:
    """No losing profile may reach a zero exit anywhere in the chain."""
    path = tmp_path / "tags.json"
    if case == "malformed":
        path.write_text('{"bypass_actors": [', encoding="utf-8")
    elif case == "empty-bypass":
        path.write_text(json.dumps(with_bypass([])), encoding="utf-8")
    assert guard.main([str(path)]) == 1


def test_the_signed_tag_message_asserts_the_bypass_the_profile_carries() -> None:
    """The signed message used to assert `empty`, which is what made it auditable.

    It has to keep naming what it is vouching for, and it must now name the
    owner's bypass. It is derived from the guard's constant, so the signature
    and the profile cannot drift apart.
    """
    message = guard.tag_message("v1.2.3", 42, "2026-08-29T00:00:00Z")
    line = next(
        ln for ln in message.splitlines() if ln.startswith("Tag-Ruleset-Bypass-Actors:")
    )
    assert line == "Tag-Ruleset-Bypass-Actors: RepositoryRole:5:always"


def test_the_hosted_parity_check_refuses_an_empty_hosted_bypass_list() -> None:
    """A hosted ruleset with no bypass is the live form of the same lockout.

    Nothing is applied to this repository today, so this path has no live
    subject; it is checked here so it cannot be the half that stayed wrong.
    """
    hosted = {**VALID, "bypass_actors": []}
    assert guard.validate_hosted_parity(VALID, hosted)
    assert guard.validate_hosted_parity(VALID, dict(VALID)) == []
