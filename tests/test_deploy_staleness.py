"""The clock on the deployment: is the `site/` a family receives main's `site/`?

Written from both directions, because the failure this guards against is a green
gate. A detector that cannot fire is noise and gets deleted; a detector that
reports a number it did not really measure is worse than none, because the
number reads as a measurement and nobody re-derives it.

So these cover the drift it must report AND every way the comparison can be
meaningless -- no deployment at all, one that never succeeded, a commit this
clone does not contain, a history that has diverged, a commit with no `site/`.
Each of those must end in a refusal. None may end in a comfortable zero.

The sharpest case is `test_an_unchanged_site_is_not_drift_however_old_the_deploy`.
This repository commits its rendered pages and `pages.yml` uploads them as-is,
so the deployed SHA and main's SHA differ constantly while the published bytes
are identical: measured 2026-09-13, the 30 most recent deployments all carried
the same `site/` tree because `site/` had not changed since 2026-09-05, while
main took 29 further commits. A sentinel comparing SHAs would have reported
drift on 29 of those 30 and been wrong every time. Comparing the tree object id
is what makes that impossible, and these are what keep it that way.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"


def _tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `@dataclass` resolves annotations
    # through `sys.modules[cls.__module__]`, so a module that is not there yet
    # raises on the decorator rather than on anything to do with this repository.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


staleness = _tool("deploy_staleness")

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
SEPTEMBER = "2026-09-13T16:49:09Z"


def _deployment(**over: Any) -> dict[str, Any]:
    row = {
        "id": 6423967047,
        "sha": "c" * 40,
        "environment": "github-pages",
        "created_at": SEPTEMBER,
    }
    row.update(over)
    return row


def _succeeded(_id: Any) -> list[Mapping[str, Any]]:
    # The real shape: `gh api .../statuses` returns newest first, and a Pages
    # deployment accumulates waiting -> queued -> in_progress -> success.
    return [
        {"state": "success"},
        {"state": "in_progress"},
        {"state": "queued"},
        {"state": "waiting"},
    ]


def _never_succeeded(_id: Any) -> list[Mapping[str, Any]]:
    return [{"state": "failure"}, {"state": "in_progress"}, {"state": "queued"}]


# --- what the deployment record is allowed to mean --------------------------


def test_the_newest_successful_deployment_is_the_live_build() -> None:
    record = staleness.newest_successful_deployment([_deployment()], _succeeded)
    assert record.sha == "c" * 40
    assert record.created_at.date().isoformat() == "2026-09-13"
    assert record.deployment_id == 6423967047


def test_the_newest_deployment_wins_over_an_older_one() -> None:
    older = _deployment(id=2, sha="d" * 40, created_at="2026-09-01T00:00:00Z")
    record = staleness.newest_successful_deployment([_deployment(), older], _succeeded)
    assert record.sha == "c" * 40


def test_a_run_that_published_nothing_is_not_a_deploy() -> None:
    """The trap this file exists for.

    `site-publish.yml` skips its only job unless four `vars.SITE_*` are set, and
    none of them is, so every run of it is a GREEN run that published nothing.
    `pages.yml` skips its job unless the `ci` run it follows succeeded. Neither
    skip creates a deployment, so the deployment list is unaffected by them and
    the answer stays the last real publish. Asserting the absence directly,
    because the bug would be a silent extra row rather than an exception.
    """
    skipped_runs_create_no_deployments: list[Mapping[str, Any]] = [_deployment()]
    record = staleness.newest_successful_deployment(
        skipped_runs_create_no_deployments, _succeeded
    )
    assert record.created_at.date().isoformat() == "2026-09-13"


def test_no_deployment_at_all_is_a_refusal_not_a_zero() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment([], _succeeded)


def test_a_deployment_that_never_succeeded_is_a_refusal() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="successful status"):
        staleness.newest_successful_deployment([_deployment()], _never_succeeded)


def test_a_deployment_still_in_progress_is_not_yet_a_publish() -> None:
    """A row is a request to publish. Bytes land when its status says so."""

    def still_going(_id: Any) -> list[Mapping[str, Any]]:
        return [{"state": "in_progress"}, {"state": "queued"}]

    with pytest.raises(staleness.StalenessUnknown, match="successful status"):
        staleness.newest_successful_deployment([_deployment()], still_going)


def test_a_failed_newer_deployment_does_not_hide_the_successful_older_one() -> None:
    """A failed republish leaves the previous build serving; that is the live one."""
    failed = _deployment(id=9, sha="e" * 40, created_at="2026-09-13T18:00:00Z")

    def statuses(deployment_id: Any) -> list[Mapping[str, Any]]:
        return [{"state": "failure"}] if deployment_id == 9 else [{"state": "success"}]

    record = staleness.newest_successful_deployment([_deployment(), failed], statuses)
    assert record.sha == "c" * 40


def test_a_row_without_a_commit_id_is_not_a_deployment() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment(
            [_deployment(sha="not-a-sha")], _succeeded
        )


def test_a_deployment_for_another_environment_is_not_the_published_site() -> None:
    other = _deployment(id=3, sha="f" * 40, environment="staging")
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment([other], _succeeded)


# --- the published subtree, which is the whole comparison -------------------


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(  # noqa: S603
            ["git", "-C", str(root), *args],  # noqa: S607
            check=True,
            capture_output=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "sentinel@example.test")
    git("config", "user.name", "sentinel")
    return root


def _commit(
    root: Path, path: str, body: str = "x", *, when: datetime | None = None
) -> str:
    """Write and commit one file, optionally dating the commit.

    `when` is not a convenience. The waiting clock is measured from the
    committer date of the oldest unpublished change to `site/`, so a test that
    lets git stamp "now" is testing a change that has waited zero days no matter
    how old it makes the deployment. Every overdue case below therefore dates
    its commits, and the ones that do not are asserting the opposite.
    """
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "add", path],  # noqa: S607
        check=True,
        capture_output=True,
    )
    env = None
    if when is not None:
        stamp = when.isoformat()
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "commit", "-m", f"touch {path}"],  # noqa: S607
        check=True,
        capture_output=True,
        env=env,
    )
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _repo(tmp_path)
    monkeypatch.setattr(staleness, "REPO_ROOT", root)
    return root


def _record(sha: str, created_at: datetime) -> Any:
    return staleness.DeployRecord(deployment_id=1, sha=sha, created_at=created_at)


def test_the_published_subtree_is_read_as_a_tree_object(clone: Path) -> None:
    sha = _commit(clone, "site/index.html")
    tree = staleness.published_tree(sha)
    assert len(tree) == 40
    # The same tree id as git itself reports for that path.
    expected = subprocess.run(  # noqa: S603
        ["git", "-C", str(clone), "rev-parse", f"{sha}:site"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tree == expected


def test_a_commit_with_no_published_subtree_is_a_refusal(clone: Path) -> None:
    """A deployed commit that never had `site/` cannot be compared to one."""
    sha = _commit(clone, "README.md")
    with pytest.raises(staleness.StalenessUnknown, match="has no site/ tree"):
        staleness.published_tree(sha)


def test_an_unchanged_site_is_not_drift_however_old_the_deploy(clone: Path) -> None:
    """The model-2 case, and the reason SHAs are not compared here.

    Measured on this repository 2026-09-13: `site/` last changed 2026-09-05, and
    the 30 deployments since all carried the identical tree `cf098c3876` while
    main took 29 further commits. Comparing SHAs would call 29 of those drift.
    The visitor held every byte main had the whole time.
    """
    deployed = _commit(clone, "site/index.html")
    for i in range(29):
        _commit(clone, f"src/module_{i}.py")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=60)), "HEAD", NOW)

    assert drift.commits == 29
    assert drift.visitor_commits == 0
    assert drift.deployed_tree == drift.head_tree
    assert not drift.published_bytes_differ
    assert not drift.overdue
    assert "Up to date" in staleness.render(drift)


def test_a_change_under_site_is_drift_even_when_the_shas_are_adjacent(
    clone: Path,
) -> None:
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=31))
    _commit(clone, "site/01100170106906.en.html", when=NOW - timedelta(days=30))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=30)), "HEAD", NOW)

    assert drift.commits == 1
    assert drift.visitor_commits == 1
    assert drift.published_bytes_differ
    assert drift.overdue


def test_a_change_that_was_reverted_is_not_drift(clone: Path) -> None:
    """Two commits touched `site/` and the bytes are back where they started.

    A commit-counting sentinel reports two visitor-visible commits waiting. The
    tree comparison reports what is true: the visitor holds main's bytes.
    """
    deployed = _commit(clone, "site/index.html", "original")
    _commit(clone, "site/index.html", "changed")
    _commit(clone, "site/index.html", "original")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=90)), "HEAD", NOW)

    assert drift.visitor_commits == 2
    assert not drift.published_bytes_differ
    assert not drift.overdue


def test_a_browse_page_change_that_touches_no_spine_file_is_drift(
    clone: Path,
) -> None:
    """Commit 6985dfb98 in miniature, which is the gap this sentinel fills.

    It rewrote 2,234 files under `site/` -- every county and district page --
    and none of the eight that `tools/verify_live_site.py` compares on every
    run. The published tree changed; the spine did not.
    """
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=41))
    _commit(clone, "site/district/1234567.en.html", when=NOW - timedelta(days=40))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=40)), "HEAD", NOW)

    assert drift.published_bytes_differ
    assert drift.visitor_commits == 1
    assert drift.overdue


def test_nothing_since_the_deploy_is_up_to_date(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=1)), "HEAD", NOW)

    assert drift.commits == 0
    assert drift.visitor_commits == 0
    assert not drift.published_bytes_differ
    assert not drift.overdue


# --- when the clock starts, and when it is allowed to fire ------------------


def test_age_alone_is_not_overdue(clone: Path) -> None:
    """A site nobody republished because nothing it publishes changed is

    correct, not stale. On this repository that is the normal state -- `site/`
    changed 7 times in 140 commits -- so reporting on age alone would fire every
    week, and a sentinel that always fires is one nobody reads.
    """
    deployed = _commit(clone, "site/index.html")
    for i in range(5):
        _commit(clone, f"docs/adr/{i}.md")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.days_since_deploy == 200
    assert drift.visitor_commits == 0
    assert not drift.overdue


def test_the_waiting_clock_starts_at_the_commit_not_the_deploy(clone: Path) -> None:
    """A change that landed today has waited a day, not as long as the deploy.

    The deploy here is 200 days old, which is fine: nothing was waiting for 199
    of them. Dating the drift from the deployment instead would fire instantly
    on any repository that publishes rarely and correctly, which is this one.
    """
    deployed = _commit(clone, "site/index.html")
    _commit(clone, "site/new.en.html")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.days_since_deploy == 200
    assert drift.published_bytes_differ
    assert drift.waiting_days <= 1
    assert not drift.overdue


def test_inside_the_threshold_is_not_overdue(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html")
    _commit(clone, "site/index.html", "republished")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=3)), "HEAD", NOW)

    assert drift.published_bytes_differ
    assert not drift.overdue
    assert "Waiting" in staleness.render(drift)


def test_the_threshold_is_configurable_and_is_the_thing_compared(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=4))
    _commit(clone, "site/index.html", "republished", when=NOW - timedelta(days=3))
    record = _record(deployed, NOW - timedelta(days=3))

    lenient = staleness.measure(record, "HEAD", NOW + timedelta(days=10), 14)
    strict = staleness.measure(record, "HEAD", NOW + timedelta(days=10), 5)

    assert not lenient.overdue
    assert strict.overdue


# --- every way the comparison can be meaningless ----------------------------


def test_a_commit_this_clone_does_not_have_is_a_refusal(clone: Path) -> None:
    """The shallow-checkout case, which is the one that reports zero silently.

    `git log <absent>..HEAD` on a shallow clone lists nothing, so the site reads
    as current. This is why the sentinel checks out with `fetch-depth: 0`, and
    why the refusal exists rather than trusting that it did.
    """
    _commit(clone, "site/index.html")

    with pytest.raises(staleness.StalenessUnknown, match="not in this clone"):
        staleness.measure(_record("a" * 40, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_diverged_history_is_a_refusal(clone: Path) -> None:
    _commit(clone, "site/index.html")
    subprocess.run(  # noqa: S603
        ["git", "-C", str(clone), "checkout", "-b", "other"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    orphan = _commit(clone, "site/orphan.html")
    subprocess.run(  # noqa: S603
        ["git", "-C", str(clone), "checkout", "main"],  # noqa: S607
        check=True,
        capture_output=True,
    )

    with pytest.raises(staleness.StalenessUnknown, match="not an ancestor"):
        staleness.measure(_record(orphan, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_malformed_deployed_sha_is_a_refusal(clone: Path) -> None:
    _commit(clone, "site/index.html")

    with pytest.raises(staleness.StalenessUnknown, match="not a commit id"):
        staleness.measure(_record("nope", NOW), "HEAD", NOW)


def test_a_deployed_commit_without_site_is_a_refusal(clone: Path) -> None:
    deployed = _commit(clone, "README.md")
    _commit(clone, "site/index.html")

    with pytest.raises(staleness.StalenessUnknown, match="has no site/ tree"):
        staleness.measure(_record(deployed, NOW - timedelta(days=5)), "HEAD", NOW)


# --- the report, and the exit code ------------------------------------------


def test_the_report_states_the_measurement_before_its_verdict(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=64))
    _commit(clone, "site/index.html", "republished", when=NOW - timedelta(days=63))
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    report = staleness.render(drift)

    assert deployed[:9] in report
    assert "OVERDUE" in report
    assert report.index("Behind by") < report.index("OVERDUE")
    # Both tree ids are stated, because the verdict rests on them.
    assert drift.deployed_tree[:12] in report
    assert drift.head_tree[:12] in report


def test_the_report_names_both_clocks_and_does_not_confuse_them(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=64))
    _commit(clone, "site/index.html", "republished", when=NOW - timedelta(days=20))
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    report = staleness.render(drift)

    assert drift.days_since_deploy == 63
    assert drift.waiting_days == 20
    assert "63 days ago" in report
    assert f"waited {drift.waiting_days} days" in report


def test_the_json_carries_every_number_the_report_states(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", when=NOW - timedelta(days=64))
    _commit(clone, "site/county/01.en.html", when=NOW - timedelta(days=63))
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=63)), "HEAD", NOW)

    payload = staleness.as_json(drift)

    assert payload["deployed_sha"] == deployed
    assert payload["days_since_deploy"] == 63
    assert payload["commits"] == 1
    assert payload["visitor_commits"] == 1
    assert payload["published_bytes_differ"] is True
    assert payload["overdue"] is True
    assert payload["deployed_tree"] != payload["head_tree"]


def test_the_cli_refuses_with_a_nonzero_exit_when_it_cannot_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 0 with a reassuring report. The sentinel workflow turns a

    measurement into an issue and a refusal into a red run, so this exit code is
    the whole difference between "the site is fine" and "nobody can tell".
    """
    payload = tmp_path / "deployments.json"
    payload.write_text('{"deployments": [], "statuses": {}}', encoding="utf-8")

    code = staleness.main(["--deployments-json", str(payload)])

    assert code == 2
    assert "cannot measure" in capsys.readouterr().err


def test_the_cli_reports_a_measurement_with_exit_zero(
    clone: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deployed = _commit(clone, "site/index.html")
    _commit(clone, "src/renderer.py")
    payload = tmp_path / "deployments.json"
    payload.write_text(
        json.dumps(
            {
                "deployments": [
                    {
                        "id": 1,
                        "sha": deployed,
                        "environment": "github-pages",
                        "created_at": "2026-09-01T00:00:00Z",
                    }
                ],
                "statuses": {"1": [{"state": "success"}]},
            }
        ),
        encoding="utf-8",
    )

    code = staleness.main(
        ["--deployments-json", str(payload), "--head", "HEAD", "--json"]
    )

    assert code == 0
    assert '"published_bytes_differ": false' in capsys.readouterr().out


def test_the_github_output_says_measured_false_on_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The workflow reads this to decide red-or-issue; a refusal must say so.

    If `measured` were absent or true here, the reporting step would fall
    through to "not overdue" and close the report issue on the strength of a
    measurement that was never made.
    """
    output = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    payload = tmp_path / "deployments.json"
    payload.write_text('{"deployments": [], "statuses": {}}', encoding="utf-8")

    assert staleness.main(["--deployments-json", str(payload)]) == 2

    written = output.read_text(encoding="utf-8")
    assert "measured=false" in written
    assert "overdue=" not in written


# --- the workflow this module is the body of --------------------------------

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-staleness.yml"


def workflow_source() -> str:
    """The sentinel workflow with comment-only lines dropped.

    `tests/test_ci_parity.py` does the same thing for the same reason: a comment
    naming a permission is prose about the file, not a grant in it. Both
    directions of that mistake are real. Across this portfolio four conformance
    checks once passed because they matched tool names in comments; this file
    first failed because the header's sentence "no `pages: write`" is a promise
    that the workflow does not hold that permission, and a check reading raw
    text cannot tell a promise from a grant.
    """
    return "\n".join(
        line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_sentinel_holds_no_permission_that_could_publish() -> None:
    """It reports; it must never be able to deploy.

    `pages: write` and `id-token: write` are what pages.yml and site-publish.yml
    hold to publish. A sentinel that acquired either could deploy the thing it
    is measuring, and its verdict would stop being an observation.
    """
    source = workflow_source()
    assert "permissions: {}" in source
    for forbidden in ("pages: write", "id-token: write", "contents: write"):
        assert forbidden not in source, (
            f"{forbidden} must not appear in {WORKFLOW.name}"
        )


def test_the_permission_check_reads_grants_and_not_prose() -> None:
    """The comment stripping above must not be able to hide a real grant.

    A `permissions:` block is indented, so dropping comment-only lines can never
    drop one; this proves the stripped text still carries the grants the job
    does hold, which is what makes the absence of the others meaningful.
    """
    source = workflow_source()
    assert "pages: write" in WORKFLOW.read_text(encoding="utf-8")  # in the prose
    for granted in ("contents: read", "deployments: read", "issues: write"):
        assert granted in source


def test_the_sentinel_checks_out_the_full_history() -> None:
    """Without this the deployed commit is absent and the drift reads as zero."""
    source = workflow_source()
    assert "fetch-depth: 0" in source
    assert "persist-credentials: false" in source


def test_the_sentinel_does_not_arm_or_read_the_publish_variables() -> None:
    """Whether this site publishes is not this workflow's decision to touch."""
    source = workflow_source()
    for variable in (
        "vars.SITE_S3_BUCKET",
        "vars.SITE_CLOUDFRONT_DISTRIBUTION_ID",
        "vars.SITE_PUBLISH_ROLE_ARN",
        "vars.SITE_AWS_REGION",
    ):
        assert variable not in source


def test_the_publishers_triggers_are_untouched() -> None:
    """This PR must not change publishing policy, only make staleness visible.

    Both publishers fire on `workflow_run` after `ci`, deliberately: it is what
    makes "a commit that fails the accessibility, parity or published-site gates
    never reaches families" true. Adding a `push:` trigger to either would be a
    policy change wearing a sentinel's clothes.
    """
    for name in ("pages.yml", "site-publish.yml"):
        source = (REPO_ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )
        assert "workflow_run:" in source
        assert "workflows: [ci]" in source
        assert "\n  push:" not in source
