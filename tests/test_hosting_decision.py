"""The hosting decision has one record, and that record has to agree with the switch.

Issue #82: the next `make publish` carries D5 (ADR 0005) and does not fit
under this repository's budget for GitHub Pages. The owner chose on 2026-09-18
to move the domain to the S3 + CloudFront origin in `deploy/site/`, and until
ADR 0008 that choice lived only in prose -- the deploy record, the cutover
commands and a module docstring -- none of which is where this project keeps
its decisions.

Which origin actually serves the domain is one committed word,
`deploy/site/served-by`, read by `make publish`, the suite and `pages.yml`
through `homeroom.publish_limits`. These tests hold the ADR to that word, so
the decision record cannot say the move happened before the switch does, or go
on saying it has not happened after the switch flips.
"""

from __future__ import annotations

import re
from pathlib import Path

from homeroom.publish_limits import (
    PAGES_SITE_LIMIT_BYTES,
    PUBLISHED_BUDGET_BYTES,
    PUBLISHED_BUDGET_SHARE,
    SERVED_BY_CHOICES,
    SERVED_BY_CLOUDFRONT,
    SERVED_BY_FILE,
    SERVED_BY_PAGES,
    SITE_BUDGET_SHARE,
    SITEMAP_BYTE_BUDGET,
    SITEMAP_URL_BUDGET,
    read_served_by,
)

ROOT = Path(__file__).resolve().parent.parent
ADR = ROOT / "docs" / "adr" / "0008-serve-the-site-from-s3-behind-cloudfront.md"
DEPLOY_RECORDS = (
    ROOT / "deploy" / "site" / "README.md",
    ROOT / "deploy" / "site" / "CUTOVER.md",
)

NOT_APPLIED = "Not applied"

#: The bridge of 2026-11-17: the share of the Pages ceiling the tree is held to
#: until the cutover, and the tree it was raised to admit, rendered in full
#: that day from `main` with both search-title branches merged.
BRIDGE_SHARE = 0.96
BRIDGE_TREE_BYTES = 953_659_316


def adr_source() -> str:
    return ADR.read_text(encoding="utf-8")


def status_line() -> str:
    found = re.search(r"^Status: (.+)$", adr_source(), re.M)
    assert found, f"{ADR.name} has no Status line"
    return found.group(1)


def test_the_hosting_adr_names_the_switch_and_both_of_its_values() -> None:
    """A reader of the decision has to be able to find the thing that enacts it."""
    text = adr_source()
    assert SERVED_BY_FILE.as_posix() in text
    for value in SERVED_BY_CHOICES:
        assert f"`{value}`" in text, f"{ADR.name} does not name `{value}`"


def test_the_hosting_adr_says_applied_only_when_the_switch_says_so() -> None:
    """The status follows `served-by`, in both directions.

    While the switch says `github-pages` the decision is taken and not applied,
    and the status must say so. Flipping it to `cloudfront` (step 9 of
    `deploy/site/CUTOVER.md`, after DNS has moved) fails this test until the
    status line is rewritten in the same pull request.
    """
    served_by = read_served_by(ROOT / SERVED_BY_FILE)
    status = status_line()
    if served_by == SERVED_BY_PAGES:
        assert NOT_APPLIED in status, (
            f"served-by says {served_by!r} but {ADR.name} does not say "
            f"{NOT_APPLIED!r}: {status!r}"
        )
    else:
        assert served_by == SERVED_BY_CLOUDFRONT
        assert NOT_APPLIED not in status, (
            f"served-by says {served_by!r}; rewrite {ADR.name}'s status with the "
            "date DNS moved"
        )


def test_the_deploy_records_cite_the_hosting_adr() -> None:
    """The reasoning and the commands both point back at the decision."""
    for record in DEPLOY_RECORDS:
        assert "ADR 0008" in record.read_text(encoding="utf-8"), (
            f"{record.relative_to(ROOT)} does not cite ADR 0008"
        )


def test_the_hosting_adr_keeps_the_rollback_origin() -> None:
    """The decision is a move with a way back, not a teardown of Pages.

    `pages.yml` keeps deploying whenever the tree fits, which is what makes the
    rollback one DNS record. An ADR that stopped saying so would be the first
    step towards deleting the workflow that the rollback depends on.
    """
    text = adr_source()
    assert "pages.yml" in text
    assert "rollback" in text.lower()
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "actions/deploy-pages@" in pages


# ----------------------------------------------------------------------------------
# The bridge: 96% of the Pages ceiling, until the `served-by` flip and no longer
# ----------------------------------------------------------------------------------


def test_the_bridge_budget_lasts_exactly_as_long_as_pages_is_the_origin() -> None:
    """The raised budget is tied to the switch, in both directions.

    While `served-by` says `github-pages` the tree is held to 96% of the
    ceiling, which is the owner's 2026-11-17 decision and nothing looser. Once
    it says `cloudfront` no total-size budget is applied, so a 96% left in the
    module would be a raised number with no reason attached, waiting for the
    day somebody points the switch back. The flip therefore fails here until
    the share is set back to the standing 90% in the same pull request.
    """
    served_by = read_served_by(ROOT / SERVED_BY_FILE)
    if served_by == SERVED_BY_PAGES:
        assert SITE_BUDGET_SHARE == BRIDGE_SHARE
        assert PUBLISHED_BUDGET_BYTES == 960_000_000
    else:
        assert SITE_BUDGET_SHARE == PUBLISHED_BUDGET_SHARE, (
            f"served-by says {served_by!r}: the bridge is over. Set "
            "SITE_BUDGET_SHARE back to PUBLISHED_BUDGET_SHARE in "
            "src/homeroom/publish_limits.py."
        )


def test_the_bridge_admits_the_measured_tree_and_stops_short_of_the_ceiling() -> None:
    """It was raised for one tree, and it still has to be able to refuse.

    A budget at the ceiling fires only on a tree GitHub has already refused.
    This one keeps 40 MB under it, and clears the tree it was raised for by
    single megabytes, so the next per-page section is refused here rather than
    at deploy time.
    """
    assert PUBLISHED_BUDGET_SHARE == 0.90
    assert PUBLISHED_BUDGET_SHARE <= SITE_BUDGET_SHARE <= BRIDGE_SHARE
    assert PAGES_SITE_LIMIT_BYTES - PUBLISHED_BUDGET_BYTES >= 40_000_000
    if SITE_BUDGET_SHARE == BRIDGE_SHARE:
        assert BRIDGE_TREE_BYTES <= PUBLISHED_BUDGET_BYTES
        assert PUBLISHED_BUDGET_BYTES - BRIDGE_TREE_BYTES < 10_000_000


def test_the_bridge_leaves_the_sitemap_budgets_where_they_were() -> None:
    """Only the tree's budget moved. The sitemap's two are still 90% of each."""
    assert SITEMAP_URL_BUDGET == 45_000
    assert SITEMAP_BYTE_BUDGET == 47_185_920


def test_the_records_say_the_bridge_is_temporary_and_when_it_ends() -> None:
    """A raised budget with no end date written down is just a raised budget."""
    cutover = (ROOT / "deploy" / "site" / "CUTOVER.md").read_text(encoding="utf-8")
    for name, text in ((ADR.name, adr_source()), ("CUTOVER.md", cutover)):
        assert "temporary bridge" in text, f"{name} does not call it temporary"
        assert "96%" in text, f"{name} does not state the bridge share"
        assert f"{BRIDGE_TREE_BYTES:,}" in text, (
            f"{name} does not state the tree the bridge was raised for"
        )
        assert "SITE_BUDGET_SHARE" in text, (
            f"{name} does not name what the flip sets back"
        )
