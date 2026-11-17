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
    SERVED_BY_CHOICES,
    SERVED_BY_CLOUDFRONT,
    SERVED_BY_FILE,
    SERVED_BY_PAGES,
    read_served_by,
)

ROOT = Path(__file__).resolve().parent.parent
ADR = ROOT / "docs" / "adr" / "0008-serve-the-site-from-s3-behind-cloudfront.md"
DEPLOY_RECORDS = (
    ROOT / "deploy" / "site" / "README.md",
    ROOT / "deploy" / "site" / "CUTOVER.md",
)

NOT_APPLIED = "Not applied"


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
