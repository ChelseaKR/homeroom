"""The `secret-scan` job must read every commit, not the commit it was handed.

Until 2026-09-13 the job was one step, `gitleaks/gitleaks-action@v3.0.0`, and
that action picks its scan range from the triggering event:

    push, N commits   gitleaks detect --log-opts=--no-merges --first-parent BASE^..HEAD
    push, 1 commit    gitleaks detect --log-opts=-1            <- exactly one commit
    pull_request      the pull request's own commits
    schedule /
    workflow_dispatch no --log-opts at all: the whole history

`ci.yml` triggers on `push` and `pull_request` and nothing else, so the two
events that walk the history never fired here. Every squash merge into `main` is
a one-commit push, which means the check read 1 of `main`'s 138 commits and
reported success. A credential added in one commit and deleted in the next was
invisible to it, in both lanes: the push lane saw only the deletion, and the
pull request lane saw a diff that nets to nothing.

`fetch-depth: 0` did not prevent that and could not. It decides how much history
`actions/checkout` puts on disk; how much of it gets read is decided by how the
scanner is invoked. This job had `fetch-depth: 0` the entire time it was reading
one commit, which is exactly the state a depth assertion cannot detect. So the
assertions below are about the *invocation*. The `fetch-depth: 0` assertion is
kept, as the necessary precondition it actually is and nothing more.

`make secret-scan-history` runs `gitleaks git .` with no `--log-opts`. With no
range, gitleaks walks `git log -p --full-history --all`: every commit on every
ref the checkout has, on every event. Measured here on 2026-09-13, that is 199
commits across all refs, 24 of them merges, and gitleaks reported exactly the 175
non-merge commits -- 874.22 MB in 3m26s. It is the same history pass
`make secret-scan` has always run locally, so CI and the local gate now run the
same command instead of two different ones.

Measured on a throwaway clone of this repository, with its remote removed: a
random, real-shaped AWS key planted in one commit and deleted in the next left
`gitleaks git . --log-opts=-1` exiting 0 while `gitleaks git .` exited 1.

Every assertion reads its file with comments stripped. Four conformance checks
elsewhere in this portfolio passed because they matched a tool name inside a
comment, and the comments here deliberately name both the action that was
removed and the flag that must not return.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"

_COMMENT = re.compile(r"(?m)^\s*#.*$|\s+#.*$")


def _ci_code() -> str:
    return _COMMENT.sub("", CI.read_text(encoding="utf-8"))


def _makefile_code() -> str:
    """The Makefile without its comments.

    Only whole-line comments are stripped: a `#` inside a recipe is the shell's,
    not make's, and cutting at it would corrupt the command being asserted on.
    """
    return "\n".join(
        line
        for line in MAKEFILE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _secret_scan_job() -> str:
    """The `secret-scan` job's own block of ci.yml, comments already gone."""
    code = _ci_code()
    start = code.index("\n  secret-scan:\n")
    rest = code[start + 1 :]
    following = re.search(r"(?m)^  [a-z][a-z0-9-]*:\s*$", rest[1:])
    return rest if following is None else rest[: following.start() + 1]


def _recipe(target: str) -> list[str]:
    """The recipe lines of one make target."""
    lines = _makefile_code().splitlines()
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(target)}\s*:(?!=)", line):
            body: list[str] = []
            for following in lines[index + 1 :]:
                if following.startswith("\t"):
                    body.append(following)
                elif following.strip():
                    break
            return body
    raise AssertionError(f"the Makefile has no `{target}` target")


def test_the_scanner_is_not_handed_a_range() -> None:
    """`gitleaks git .` with no range walks every ref, not a handed-over slice."""
    history = " ".join(_recipe("secret-scan-history"))
    assert "$(GITLEAKS) git . --no-banner --redact --exit-code 1" in history, (
        "`make secret-scan-history` no longer runs `gitleaks git .`. Whatever "
        f"replaces it must still walk the whole history, not a range: {history!r}"
    )
    assert "--log-opts" not in _makefile_code(), (
        "`--log-opts` scopes gitleaks to a commit range. A range chosen from the "
        "triggering event is how this check came to read 1 of 138 commits."
    )
    assert "--log-opts" not in _ci_code(), "see above: no range in the workflow either"


def test_the_event_driven_action_does_not_come_back() -> None:
    assert "gitleaks/gitleaks-action" not in _ci_code(), (
        "gitleaks/gitleaks-action picks its scan range from the triggering event "
        "and degrades to `--log-opts=-1` on a single-commit push, which is every "
        "squash merge into `main`."
    )


def test_the_secret_scan_job_runs_the_history_pass() -> None:
    """The job must reach the history walk, not merely exist."""
    job = _secret_scan_job()
    assert re.search(r"(?m)^\s*-?\s*run:\s*make secret-scan-history\s*$", job), (
        "the secret-scan job does not run `make secret-scan-history`, so nothing "
        f"in it walks the history:\n{job}"
    )


def test_checkout_still_fetches_the_history_the_scan_walks() -> None:
    """Necessary, not sufficient: without it there is nothing on disk to walk.

    This assertion is not evidence that the scan reads history. The job held
    this exact line through every run that read one commit. It is here so that
    removing it -- which would leave `gitleaks git .` walking the single commit
    `actions/checkout` fetched -- fails rather than passes quietly.
    """
    job = _secret_scan_job()
    assert re.search(r"(?m)^\s*fetch-depth:\s*0\s*$", job), (
        "`fetch-depth: 0` is gone from the secret-scan checkout. It is the "
        "precondition for a history scan; the invocation is what makes it one."
    )


def test_the_pinned_binary_is_checksum_verified() -> None:
    """The runner has no gitleaks, so one is fetched. It has to be the right one."""
    install = " ".join(_recipe("gitleaks-binary"))
    assert (
        "gitleaks_checksums.txt" in install and "sha256sum --check --strict" in install
    ), (
        "the gitleaks binary is fetched without verifying the checksum GitHub "
        f"publishes with the release: {install!r}"
    )
    assert re.search(r"(?m)^GITLEAKS_VERSION \?= \d+\.\d+\.\d+$", _makefile_code()), (
        "GITLEAKS_VERSION must pin an exact gitleaks release, not a range or a tag"
    )


def test_the_working_tree_pass_survived_the_split() -> None:
    """Splitting the target must not have dropped the pass CI cannot run.

    `make secret-scan` was one target running both passes. CI runs only the
    history half, because in CI the working tree is the committed tree. The
    other half still has to run locally, which means `secret-scan` still has to
    depend on it.
    """
    code = _makefile_code()
    match = re.search(r"(?m)^secret-scan\s*:(?!=)(.*)$", code)
    assert match, "the Makefile no longer has a `secret-scan` target"
    prerequisites = match.group(1).split()
    assert "secret-scan-history" in prerequisites, prerequisites
    assert "secret-scan-tree" in prerequisites, prerequisites
    tree = " ".join(_recipe("secret-scan-tree"))
    assert "$(GITLEAKS) dir $(SECRET_SCAN_TREE)" in tree, (
        "`make secret-scan` no longer scans the working tree, which is the one "
        "place an uncommitted key sits and the history pass is blind to."
    )
