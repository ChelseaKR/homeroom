"""What the published surface is allowed to weigh, and how close it already is.

`site/` is committed and uploaded as it stands (`.github/workflows/pages.yml`
builds nothing), so the ceilings that govern the deploy are ceilings on bytes in
this repository. Two of them exist, both documented by somebody else, and until
this module neither was checked anywhere: GitHub allows a published Pages site
1 GB, and the sitemap protocol allows one file 50,000 URLs and 50 MB.

Both fail quietly, which is why they are worth a gate. An artifact over the
Pages limit is refused at deploy time, so the site stays on whatever it was
serving and every check in this repository stays green; a sitemap over the
protocol's caps is one a crawler stops reading part-way down, and nothing
anywhere reports a crawler giving up. In both cases the first person who could
notice is a family who cannot reach a school page.

The measurements that made this worth writing, re-taken 2026-09-06 against the
committed tree:

    site/           867,639,523 bytes across 23,310 files -- 86.8% of the 1 GB
                    ceiling, having been 212 KB, then 836 MB, then this, inside
                    2026-09-05: all 10,534 schools published, then 2,234 county
                    and district pages added on top
    sitemap.xml     23,303 URLs and 1,821,378 bytes -- 46.6% of the 50,000-URL
                    cap and 3.5% of the 50 MB one
    largest file    sitemap.xml again, at 1.8 MB; no page exceeds 109 KB

(`du -sh site` reports 856M for that same tree. That is allocated blocks:
23,310 files each rounded up to a 4 KiB boundary. What the deploy uploads and
what GitHub measures is the apparent size, which is what these gates read.)

The tree figure was 867,007,924 bytes when this module was first written; #78
moved it by 631,599 bytes without changing the file count, and it is re-measured
here rather than left at the number it was true for.

Every gate here fails at a budget below the real limit rather than at it, and
names the limit, its source, the budget and the current measurement when it
does. A gate that fires only once the deploy is already broken tells somebody
what the deploy would have told them anyway.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from homeroom.publish_limits import (
    PAGES_SITE_LIMIT_BYTES,
    PUBLISHED_BUDGET_BYTES,
    PUBLISHED_BUDGET_SHARE,
    SITEMAP_BYTE_BUDGET,
    SITEMAP_BYTE_LIMIT,
    SITEMAP_URL_BUDGET,
    SITEMAP_URL_LIMIT,
    NothingWasWeighed,
    mb,
    measure,
    total_bytes,
    where_the_bytes_are,
)
from tests.test_live_sentinel import sentinel

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

# ----------------------------------------------------------------------------------
# The limits, and the budgets kept under them
# ----------------------------------------------------------------------------------
#
# Every ceiling and budget below is imported from `homeroom.publish_limits`
# rather than declared here, and the reason is that this module is no longer the
# only reader of them. `make publish` weighs the tree it has just rendered
# against the same numbers before it replaces `site/`, so a budget retyped in
# two places would be a build step and a test gate quietly disagreeing about
# what may be published -- which is the shape of defect this file exists to
# catch, not one to introduce. What stays local is the per-file budget, which is
# derived from `tools/verify_live_site.py` rather than from a documented limit.

# `PUBLISHED_BUDGET_SHARE` is 90% of the Pages ceiling. 10% of the cap is
# ~100 MB, which is about 2,500 school pages at what they currently weigh: room
# to notice, publish something smaller, and still have the site up while it is
# sorted out. From the 2026-09-06 measurement it leaves 32 MB, which is less
# than one new per-page section across 21,068 school pages -- and that is the
# finding rather than a badly chosen number. Measured, not supposed: rendering
# 240 pages with and without D5 (ADR 0005) puts that one section at 8,723 bytes
# a page, so publishing it costs 184 MB and takes the tree past the ceiling
# itself, not merely past this budget (issue #82). At 86.8% of the cap there is
# no room for a new measure on every page, and the point of putting the budget
# where a build can see it is that the next thing published has to say what
# comes off first.
#
# `SITEMAP_URL_LIMIT` and `SITEMAP_BYTE_LIMIT` come from
# <https://www.sitemaps.org/protocol.html>: one sitemap file carries "no more
# than 50,000 URLs" and is "no larger than 50MB (52,428,800 bytes)
# uncompressed". Past either, the protocol's answer is a sitemap index over
# several files, which this project would have to write. The budgets are the
# same 90% of each, and the URL cap is the one that binds: at the measured 78
# bytes an entry, 50,000 URLs is under 4 MB, so this sitemap reaches the URL cap
# with 46 MB of its byte allowance unspent. The byte budget only becomes the
# live one if the addresses get much longer than the CDS digits they are now --
# a slug per school, say -- which is a reason to keep both.

#: The smallest ceiling over a single published file, read from the tool that
#: sets it rather than retyped: `tools/verify_live_site.py` refuses to read more
#: than this from the origin, and raises when it meets a file that big. That is
#: not a soft limit -- one oversized file in the always-compared spine (the
#: sitemap is in it) makes the whole daily deployment check exit 4, "could not
#: run", so the check that says the live site is the published site stops
#: working and stops saying anything. GitHub's own per-file limits sit well
#: above it: a push carrying a file over 100 MiB is blocked outright, and
#: `site/` is committed.
SENTINEL_READ_LIMIT_BYTES: int = sentinel.MAXIMUM_FILE_BYTES

#: Half of it, so a file crossing this still has a full doubling of headroom
#: before the sentinel goes blind on it. The largest file published today is
#: 1.8 MB, so this is not a line anything is near; it is the line that stops a
#: single file from quietly becoming unverifiable.
FILE_BUDGET_BYTES = SENTINEL_READ_LIMIT_BYTES // 2


# ----------------------------------------------------------------------------------
# Reading the tree
# ----------------------------------------------------------------------------------


@cache
def published_files() -> tuple[tuple[Path, int], ...]:
    """Every published file, path relative to `site/`, with its size.

    Every file, not every page: the preview cards, `robots.txt`, `CNAME` and the
    sitemap are uploaded with the markup and count against the same ceiling.
    Measured at 0.2s over the 23,310 files published on 2026-09-05, which is why
    this reads them all rather than sampling. Cached, because five checks below
    read it.

    This is `homeroom.publish_limits.measure` pointed at the committed tree --
    the same reader `make publish` runs over the tree it has just rendered, so a
    file the build weighs and a file this suite weighs are the same file.
    """
    return measure(SITE)


def published_bytes() -> int:
    return total_bytes(published_files())


def sitemap_source() -> str:
    return (SITE / "sitemap.xml").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------
# The gates
# ----------------------------------------------------------------------------------


def test_these_gates_are_weighing_a_real_published_tree() -> None:
    """A budget over an empty directory passes, having weighed nothing.

    That is the failure mode a limit check is most exposed to, and this
    repository refuses it in the same shape three times already: `MINIMUM_FILES`
    in `tools/verify_live_site.py`, the `-s` test in the Makefile's
    `determinism` target, which was added after CI spent a while comparing two
    empty hash files and reporting success, and `NothingWasWeighed` in
    `homeroom.publish_limits`. So the floor is stated here rather than assumed
    by the three checks below, all of which would pass on a `site/` that a
    half-finished `make publish` had emptied.

    The reader raises rather than returning an empty tuple, so this catches the
    raise and states it as this module's own floor. `make publish` no longer
    empties `site/` before it has something to put there, which is the change
    that made the raise the right shape: an empty `site/` in a checkout is now a
    deleted tree rather than an interrupted publish, and `git checkout -- site`
    is still the answer to both.
    """
    try:
        files = published_files()
    except NothingWasWeighed as empty:
        raise AssertionError(
            f"{empty}, so every budget below would pass having measured "
            "nothing. Restore the tree with `git checkout -- site`."
        ) from empty
    names = {path.as_posix() for path, _ in files}
    assert "index.html" in names, "site/ has no front door"
    assert "sitemap.xml" in names, "site/ publishes no sitemap to hold to a limit"
    schools = [
        name
        for name in names
        if "/" not in name and name.endswith(".html") and name != "index.html"
    ]
    assert schools, "site/ publishes no school page"
    assert published_bytes() > 0, "every published file is empty"


def test_the_published_tree_stays_inside_the_size_a_deploy_will_accept() -> None:
    """One gigabyte is the deploy's hard edge, and this site sits at 86.8% of it.

    Nothing in this repository measured that until now, and the way it goes
    wrong is the worst kind: `make publish` succeeds, the commit is reviewable,
    every other gate is green, and the Pages deploy refuses the artifact or
    stops working -- leaving families on a stale site, or on none, with the
    repository reporting success. The size is a property of the committed bytes,
    so it can be checked here, on a machine with no acquired file and no
    network, which is where the rest of this repository's published-site checks
    already run.

    The budget is 90% of the ceiling. What that 10% buys is time: about 100 MB,
    or roughly 2,500 school pages at what they weigh now, in which to notice,
    decide and republish while the site is still being served. A gate at the
    ceiling itself would only ever fire on a tree that was already undeployable.

    **When this trips**, the answer is not a bigger budget. The tree is
    committed HTML with no compression step to add and nothing to prune that is
    not a page somebody can reach, so the question is which pages exist. Three
    real answers, in the order they were considered when the ask layer was
    scoped: publish fewer pages; take something off before putting something on
    (a new per-page section costs its own size times 21,068); or move off Pages,
    which is a hosting decision and a much larger one. The headroom is already
    load-bearing -- rendering ask pages for all 10,534 schools rather than two
    would be about 1.1 GB and does not fit -- and that is exactly the sort of
    fact this gate exists to state before somebody spends it by accident.
    """
    total = published_bytes()
    assert total <= PUBLISHED_BUDGET_BYTES, (
        f"site/ is {mb(total)} across {len(published_files()):,} files, over "
        f"this repository's {mb(PUBLISHED_BUDGET_BYTES)} budget and "
        f"{total / PAGES_SITE_LIMIT_BYTES:.1%} of the "
        f"{mb(PAGES_SITE_LIMIT_BYTES)} GitHub allows a published Pages site "
        "(docs.github.com/en/pages/getting-started-with-github-pages/"
        "github-pages-limits). "
        f"Where the bytes are: {where_the_bytes_are(published_files())}. "
        f"The budget is {PUBLISHED_BUDGET_SHARE:.0%} of the ceiling so that "
        "this fails while the site is still deployable; raising it spends the "
        "margin rather than the problem. Publish fewer pages, or decide what "
        "comes off before deciding what goes on."
    )


def test_no_published_file_is_too_large_for_the_check_that_watches_the_deploy() -> None:
    """A file too big to read is a file the live sentinel silently stops checking.

    `tools/verify_live_site.py` is what says the bytes at homeroom.chelseakr.com
    are the bytes in this checkout, and it reads at most
    `MAXIMUM_FILE_BYTES` from the origin, raising on anything larger. That
    raise is not scoped to the file: it aborts the run with "could not run",
    so one oversized file takes the whole deployment check offline -- and the
    sitemap, the file here nearest to growing without a bound, is in the spine
    that sentinel compares on every run rather than in the sample it rotates
    through.

    So the budget is half the sentinel's own bound, read from that module
    rather than retyped, and a file crossing it is reported while there is
    still a doubling of room left. Nothing published today is near it: the
    largest file is the sitemap at 1.8 MB, and no page exceeds 109 KB. This is
    a gate on a shape of growth, not on today's tree.
    """
    assert SENTINEL_READ_LIMIT_BYTES > 0, (
        "tools/verify_live_site.py no longer declares a read limit, so this "
        "budget has nothing to be half of"
    )
    over = sorted(
        ((size, path) for path, size in published_files() if size > FILE_BUDGET_BYTES),
        reverse=True,
    )
    assert not over, (
        f"{len(over)} published file(s) exceed the {mb(FILE_BUDGET_BYTES)} "
        f"per-file budget, which is half the {mb(SENTINEL_READ_LIMIT_BYTES)} "
        "`tools/verify_live_site.py` can read from the origin; past that bound "
        "the daily check of the deployment exits 'could not run' rather than "
        "comparing anything: "
        + ", ".join(f"{path} at {mb(size)}" for size, path in over[:5])
    )


def test_the_sitemap_lists_fewer_urls_than_one_sitemap_file_may_carry() -> None:
    """Past 50,000 URLs a sitemap is not a big sitemap, it is an invalid one.

    The protocol (sitemaps.org/protocol.html) caps a single file at 50,000 URLs
    and expects a sitemap index over several files past that. A crawler meeting
    an over-long file is entitled to stop reading it, and what it stops reading
    are school pages -- so the visible symptom is schools quietly missing from
    search results, months later, with no error anywhere to connect it to.

    This file did not exist at anything like this size until 2026-09-05, when
    publishing every school took it from 5 URLs to 23,303 in a day. 46.6% of
    the cap is comfortable and the growth was not: the budget is 90%, leaving
    5,000 URLs of room, which is enough to publish the tree and then fix it.
    `homeroom.site.sitemap_xml` writes one file with no splitting logic in it,
    so crossing this is a feature to build rather than a number to raise.
    """
    listed = sitemap_source().count("<loc>")
    assert listed, "sitemap.xml lists no URL at all"
    assert listed <= SITEMAP_URL_BUDGET, (
        f"sitemap.xml lists {listed:,} URLs, over the {SITEMAP_URL_BUDGET:,} "
        f"budget and {listed / SITEMAP_URL_LIMIT:.1%} of the "
        f"{SITEMAP_URL_LIMIT:,} the sitemap protocol allows one file "
        "(sitemaps.org/protocol.html). Past the cap the answer is a sitemap "
        "index over several files, which homeroom.site.sitemap_xml does not "
        "write yet."
    )


def test_the_sitemap_is_smaller_than_one_sitemap_file_may_be() -> None:
    """The protocol's other cap, which this file will reach second and could reach first.

    50 MB (52,428,800 bytes) uncompressed, same source, same consequence: a
    crawler may stop reading. At the 78 bytes an entry these addresses cost,
    the URL cap arrives first by a wide margin -- 50,000 of them is under 4 MB.
    That ordering is a property of the addresses, not of the protocol: these
    are CDS digits under two short directories, and a scheme that spelled out
    school and district names instead would multiply the bytes per URL without
    changing the count. Both caps are checked because which one binds is a
    decision this project could still make differently.
    """
    size = (SITE / "sitemap.xml").stat().st_size
    listed = sitemap_source().count("<loc>")
    assert size <= SITEMAP_BYTE_BUDGET, (
        f"sitemap.xml is {mb(size)}, over the {mb(SITEMAP_BYTE_BUDGET)} budget "
        f"and {size / SITEMAP_BYTE_LIMIT:.1%} of the "
        f'{SITEMAP_BYTE_LIMIT:,} bytes -- "50MB ... uncompressed" -- the '
        "sitemap protocol allows one file (sitemaps.org/protocol.html). It "
        f"lists {listed:,} URLs at {size / max(listed, 1):.0f} bytes each."
    )
