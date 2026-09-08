"""How much of the live site the sentinel compares, and which parts.

`tools/verify_live_site.py` fetched every published file until 2026-09-05. That
was eight files. Publishing all 10,534 schools made it 21,076, so the daily run
would have pulled 836MB from the origin every morning and taken hours doing it.

The comparison is bounded now, and bounding a sentinel is exactly the kind of
change that can quietly turn it into nothing -- the failure mode its own module
docstring calls out. So what stays exhaustive, what rotates, and the fact that
rotation reaches every page are checked here rather than assumed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "verify_live_site", ROOT / "tools" / "verify_live_site.py"
)
assert SPEC and SPEC.loader
sentinel = importlib.util.module_from_spec(SPEC)
# Registered before it is executed: the module defines a dataclass, and
# `@dataclass` resolves its own module out of `sys.modules` while running.
sys.modules[SPEC.name] = sentinel
SPEC.loader.exec_module(sentinel)

SPINE = [
    "CNAME",
    "index.html",
    "robots.txt",
    "sitemap.xml",
    "social-card.en.png",
    "social-card.es.png",
    "ask/00000000000001.en.html",
    "ask/00000000000001.es.html",
]


def corpus(schools: int, browse: int = 0) -> list[str]:
    """A published tree of `schools` school pages, `browse` county and district
    pages, and the usual spine."""
    pages = [
        f"{10000000000000 + n}.{loc}.html"
        for n in range(schools)
        for loc in ("en", "es")
    ]
    pages += [
        f"{kind}/{n:05d}.{loc}.html"
        for kind in ("county", "district")
        for n in range(browse)
        for loc in ("en", "es")
    ]
    return sorted(SPINE + pages)


def schools_in(selected: list[str]) -> list[str]:
    return [r for r in selected if sentinel.rotates(r)]


def test_what_counts_as_a_school_page() -> None:
    """The split decides what rotates, so a miscount here silences the sentinel."""
    assert sentinel.is_school_page("57726786056246.en.html")
    assert not sentinel.is_school_page("index.html")
    assert not sentinel.is_school_page("ask/57726786056246.en.html")
    assert not sentinel.is_school_page("robots.txt")
    assert not sentinel.is_school_page("social-card.en.png")


def test_the_browse_pages_rotate_rather_than_sitting_in_the_spine() -> None:
    """2,234 of them, and they are not addressed like a school page.

    `is_school_page` asks for a name with no directory in it, which every county
    and district page fails. Left at that they would have counted as spine and
    been fetched in full every morning, quietly undoing the bound this module
    exists to keep -- the sentinel would still have passed, just slowly and at
    the origin's expense.
    """
    assert sentinel.rotates("county/19.en.html")
    assert sentinel.rotates("district/1964733.es.html")
    assert not sentinel.rotates("ask/57726786056246.en.html")
    assert not sentinel.rotates("index.html")
    assert not sentinel.rotates("sitemap.xml")

    relatives = corpus(200, browse=50)
    selected = sentinel.comparison_set(relatives, 20, 2)
    assert len(schools_in(selected)) == 20
    assert len(selected) == 20 + len(SPINE)


def test_the_spine_is_compared_on_every_run() -> None:
    """A stale deploy shows up in the index and the sitemap first."""
    relatives = corpus(500)
    for offset in range(6):
        selected = sentinel.comparison_set(relatives, 20, offset)
        for path in SPINE:
            assert path in selected, (path, offset)


def test_a_run_is_bounded_by_the_sample() -> None:
    relatives = corpus(500)
    selected = sentinel.comparison_set(relatives, 20, 3)
    assert len(schools_in(selected)) == 20
    assert len(selected) == 20 + len(SPINE)


def test_consecutive_runs_do_not_repeat_the_same_school_pages() -> None:
    """Rotation is the whole reason a bounded run is still a real check."""
    relatives = corpus(500)
    first = set(schools_in(sentinel.comparison_set(relatives, 20, 7)))
    second = set(schools_in(sentinel.comparison_set(relatives, 20, 8)))
    assert first and second
    assert not (first & second)


def test_rotation_reaches_every_school_page() -> None:
    """Bounded per run, exhaustive over time; otherwise pages are never checked."""
    relatives = corpus(50)
    total = len(schools_in(relatives))
    seen: set[str] = set()
    for offset in range(total):  # more than enough windows to wrap
        seen |= set(schools_in(sentinel.comparison_set(relatives, 7, offset)))
    assert seen == set(schools_in(relatives))


def test_a_same_day_rerun_compares_the_same_window() -> None:
    """The retry loop looks again for a deploy to settle, not somewhere else."""
    relatives = corpus(500)
    assert sentinel.comparison_set(relatives, 20, 11) == sentinel.comparison_set(
        relatives, 20, 11
    )


def test_sample_zero_compares_the_whole_tree() -> None:
    """The by-hand sweep after a publish, and the old behaviour, still reachable."""
    relatives = corpus(50)
    assert sentinel.comparison_set(relatives, 0, 1) == sorted(relatives)


def test_a_sample_wider_than_the_corpus_compares_all_of_it() -> None:
    """Asking for more than exists is a full sweep, not a wrapped and doubled one."""
    relatives = corpus(10)
    selected = sentinel.comparison_set(relatives, 10_000, 4)
    assert selected == sorted(relatives)
    assert len(selected) == len(set(selected))


# ----------------------------------------------------------------------------------
# The workflow step that runs the sentinel, executed under the shell that ships
# ----------------------------------------------------------------------------------
#
# A sentinel is only as good as the step that reports its verdict, and that step is
# shell, in YAML, run by a shell nobody names. GitHub's default for a `run:` block
# that declares no `shell:` is `bash -e {0}` -- errexit ON -- and `set -uo pipefail`
# does NOT turn it off (that needs `set +e`). Reading the body under plain `bash`
# gives the opposite answer on the rows that matter, so this lifts the real body out
# of the YAML, runs it under `bash -e` with both commands stubbed, and asserts the
# step still declares no `shell:` -- or the fixture quietly stops being what ships.
#
# Measured against origin/main on 2026-09-08, before the fix:
#
#   verify_rc  ls-remote   step exit
#   0          ok          0
#   0          fails       128   <- an already-green run reddened by a read it did
#                                   not need, with git's own code
#   1          ok          1
#   1          fails       1     <- the deploy-race warning is UNREACHABLE: errexit
#                                   ends the step at the python line, so `verify_rc`
#                                   is never assigned and the excuse never runs in
#                                   the one case it was written for
#   4          fails       4     <- same, for "could not run"

WORKFLOW = ROOT / ".github" / "workflows" / "live-integrity.yml"
STEP_NAME = "Compare the live surface with what this checkout publishes"


def _step_lines() -> list[str]:
    """The lines of the one step this module is about, read as bytes, not as YAML.

    A YAML parser would be tidier and would need a dependency this repository does
    not have. It would also read `shell: bash` and `shell:  bash` the same, which is
    fine, and would let a `<<:` merge or an anchor hide the key, which is not. So the
    step is sliced out of the file textually and both checks below read those lines.
    """
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^\s*-\s", line)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = lines[start:end]
        if any(f"name: {STEP_NAME}" in line for line in block):
            return block
    raise AssertionError(f"no step named {STEP_NAME!r} in {WORKFLOW.name}")


def _step_body() -> str:
    """The `run:` block scalar, dedented exactly as the runner would receive it."""
    block = _step_lines()
    for index, line in enumerate(block):
        if line.strip() == "run: |":
            indent = len(line) - len(line.lstrip())
            body = []
            for following in block[index + 1 :]:
                if (
                    following.strip()
                    and (len(following) - len(following.lstrip())) <= indent
                ):
                    break
                body.append(following)
            return textwrap.dedent("\n".join(body)) + "\n"
    raise AssertionError("the step no longer carries a `run: |` block")


def test_the_step_declares_no_shell_so_the_harness_below_is_what_ships() -> None:
    """The fixture pins `bash -e`; this pins that `bash -e` is what GitHub will use.

    Without this the harness can go on passing while the shipped step runs under a
    different shell, which is the failure mode that makes a lifted-out `run:` body a
    worse test than none.
    """
    lines = _step_lines()
    named = [line for line in lines if line.strip().startswith("shell:")]
    assert not named, (
        "the step now names a shell, so GitHub no longer runs it with `bash -e {0}` "
        f"and the harness below is testing something else: {named}"
    )
    assert _step_body().strip(), "the step carries no body"


def _harness(
    tmp_path: Path,
    *,
    verify_rc: int,
    ls_remote_fails: bool = False,
    remote_moved: bool = False,
) -> tuple[int, str]:
    """Run the shipped step body under the shell GitHub uses, with both tools stubbed.

    Returns the exit code AND the output. On the row that actually separates the two
    bodies they agree on the code and differ only in whether the warning was printed,
    so a harness that returned the code alone would report a control as having fired
    when it had not.
    """
    body = tmp_path / "body.sh"
    body.write_text(_step_body(), encoding="utf-8")

    binaries = tmp_path / "bin"
    binaries.mkdir()
    head = "a" * 40
    remote = "b" * 40 if remote_moved else head
    (binaries / "git").write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        f'  rev-parse) echo "{head}";;\n'
        "  ls-remote)\n"
        '    if [ "${LS_REMOTE_FAILS:-0}" = 1 ]; then echo "fatal" >&2; exit 128; fi\n'
        f'    printf "{remote}\\trefs/heads/main\\n";;\n'
        "esac\n",
        encoding="utf-8",
    )
    (binaries / "python3").write_text(
        '#!/bin/bash\nexit "${VERIFY_RC:-0}"\n', encoding="utf-8"
    )
    for name in ("git", "python3"):
        path = binaries / name
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    environment = dict(os.environ)
    environment["PATH"] = f"{binaries}:{environment['PATH']}"
    environment["VERIFY_RC"] = str(verify_rc)
    environment["LS_REMOTE_FAILS"] = "1" if ls_remote_fails else "0"
    bash = shutil.which("bash")
    assert bash, "no bash on this machine, so this harness would prove nothing"
    completed = subprocess.run(  # noqa: S603 - a fixture script we just wrote
        [bash, "-e", str(body)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.returncode, completed.stdout + completed.stderr


@pytest.mark.parametrize("ls_remote_fails", [False, True])
def test_a_passing_sentinel_is_green_whatever_the_remote_read_does(
    tmp_path: Path, ls_remote_fails: bool
) -> None:
    """The 128 row. A read the step does not need must not be able to fail the run.

    With the remote read taken unconditionally, `git`'s own 128 propagated under
    errexit and a green sentinel reported as a broken one.
    """
    assert _harness(tmp_path, verify_rc=0, ls_remote_fails=ls_remote_fails)[0] == 0


@pytest.mark.parametrize("verify_rc", [sentinel.EXIT_DIFFERS, sentinel.EXIT_CANNOT_RUN])
def test_a_failing_sentinel_still_reaches_the_deploy_race_excuse(
    tmp_path: Path, verify_rc: int
) -> None:
    """The unreachable-excuse row: the remote agrees, so the verdict stands.

    Reaching this at all is the fix. Before it, errexit ended the step at the
    `python3` line and nothing below ever ran.
    """
    assert _harness(tmp_path, verify_rc=verify_rc)[0] == verify_rc


def test_a_failing_remote_read_reports_the_difference_rather_than_excusing_it(
    tmp_path: Path,
) -> None:
    """Failing open on the excuse would turn a network blip into a suppressed verdict.

    The other direction is the one to refuse: if the remote cannot be re-read, a
    concurrent deploy cannot be ruled out, and the honest answer is the difference the
    sentinel actually found -- not silence.
    """
    code, output = _harness(
        tmp_path, verify_rc=sentinel.EXIT_DIFFERS, ls_remote_fails=True
    )
    assert code == sentinel.EXIT_DIFFERS, output
    assert "could not re-read origin/main" in output


@pytest.mark.parametrize("verify_rc", [sentinel.EXIT_DIFFERS, sentinel.EXIT_CANNOT_RUN])
def test_a_genuine_deploy_race_is_excused_and_says_so(
    tmp_path: Path, verify_rc: int
) -> None:
    """The ONE row that separates the two bodies, and the reason this file exists.

    The sentinel found a difference AND the remote has moved: that is the deploy
    working, and the step is meant to warn and pass. Under the old body errexit ended
    the step at the `python3` line, so `verify_rc` was never assigned and this block
    never ran -- it exited 1 with no annotation, in exactly the situation it was
    written to handle.

    The first control on this fix caught only the 128 row, because the old and new
    bodies produce the SAME exit code when the remote agrees. This is the case where
    they differ, and it is asserted on the annotation as well as the code.
    """
    code, output = _harness(tmp_path, verify_rc=verify_rc, remote_moved=True)
    assert code == 0, output
    assert "::warning::main moved to" in output
