"""What a published tree may weigh, and the refusal that runs before it is served.

`site/` is rendered on a machine holding the acquired CDE files and committed as
it stands; `.github/workflows/pages.yml` uploads that directory and builds
nothing. So the ceilings that govern the deploy are ceilings on bytes in this
repository, and the two that exist are documented by somebody else: GitHub
allows a published Pages site 1 GB, and the sitemap protocol allows one file
50,000 URLs and 50 MB.

`tests/test_published_limits.py` has held the *committed* tree to those since
2026-09-06. This module is the same limits, held one step earlier, because the
committed tree is not where the trouble starts. `make publish` used to open with
``rm -rf site`` and take about a quarter of an hour: the deployed tree was
deleted before a single byte of its replacement existed, and nothing between
that ``rm`` and the "commit it to deploy" line at the end weighed the result.
An over-budget publish therefore destroyed the working copy of a site that was
being served, printed success, and left the size to be discovered by a later
``make verify`` -- or, if nobody ran one, by GitHub refusing the artifact while
every check in the repository stayed green and families kept receiving the tree
that was last accepted.

Issue #82 is the live instance: publishing D5 on the school pages (ADR 0005) is
a measured 8,723 bytes across 21,068 pages, which is 184 MB, which does not fit
under the ceiling at all. Which of the three answers to that is taken -- move
hosts, republish without ``--assignments``, or take an existing section off the
page -- is the owner's, and nothing here chooses. What this module does is make
the next `make publish` say so, with the numbers, while `site/` is still intact.

The check runs against a staged tree, so its verdict is a measurement of the
bytes that would be published rather than a projection from a sample. It is
deliberately not a *fast* check -- it cannot answer before the render it is
weighing has happened -- and the thing it is early to is the irreversible step,
which is the one that mattered.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

# ----------------------------------------------------------------------------------
# The limits, and the budgets kept under them
# ----------------------------------------------------------------------------------

#: What GitHub allows a published Pages site.
#: <https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits>
#: says "1 GB" and does not say which GB, so this takes the smaller reading. The
#: larger one (2^30) would put the budget 74 MB above a cliff that might be at
#: 10^9, which is the one direction a size gate must not be wrong in.
PAGES_SITE_LIMIT_BYTES = 1_000_000_000

#: The share of each ceiling this repository will publish. What the remaining
#: 10% buys is time: about 100 MB, or roughly 2,500 school pages at what they
#: weigh now, in which to notice, decide and republish while the site is still
#: being served. A gate at the ceiling itself would only ever fire on a tree
#: that was already undeployable.
PUBLISHED_BUDGET_SHARE = 0.90
PUBLISHED_BUDGET_BYTES = int(PAGES_SITE_LIMIT_BYTES * PUBLISHED_BUDGET_SHARE)

#: <https://www.sitemaps.org/protocol.html>: one sitemap file carries "no more
#: than 50,000 URLs" and is "no larger than 50MB (52,428,800 bytes)
#: uncompressed". Past either, the protocol's answer is a sitemap index over
#: several files, which `homeroom.site.sitemap_xml` does not write.
SITEMAP_URL_LIMIT = 50_000
SITEMAP_BYTE_LIMIT = 52_428_800
SITEMAP_URL_BUDGET = int(SITEMAP_URL_LIMIT * PUBLISHED_BUDGET_SHARE)
SITEMAP_BYTE_BUDGET = int(SITEMAP_BYTE_LIMIT * PUBLISHED_BUDGET_SHARE)

#: The Pages limits page states this one too, and it is the ceiling a *source*
#: file crosses rather than a tree: nothing GitHub serves may exceed 100 MB.
PAGES_FILE_LIMIT_BYTES = 100 * 1024 * 1024


class NothingWasWeighed(Exception):
    """The tree handed in holds no file, so no budget below it means anything.

    This is the failure mode a limit check is most exposed to, and this
    repository has now refused it in the same shape four times: `MINIMUM_FILES`
    in `tools/verify_live_site.py`, the `-s` test in the Makefile's
    `determinism` target, `test_these_gates_are_weighing_a_real_published_tree`,
    and here. Every budget in this module passes over an empty directory, having
    measured nothing, and a publish step that took that for a verdict would
    replace a live site with the empty tree a half-finished render left behind.
    """


# ----------------------------------------------------------------------------------
# Reading a tree
# ----------------------------------------------------------------------------------


def measure(root: Path) -> tuple[tuple[Path, int], ...]:
    """Every file under ``root`` with its size, relative to ``root``.

    Every file, not every page: the preview cards, `robots.txt`, `CNAME` and the
    sitemap are uploaded with the markup and count against the same ceiling.
    Measured at 0.2s over the 23,310 files published on 2026-09-05, which is why
    this reads them all rather than sampling.

    Raises `NothingWasWeighed` when the directory is missing or holds no file.
    """
    if not root.is_dir():
        raise NothingWasWeighed(f"{root} is not a directory, so nothing was weighed")
    files = tuple(
        (path.relative_to(root), path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )
    if not files:
        raise NothingWasWeighed(f"{root} holds no file, so nothing was weighed")
    return files


def total_bytes(files: tuple[tuple[Path, int], ...]) -> int:
    return sum(size for _, size in files)


def mb(count: int) -> str:
    """Decimal MB, to match the decimal GB the Pages ceiling is read as."""
    return f"{count / 1_000_000:,.1f} MB"


def where_the_bytes_are(files: tuple[tuple[Path, int], ...]) -> str:
    """The tree grouped by its top level, which is how it has actually grown.

    Reported in the failure below because "site/ is too big" is not actionable
    and "district/ is 2,118 files and 17.8 MB" is. The growth so far arrived as
    whole areas: all 10,534 schools at the root, then `county/` and `district/`
    on top of them.
    """
    sizes: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for relative, size in files:
        area = f"{relative.parts[0]}/" if len(relative.parts) > 1 else "(root)"
        sizes[area] += size
        counts[area] += 1
    return "; ".join(
        f"{area} {counts[area]:,} files, {mb(size)}"
        for area, size in sizes.most_common()
    )


# ----------------------------------------------------------------------------------
# The refusals
# ----------------------------------------------------------------------------------


def _size_refusal(files: tuple[tuple[Path, int], ...]) -> str | None:
    total = total_bytes(files)
    if total <= PUBLISHED_BUDGET_BYTES:
        return None
    return (
        f"the rendered tree is {mb(total)} across {len(files):,} files, over the "
        f"{mb(PUBLISHED_BUDGET_BYTES)} budget and "
        f"{total / PAGES_SITE_LIMIT_BYTES:.1%} of the "
        f"{mb(PAGES_SITE_LIMIT_BYTES)} GitHub allows a published Pages site "
        "(docs.github.com/en/pages/getting-started-with-github-pages/"
        "github-pages-limits). "
        f"Where the bytes are: {where_the_bytes_are(files)}."
    )


def _file_refusal(files: tuple[tuple[Path, int], ...]) -> str | None:
    over = sorted(
        ((size, path) for path, size in files if size > PAGES_FILE_LIMIT_BYTES),
        reverse=True,
    )
    if not over:
        return None
    named = ", ".join(f"{path} at {mb(size)}" for size, path in over[:5])
    return (
        f"{len(over)} rendered file(s) exceed the {mb(PAGES_FILE_LIMIT_BYTES)} "
        f"GitHub Pages allows a single served file: {named}."
    )


def _sitemap_caps(size: int, listed: int) -> list[str]:
    """The protocol's two caps, over a size and a count rather than a file.

    Separated from the read so both are reachable without writing one. The byte
    cap's budget is 47.2 MB and this project's sitemap is 1.8 MB, so the only
    way to exercise that branch through a file is to write 47 MB of fixture to
    test arithmetic -- and a refusal no test can reach is a refusal nobody has
    checked the wording or the threshold of, which is a shape this repository
    has already found twice (`test_the_evaluation_gate_can_fail`, issue #37).
    """
    refusals = []
    if not listed:
        refusals.append("sitemap.xml lists no URL at all")
    if listed > SITEMAP_URL_BUDGET:
        refusals.append(
            f"sitemap.xml lists {listed:,} URLs, over the {SITEMAP_URL_BUDGET:,} "
            f"budget and {listed / SITEMAP_URL_LIMIT:.1%} of the "
            f"{SITEMAP_URL_LIMIT:,} the sitemap protocol allows one file "
            "(sitemaps.org/protocol.html); past the cap a crawler is entitled "
            "to stop reading, and what it stops reading are school pages"
        )
    if size > SITEMAP_BYTE_BUDGET:
        refusals.append(
            f"sitemap.xml is {mb(size)}, over the {mb(SITEMAP_BYTE_BUDGET)} "
            f"budget and {size / SITEMAP_BYTE_LIMIT:.1%} of the "
            f"{SITEMAP_BYTE_LIMIT:,} bytes the sitemap protocol allows one file "
            "(sitemaps.org/protocol.html)"
        )
    return refusals


def _sitemap_refusals(root: Path, files: tuple[tuple[Path, int], ...]) -> list[str]:
    """The sitemap in this tree held to those caps, or no sitemap to hold.

    A tree rendered with ``--site-url`` writes one; a tree rendered without one
    writes none, and that is a legitimate build rather than a fault, so a
    missing sitemap is passed over rather than refused. What is refused is a
    sitemap that exists and is past a cap, because past either the protocol's
    answer is a sitemap index over several files and `homeroom.site.sitemap_xml`
    writes a single file with no splitting logic in it.
    """
    sizes = {path: size for path, size in files}
    sitemap = Path("sitemap.xml")
    if sitemap not in sizes:
        return []
    source = (root / sitemap).read_text(encoding="utf-8")
    return _sitemap_caps(sizes[sitemap], source.count("<loc>"))


def refusals(root: Path) -> list[str]:
    """Every reason this rendered tree must not replace the published one.

    Empty means it may. `NothingWasWeighed` is raised rather than returned,
    because a tree that could not be measured is not a tree that passed.
    """
    files = measure(root)
    found = [
        refusal
        for refusal in (_size_refusal(files), _file_refusal(files))
        if refusal is not None
    ]
    return found + _sitemap_refusals(root, files)


# ----------------------------------------------------------------------------------
# The command `make publish` runs between rendering and serving
# ----------------------------------------------------------------------------------

#: Printed under a refusal. It names where the decision is recorded and does not
#: take it: which of the three answers to #82 is right is the owner's call, and
#: a build step that picked one would be making a hosting or a scope decision by
#: exiting non-zero at the wrong moment.
WHAT_TO_DO = """
This is not a budget to raise. The tree is committed HTML with no compression
step to add and nothing to prune that is not a page somebody can reach, so the
question is which pages exist. The answers on the table, and the record of the
one live instance, are in issue #82 and in `deploy/site/README.md`; they are
decisions rather than steps, and nothing in this repository takes one.

`site/` has not been touched. The rendered tree is left where it is so it can be
measured, and `make publish` can be run again once the question above is
settled.
""".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-publish-limits",
        description=(
            "Weigh a rendered site tree against the limits its deploy is "
            "subject to. Exits non-zero, before anything is served, when the "
            "tree could not be published."
        ),
    )
    parser.add_argument(
        "tree",
        type=Path,
        help="the rendered directory to weigh, e.g. build/publish-site",
    )
    args = parser.parse_args(argv)

    try:
        files = measure(args.tree)
    except NothingWasWeighed as empty:
        print(f"publish-limits: {empty}", flush=True)
        print(
            "publish-limits: refusing to report a tree as within budget when no "
            "byte of it was read; a half-finished render is not a small site.",
            flush=True,
        )
        return 1

    total = total_bytes(files)
    found = refusals(args.tree)
    print(
        f"publish-limits: {args.tree} is {mb(total)} across {len(files):,} files, "
        f"{total / PAGES_SITE_LIMIT_BYTES:.1%} of the "
        f"{mb(PAGES_SITE_LIMIT_BYTES)} Pages ceiling, with "
        f"{mb(max(PUBLISHED_BUDGET_BYTES - total, 0))} left under the "
        f"{PUBLISHED_BUDGET_SHARE:.0%} budget.",
        flush=True,
    )
    if not found:
        return 0
    for refusal in found:
        print(f"publish-limits: REFUSED: {refusal}", flush=True)
    print(WHAT_TO_DO, flush=True)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
