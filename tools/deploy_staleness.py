#!/usr/bin/env python3
"""How long has homeroom.chelseakr.com been serving an older `site/` than main's?

This reads the GitHub *deployment record* and compares the published subtree.
It fetches nothing from the live origin, deploys nothing, and holds no
credential that could.

What already exists, and what it does not answer
------------------------------------------------
`live-integrity.yml` runs `tools/verify_live_site.py` daily and is the better
check for "is the origin actually serving the bytes it should": it fetches from
https://homeroom.chelseakr.com and fails naming every byte-level difference.
Nothing here replaces it and nothing here duplicates it.

What it cannot answer is how far behind, and it only looks at part of the
surface. Measured against the committed tree on 2026-09-13:

  * Of the 23,310 published files, 8 are compared on every run -- `index.html`,
    `CNAME`, `robots.txt`, `sitemap.xml`, the two social cards and the two ask
    pages. The other 23,302 (21,068 school pages, 2,118 district pages, 116
    county pages) rotate through a 200-per-run window, so one full sweep takes
    117 runs. A changed page can wait ~117 days before it is ever compared.
  * That would be tolerable if a stale deploy always showed up in the eight.
    It does not. `6985dfb98` -- the most recent commit to change `site/` --
    rewrote 2,234 files and none of the eight: exactly the county and district
    browse pages. And `sitemap.xml` carries no `<lastmod>`, only `<loc>`, so it
    moves when the *set* of pages changes and never when their content does. A
    content-only republish that never happened is invisible to the spine.
  * A byte difference is also not a date. `verify_live_site.py` reports that
    something differs; it never says which commit is live, how many days it has
    been live, or how many commits are waiting. Its own failure text hands that
    question off: "find out why the deployment is behind it." This is that.

Which publisher, and which record
---------------------------------
Two workflows publish `site/`, and both fire on `workflow_run` after `ci`
succeeds on main rather than on the push:

  * `pages.yml` uploads `site/` to GitHub Pages. Its job declares
    `environment: github-pages`, so every run that publishes leaves a
    deployment row naming the commit it published. This is what serves
    homeroom.chelseakr.com, and this is the record read below.
  * `site-publish.yml` syncs `site/` to S3 behind CloudFront. It declares no
    `environment:`, so it creates no deployment row at all, and it is inert as
    committed -- all four of its `vars.SITE_*` gates are unset, which was
    confirmed against the repository's Actions variables (there are none). If
    it is ever armed it will still create no deployment, so this sentinel keeps
    measuring the Pages origin and would need extending to cover the other.
    That is stated here rather than assumed: reading one record and calling it
    "the deploy" is only honest while one publisher creates records.

Because neither publisher fires on `push`, a `ci` run that fails, is canceled,
or is evicted from its concurrency group's pending slot publishes nothing and
reports nothing. That is not hypothetical here. `ci.yml`'s own concurrency
comment records the measurement: over the 67 most recent `ci` runs on main, 20
ended `cancelled` and 23 of those 67 commits had no successful `ci` run at all
-- each one a commit that never reached families. The concurrency key was fixed
so pushes no longer contend, but a failed `ci` run still publishes nothing
silently, and nothing else in this repository is watching the clock on it.

Why the deployment record and not the run history
-------------------------------------------------
A `workflow_run`-triggered workflow whose guard job decides not to publish still
logs a *successful* run. Both publishers here are exactly that shape: `pages.yml`
skips its only job unless the `ci` run concluded `success`, and `site-publish.yml`
skips its only job unless four repository variables are set -- which none of them
is, so every single one of its runs is a green run that published nothing.
Counting runs would therefore read `site-publish.yml`'s permanent skip as a fresh
deploy forever; filtering the skips out leaves no successful run at all, which is
a refusal dressed up as a measurement.

A deployment row cannot say either of those things. It exists because bytes were
published, and it names the commit they came from. Its newest status must be
`success` before that commit may be treated as live -- a row is a *request* to
publish, and treating a failed one as live reports the site as fresher than it
is, which is the one direction of error this file exists to prevent.

Why the published subtree and not the deployed SHA
--------------------------------------------------
This is a committed-tree publisher. The Pages API reports `build_type: workflow`,
but that only says a workflow feeds Pages rather than a legacy branch build; it
does not mean the workflow *builds* anything. `pages.yml` runs no renderer. It
uploads `site/` as-is, because the pages are rendered by `make publish` on a
machine holding the acquired CDE extracts under `data/raw/`, which are never in
git and never reach a runner (AGENTS.md, PROVENANCE.md).

So "deployed SHA versus head" is the wrong measure, and wrong in the noisy
direction. Measured 2026-09-13 over this repository's 51 github-pages
deployments: `site/` last changed at `6985dfb98` on 2026-09-05, and the 30 most
recent deployments -- every one since -- carry the identical tree `cf098c3876`
while main took 29 further commits. A SHA-distance sentinel would have reported
drift on 29 of those 30 and been wrong every time; the visitor held every byte
main had throughout. A check that cries wolf weekly is a check nobody reads.

What is compared instead is the git tree object id of `site/` at the deployed
commit against the one at head. Equal ids mean the visitor holds exactly the
bytes main holds, however far apart the commits are. It is also a *complete*
comparison of all 23,310 files in a single object-id equality, which is the one
thing a sampled byte-fetch cannot be.

The visitor-visible path set, and why it is exactly `site/`
-----------------------------------------------------------
`site/` and nothing else, because for a committed-tree publisher the served
bytes *are* the subtree: `pages.yml` uploads `path: site`, `site-publish.yml`
syncs `site/`, and neither reads anything else in the repository. Nothing under
`src/`, `tests/`, `docs/` or `evals/` can change what a visitor receives until
somebody re-runs `make publish` and commits the result -- at which point the
change appears here, as a change to `site/`.

The publishers' own sources are deliberately NOT on the list. In a repository
that renders at deploy time the renderer is a visitor-visible input, but here it
is not: editing `pages.yml` changes how the committed bytes are uploaded, not
what they are, so counting it would fire this sentinel on a comment.

One thing this does not measure, named so it is not mistaken for covered: whether
the committed `site/` is stale with respect to the renderer in `src/homeroom/`.
That is a different defect -- a committed artifact nobody regenerated -- and it
belongs to a regeneration gate, not to a deploy clock. This file answers only
whether what was published is what is committed.

The rule this follows, which is the portfolio's: a detector that cannot tell must
refuse, never report a comfortable zero. Every unmeasurable case below raises
`StalenessUnknown` and exits non-zero.

Standard library only, and it imports nothing from the rest of this repository,
so it runs on a bare `python3` with no dependency resolution and cannot be broken
by one -- the same constraint `tools/sources_check.py` keeps, for the same reason.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REPO = "ChelseaKR/homeroom"

#: The environment a deployment must belong to to be the published site.
#: `pages.yml` is the only workflow here that declares one; see the module
#: docstring on why `site-publish.yml` creates no rows.
PAGES_ENVIRONMENT = "github-pages"

#: The subtree both publishers upload, and therefore the whole of what a visitor
#: receives. `pages.yml` passes `path: site` to upload-pages-artifact;
#: `site-publish.yml` syncs `site/`. Nothing else in the repository is served.
PUBLISHED_SUBTREE = "site"

#: How long something a visitor would receive may sit unpublished before this
#: reports. Generous on purpose: a publish here follows a `ci` run that already
#: takes half an hour, and the failure worth catching is a fortnight, not an
#: afternoon.
DEFAULT_MAX_AGE_DAYS = 14

_SHA = re.compile(r"^[0-9a-f]{40}$")


class StalenessUnknown(Exception):
    """The comparison could not be made, so no number is reported.

    Raised in preference to returning zero anywhere the inputs do not support a
    measurement. The caller turns this into a red run: a sentinel that cannot
    tell is a broken sentinel and has to look like one.
    """


@dataclass(frozen=True)
class DeployRecord:
    """The published build: which commit it came from, and when it went out."""

    deployment_id: int
    sha: str
    created_at: datetime


@dataclass(frozen=True)
class Drift:
    """Where the published `site/` stands against main's."""

    deployed: DeployRecord
    head: str
    deployed_tree: str
    head_tree: str
    days_since_deploy: int
    commits: int
    visitor_commits: int
    waiting_days: int
    max_age_days: int

    @property
    def published_bytes_differ(self) -> bool:
        """Does the visitor hold different bytes from the ones main publishes?

        The whole verdict rests on this and not on the commit distance. Equal
        tree ids mean every one of the published files is identical, however
        many commits have landed since -- including the case where a commit
        changed `site/` and a later one changed it back.
        """
        return self.deployed_tree != self.head_tree

    @property
    def overdue(self) -> bool:
        """Report only when something a visitor would receive has waited too long.

        Two conditions, and both are load-bearing. Age alone is never the
        verdict: a site nobody republished because nothing it publishes changed
        is correct, not stale, and on this repository that is the normal state
        -- `site/` changed 7 times in 140 commits. And a difference alone is not
        overdue either, because a publish legitimately trails its merge by the
        length of a `ci` run.
        """
        return self.published_bytes_differ and self.waiting_days > self.max_age_days


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def newest_successful_deployment(
    deployments: Iterable[Mapping[str, Any]],
    statuses_for: Any,
) -> DeployRecord:
    """The most recent `github-pages` deployment that actually published.

    `statuses_for` is called with a deployment id and returns that deployment's
    statuses, newest first. A deployment row is a *request* to publish; its
    statuses are what say whether bytes landed. A row whose newest status is
    `failure`, `error`, `in_progress` or `queued` never became a site, and
    treating its commit as live would report the site as fresher than it is.
    """
    candidates = [
        d
        for d in deployments
        if d.get("environment") in (None, PAGES_ENVIRONMENT)
        and _SHA.match(str(d.get("sha", "")))
    ]
    if not candidates:
        raise StalenessUnknown(
            "no github-pages deployment in this repository's history: there is no "
            "published build to compare main against"
        )
    candidates.sort(key=lambda d: _parse_timestamp(str(d["created_at"])), reverse=True)

    for deployment in candidates:
        states = [str(s.get("state", "")) for s in statuses_for(deployment["id"])]
        if states and states[0] == "success":
            return DeployRecord(
                deployment_id=int(deployment["id"]),
                sha=str(deployment["sha"]),
                created_at=_parse_timestamp(str(deployment["created_at"])),
            )

    raise StalenessUnknown(
        f"none of the {len(candidates)} github-pages deployment(s) reports a "
        "successful status: nothing here proves any build was ever published"
    )


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    # A fixed argument vector with no shell; `REPO_ROOT` is derived from this
    # file's own location and never from an argument or the environment.
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(REPO_ROOT), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


def _git(*args: str) -> str:
    result = _run_git(*args)
    if result.returncode != 0:
        raise StalenessUnknown(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _has_commit(sha: str) -> bool:
    """Whether this clone contains the commit, without raising on absence.

    `git cat-file` exits non-zero for a commit that is simply not here, which is
    the ordinary shallow-clone case and not a git failure. Routing it through
    `_git` would report it as one, and the refusal the caller raises -- the one
    that names the shallow checkout and says why a zero would be wrong -- would
    never be reached.
    """
    return _run_git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def require_comparable(deployed_sha: str, head: str) -> None:
    """Refuse unless this clone can actually place the deployed commit on main.

    Every failure below reports zero drift if it is not caught, and all of them
    are ordinary. A shallow checkout does not contain an older commit at all, so
    `git log <deployed>..HEAD` lists nothing and the site reads as up to date --
    which is why the sentinel workflow checks out with `fetch-depth: 0`, and why
    this refuses rather than trusting that it did. A force-push or a rebase
    leaves the deployed commit off main entirely, where "commits since" is not a
    question with an answer.
    """
    if not _SHA.match(deployed_sha):
        raise StalenessUnknown(f"deployed commit {deployed_sha!r} is not a commit id")
    if not _has_commit(deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not in this clone: the checkout "
            "is shallow, and a comparison against a history that does not reach the "
            "published build would report no drift at all"
        )
    if _git("merge-base", deployed_sha, head) != _git("rev-parse", deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not an ancestor of {head[:9]}: the "
            "history has diverged and 'commits since the deploy' has no answer"
        )


def published_tree(commit: str) -> str:
    """The git tree object id of the published subtree at `commit`.

    This is the whole comparison. Two commits with the same id here publish
    byte-identical trees -- all 23,310 files -- and two with different ids do
    not, and neither fact depends on how far apart the commits are.
    """
    result = _run_git("rev-parse", f"{commit}^{{commit}}:{PUBLISHED_SUBTREE}")
    if result.returncode != 0:
        raise StalenessUnknown(
            f"commit {commit[:9]} has no {PUBLISHED_SUBTREE}/ tree, so there is "
            "nothing to compare: a published build must contain the directory the "
            "publishers upload"
        )
    tree = result.stdout.strip()
    if not _SHA.match(tree):
        raise StalenessUnknown(
            f"{PUBLISHED_SUBTREE}/ at {commit[:9]} resolved to {tree!r}, which is not "
            "a tree object id"
        )
    return tree


def commits_between(deployed_sha: str, head: str) -> list[str]:
    """Every commit after the deployed one, newest first."""
    raw = _git("log", "--format=%H", f"{deployed_sha}..{head}")
    return [line for line in raw.splitlines() if line.strip()]


def commits_touching_published_subtree(
    deployed_sha: str, head: str
) -> list[tuple[str, datetime]]:
    """Commits after the deployed one that changed `site/`, newest first.

    Paired with their committer dates, because the oldest of them is what the
    waiting clock is measured from.
    """
    raw = _git(
        "log",
        "--format=%H %cI",
        f"{deployed_sha}..{head}",
        "--",
        PUBLISHED_SUBTREE,
    )
    found: list[tuple[str, datetime]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        sha, _, when = line.partition(" ")
        found.append((sha, _parse_timestamp(when)))
    return found


def measure(
    deployed: DeployRecord,
    head: str,
    now: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> Drift:
    """Place the published `site/` against main's, or refuse."""
    head_sha = _git("rev-parse", f"{head}^{{commit}}")
    require_comparable(deployed.sha, head_sha)

    deployed_tree = published_tree(deployed.sha)
    head_tree = published_tree(head_sha)
    waiting = commits_touching_published_subtree(deployed.sha, head_sha)

    if deployed_tree != head_tree and not waiting:
        raise StalenessUnknown(
            f"{PUBLISHED_SUBTREE}/ differs between {deployed.sha[:9]} and "
            f"{head_sha[:9]} but no commit between them touched it; the history does "
            "not explain the difference and the measurement would be a guess"
        )

    # The clock starts when the change landed, not when the last deploy went
    # out. A site deployed 60 days ago whose `site/` changed yesterday has one
    # day of drift, not sixty, and dating it from the deploy would fire on a
    # repository that publishes rarely and correctly.
    waiting_days = (now - min(when for _, when in waiting)).days if waiting else 0

    return Drift(
        deployed=deployed,
        head=head_sha,
        deployed_tree=deployed_tree,
        head_tree=head_tree,
        days_since_deploy=(now - deployed.created_at).days,
        commits=len(commits_between(deployed.sha, head_sha)),
        visitor_commits=len(waiting),
        waiting_days=waiting_days,
        max_age_days=max_age_days,
    )


def render(drift: Drift) -> str:
    """The report. States the measurement before its verdict, always."""
    lines = [
        f"Published build:  {drift.deployed.sha[:9]}  "
        f"({drift.deployed.created_at.date().isoformat()}, "
        f"deployment {drift.deployed.deployment_id}, "
        f"{drift.days_since_deploy} days ago)",
        f"main:             {drift.head[:9]}",
        f"site/ published:  {drift.deployed_tree[:12]}",
        f"site/ on main:    {drift.head_tree[:12]}",
        f"Behind by:        {drift.commits} commit(s), "
        f"{drift.visitor_commits} of them changing site/",
    ]
    if drift.overdue:
        lines.append(
            f"\nOVERDUE: the published site/ differs from main's, and the oldest "
            f"commit changing it has waited {drift.waiting_days} days, past the "
            f"{drift.max_age_days}-day threshold. The site a family receives is not "
            "the one this repository publishes."
        )
    elif drift.published_bytes_differ:
        lines.append(
            f"\nWaiting: the published site/ differs from main's; the oldest commit "
            f"changing it has waited {drift.waiting_days} days, within the "
            f"{drift.max_age_days}-day threshold."
        )
    else:
        lines.append(
            "\nUp to date: the published site/ is byte-identical to main's, so a "
            "visitor holds exactly what this repository publishes. The commits since "
            "the deploy changed nothing that is served."
        )
    return "\n".join(lines)


def as_json(drift: Drift) -> dict[str, Any]:
    return {
        "deployed_sha": drift.deployed.sha,
        "deployed_at": drift.deployed.created_at.isoformat(),
        "deployment_id": drift.deployed.deployment_id,
        "head": drift.head,
        "deployed_tree": drift.deployed_tree,
        "head_tree": drift.head_tree,
        "published_bytes_differ": drift.published_bytes_differ,
        "days_since_deploy": drift.days_since_deploy,
        "commits": drift.commits,
        "visitor_commits": drift.visitor_commits,
        "waiting_days": drift.waiting_days,
        "overdue": drift.overdue,
    }


def _gh(path: str) -> Any:
    """Read the API through `gh`, which the runner already authenticates."""
    # A fixed argument vector with no shell; `path` is built from the --repo
    # argument and constants above.
    result = subprocess.run(  # noqa: S603
        ["gh", "api", path],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise StalenessUnknown(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _statuses_reader(repo: str) -> Any:
    def statuses_for(deployment_id: Any) -> list[Mapping[str, Any]]:
        listed = _gh(f"repos/{repo}/deployments/{deployment_id}/statuses?per_page=10")
        return list(listed)

    return statuses_for


def _offline_statuses_reader(statuses: Mapping[str, Any]) -> Any:
    def statuses_for(deployment_id: Any) -> list[Mapping[str, Any]]:
        return list(statuses.get(str(deployment_id), []))

    return statuses_for


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--head", default="origin/main")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--json", action="store_true", help="emit the measurement as JSON"
    )
    parser.add_argument(
        "--deployments-json",
        type=Path,
        help="read deployments from a file instead of the API (offline use and tests)",
    )
    args = parser.parse_args(argv)

    try:
        if args.deployments_json:
            payload = json.loads(args.deployments_json.read_text(encoding="utf-8"))
            deployments = payload["deployments"]
            statuses_for = _offline_statuses_reader(payload["statuses"])
        else:
            deployments = _gh(
                f"repos/{args.repo}/deployments"
                f"?environment={PAGES_ENVIRONMENT}&per_page=20"
            )
            statuses_for = _statuses_reader(args.repo)

        deployed = newest_successful_deployment(deployments, statuses_for)
        drift = measure(deployed, args.head, datetime.now(UTC), args.max_age_days)
    except StalenessUnknown as exc:
        print(f"cannot measure deploy staleness: {exc}", file=sys.stderr)
        _write_github_output(None, str(exc))
        return 2

    print(json.dumps(as_json(drift), indent=2) if args.json else render(drift))
    _write_github_output(drift, None)
    return 0


def _write_github_output(drift: Drift | None, error: str | None) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if drift is None:
            handle.write("measured=false\n")
            handle.write(f"error={error or 'unknown'}\n")
        else:
            handle.write("measured=true\n")
            handle.write(f"overdue={str(drift.overdue).lower()}\n")
            handle.write(f"waiting_days={drift.waiting_days}\n")
            handle.write(f"commits={drift.commits}\n")
            handle.write(f"visitor_commits={drift.visitor_commits}\n")
            handle.write(f"deployed_sha={drift.deployed.sha}\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
