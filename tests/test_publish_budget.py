"""The refusal that runs between rendering a site and serving it.

`tests/test_published_limits.py` holds the *committed* tree to the ceilings the
deploy is subject to. This module is about the step before that: `make publish`
renders into a staging directory, weighs it, and replaces `site/` only if it
passes.

The order is the point. Until 2026-09-06 the recipe opened with
``rm -rf site`` and then spent about a quarter of an hour rendering the
replacement, so the irreversible step ran first and nothing weighed the result.
A publish that could not deploy destroyed the working copy of a site that was
being served and printed "commit it to deploy" at the end of it. Issue #82 is
the live instance of exactly that: D5 on the school pages is a measured 184 MB
across 21,068 pages and does not fit under the 1 GB ceiling at all.

What is checked here is the refusal, not the decision. Which of #82's three
answers is right -- move hosts, republish without ``--assignments``, take an
existing section off the page -- is the owner's, and a gate that picked one by
exiting non-zero at the right moment would be making a hosting decision in a
Makefile.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from homeroom import publish_limits
from homeroom.publish_limits import (
    PAGES_FILE_LIMIT_BYTES,
    PUBLISHED_BUDGET_BYTES,
    SITEMAP_BYTE_BUDGET,
    SITEMAP_URL_BUDGET,
    NothingWasWeighed,
    main,
    measure,
    refusals,
    total_bytes,
    where_the_bytes_are,
)

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = ROOT / "Makefile"


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _sitemap(urls: int) -> str:
    entries = "".join(
        f"<url><loc>https://homeroom.example/{n}.en.html</loc></url>"
        for n in range(urls)
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset>{entries}</urlset>'


@pytest.fixture
def a_publishable_tree(tmp_path: Path) -> Path:
    return _tree(
        tmp_path / "stage",
        {
            "index.html": "<html></html>",
            "01100170106906.en.html": "<html></html>",
            "county/01.en.html": "<html></html>",
            "sitemap.xml": _sitemap(3),
            "CNAME": "homeroom.chelseakr.com\n",
        },
    )


# ----------------------------------------------------------------------------------
# Nothing weighed is not a pass
# ----------------------------------------------------------------------------------


def test_an_empty_staging_tree_is_refused_rather_than_reported_as_small(
    tmp_path: Path,
) -> None:
    """Every budget passes over an empty directory, having measured nothing.

    This repository has refused that shape three times already -- `MINIMUM_FILES`
    in `tools/verify_live_site.py`, the `-s` test in the `determinism` target,
    and `test_these_gates_are_weighing_a_real_published_tree` -- and this is the
    place it would do the most damage: a half-finished render weighing nothing
    would clear the check and be moved over the live site.
    """
    empty = tmp_path / "stage"
    empty.mkdir()
    with pytest.raises(NothingWasWeighed):
        measure(empty)
    with pytest.raises(NothingWasWeighed):
        refusals(empty)
    assert main([str(empty)]) == 1


def test_a_staging_tree_that_was_never_rendered_is_refused(tmp_path: Path) -> None:
    """A path that is not a directory at all, which is a render that did not run."""
    with pytest.raises(NothingWasWeighed):
        measure(tmp_path / "never-rendered")
    assert main([str(tmp_path / "never-rendered")]) == 1


def test_the_empty_tree_refusal_says_why_rather_than_only_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "stage"
    empty.mkdir()
    assert main([str(empty)]) == 1
    printed = capsys.readouterr().out
    assert "nothing was weighed" in printed
    assert "within budget" in printed


# ----------------------------------------------------------------------------------
# A tree that fits
# ----------------------------------------------------------------------------------


def test_a_tree_inside_every_limit_is_allowed_through(a_publishable_tree: Path) -> None:
    assert refusals(a_publishable_tree) == []
    assert main([str(a_publishable_tree)]) == 0


def test_a_passing_run_still_says_what_the_tree_weighs(
    a_publishable_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Headroom is the number worth reading before it is spent, not after.

    `site/` went from 212 KB to 836 MB to 867.6 MB inside 2026-09-05. A check
    that says only "fine" on the way past 86.8% of a ceiling is a check nobody
    can plan against, so the measurement is printed whether it refuses or not.
    """
    assert main([str(a_publishable_tree)]) == 0
    printed = capsys.readouterr().out
    assert "files" in printed
    assert "% of the" in printed
    assert "left under the" in printed


def test_a_tree_with_no_sitemap_is_not_refused_for_lacking_one(
    tmp_path: Path,
) -> None:
    """A build without `--site-url` writes no sitemap, and that is legitimate.

    `make site` renders one; only a build told where it will be served writes
    crawler files. Refusing a tree for a file that build was never asked to
    produce would make this check fail on a correct build, which is the
    direction a gate is least useful in.
    """
    without = _tree(tmp_path / "stage", {"index.html": "<html></html>"})
    assert refusals(without) == []


# ----------------------------------------------------------------------------------
# The refusals themselves
# ----------------------------------------------------------------------------------


def test_a_tree_over_the_pages_budget_is_refused_with_the_numbers() -> None:
    """The size gate, over a file list rather than a file, so it can be exact.

    The tree is described rather than written: the check reads `st_size`, and a
    901 MB fixture on disk would test the filesystem's willingness to make a
    sparse file rather than the arithmetic being checked here. What the numbers
    stand for is the real case -- 21,068 school pages at 48,844 bytes is the
    tree issue #82 measured, and it is over the ceiling, not merely over this
    budget.
    """
    pages = PUBLISHED_BUDGET_BYTES // 48_844 + 1
    over = tuple((Path(f"{n}.en.html"), 48_844) for n in range(pages))
    assert total_bytes(over) > PUBLISHED_BUDGET_BYTES

    refusal = publish_limits._size_refusal(over)
    assert refusal is not None
    assert "900.0 MB budget" in refusal
    assert "1,000.0 MB GitHub allows" in refusal
    assert "docs.github.com" in refusal
    assert "(root)" in refusal


def test_the_size_refusal_names_where_the_bytes_are() -> None:
    """ "site/ is too big" is not actionable; "county/ is 2,118 files" is."""
    files = (
        (Path("index.html"), 10),
        (Path("county/01.en.html"), 200),
        (Path("county/02.en.html"), 300),
    )
    breakdown = where_the_bytes_are(files)
    assert breakdown.startswith("county/ 2 files")
    assert "(root) 1 files" in breakdown


def test_a_single_file_too_large_for_pages_to_serve_is_refused() -> None:
    """The other ceiling on the same documentation page, and a different one.

    The tree budget is about a total; this is about one file, which GitHub
    refuses to serve past 100 MB however small the site around it is. Checked
    over a file list for the same reason as the tree budget above.
    """
    files = (
        (Path("index.html"), 10),
        (Path("data/everything.json"), PAGES_FILE_LIMIT_BYTES + 1),
    )
    refusal = publish_limits._file_refusal(files)
    assert refusal is not None
    assert "data/everything.json" in refusal
    assert publish_limits._file_refusal(((Path("index.html"), 10),)) is None


def test_a_sitemap_past_the_protocols_url_cap_is_refused(tmp_path: Path) -> None:
    """A real tree, a real file, a real non-zero exit.

    This is the one refusal a fixture can reach at its true size: 45,001 URLs is
    under a megabyte on disk, where the tree budget and the per-file budget are
    both hundreds of megabytes. It exercises the whole path -- measure, refuse,
    print, exit 1 -- against a tree that was actually written.
    """
    tree = _tree(
        tmp_path / "stage",
        {
            "index.html": "<html></html>",
            "sitemap.xml": _sitemap(SITEMAP_URL_BUDGET + 1),
        },
    )
    found = refusals(tree)
    assert len(found) == 1
    assert f"{SITEMAP_URL_BUDGET + 1:,} URLs" in found[0]
    assert "sitemaps.org/protocol.html" in found[0]
    assert main([str(tree)]) == 1


def test_a_sitemap_over_the_protocols_byte_cap_is_refused() -> None:
    """The cap this sitemap will reach second and could reach first.

    50 MB uncompressed, same source, same consequence: a crawler may stop
    reading. At the 78 bytes an entry these addresses cost, the URL cap arrives
    first by a wide margin, so this branch is unreachable through a fixture
    without writing 47 MB of one -- and a refusal no test can reach is a refusal
    whose threshold and wording nobody has checked. It is exercised over a size
    and a count instead.
    """
    assert publish_limits._sitemap_caps(SITEMAP_BYTE_BUDGET, 10) == []
    found = publish_limits._sitemap_caps(SITEMAP_BYTE_BUDGET + 1, 10)
    assert len(found) == 1
    assert "47.2 MB budget" in found[0]
    assert "52,428,800 bytes" in found[0]


def test_a_sitemap_listing_no_url_at_all_is_refused(tmp_path: Path) -> None:
    """An empty sitemap is a crawler being told this site has no pages."""
    tree = _tree(
        tmp_path / "stage",
        {"index.html": "<html></html>", "sitemap.xml": _sitemap(0)},
    )
    assert refusals(tree) == ["sitemap.xml lists no URL at all"]


def test_the_refusal_points_at_the_open_decision_without_taking_it() -> None:
    """#82's three answers are the owner's; this step names them nowhere.

    A build step that exited non-zero in a way that pushed one of them -- "move
    to S3", say -- would be making a hosting decision in a Makefile. What it
    does instead is say where the decision is recorded and that `site/` is
    untouched.
    """
    guidance = publish_limits.WHAT_TO_DO
    assert "#82" in guidance
    assert "`site/` has not been touched" in guidance
    assert "not a budget to raise" in guidance


# ----------------------------------------------------------------------------------
# The order the recipe runs in, which is the whole fix
# ----------------------------------------------------------------------------------


def _publish_recipe() -> list[str]:
    """The `publish:` recipe's lines, in order, comments dropped."""
    body = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^publish:\n((?:\t.*\n)+)", body, re.M)
    assert match, "the Makefile has no `publish:` recipe"
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_publish_weighs_the_render_before_it_removes_the_published_tree() -> None:
    """The regression this whole module exists to stop coming back.

    `rm -rf $(PUBLISH_DIR)` used to be the first line of the recipe. It is now
    the second to last, and it must stay after the check: a render that cannot
    deploy has to leave the deployed tree where it is, because that tree is what
    families are being served until somebody decides what to do instead.
    """
    lines = _publish_recipe()
    checks = [n for n, line in enumerate(lines) if "publish-limits" in line]
    removals = [n for n, line in enumerate(lines) if "rm -rf $(PUBLISH_DIR)" in line]
    assert checks, "the publish recipe no longer weighs what it rendered"
    assert removals, "the publish recipe no longer replaces the published tree"
    assert min(checks) < min(removals), (
        "`make publish` removes $(PUBLISH_DIR) before it has weighed the tree "
        "meant to replace it; a render that cannot deploy would destroy the "
        "working copy of the site being served"
    )


def test_publish_renders_into_a_staging_tree_rather_than_over_the_published_one() -> (
    None
):
    """Nothing may write into `$(PUBLISH_DIR)` before the check has run."""
    lines = _publish_recipe()
    before_check = lines[
        : min(n for n, line in enumerate(lines) if "publish-limits" in line)
    ]
    writers = [
        line
        for line in before_check
        if "$(PUBLISH_DIR)" in line and "$(PUBLISH_STAGE)" not in line
    ]
    assert not writers, (
        "the publish recipe touches $(PUBLISH_DIR) before weighing the render: "
        f"{writers}"
    )


# ----------------------------------------------------------------------------------
# Which origin serves the site (owner decision 2026-09-18, #82)
# ----------------------------------------------------------------------------------
#
# The owner moved hosting to the S3 + CloudFront origin in `deploy/site/`. Until
# DNS moves, GitHub Pages is still what families are served, so the switch that
# relaxes the Pages ceiling is a committed file the owner flips *after* the DNS
# change: `deploy/site/served-by`. These checks hold the switch to doing exactly
# that and nothing else.

PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


def _over_the_pages_ceiling() -> tuple[tuple[Path, int], ...]:
    """A tree past the Pages ceiling, in school pages of the size D5 makes them.

    The real case is 1,060.8 MB: the committed 877.2 MB (2026-09-18) plus the
    8,723 bytes a page issue #82 measured for D5, over 21,068 school pages. This
    is about 1,048.8 MB of 48,844-byte pages, which is past the ceiling the same
    way. Described, not written, for the reason
    `test_a_tree_over_the_pages_budget_is_refused_with_the_numbers` gives.
    """
    pages = publish_limits.PAGES_SITE_LIMIT_BYTES // 48_844 + 1_000
    return tuple((Path(f"{n}.en.html"), 48_844) for n in range(pages))


def test_the_committed_switch_names_one_of_the_two_origins() -> None:
    """The file exists, says one known word, and says the origin DNS points at.

    ``github-pages`` until the owner moves DNS: this is the half of the switch
    that keeps Pages serving families. The day it changes is the day the owner
    flips it, in the commit that follows the DNS change.
    """
    served_by = publish_limits.read_served_by(ROOT / publish_limits.SERVED_BY_FILE)
    assert served_by in publish_limits.SERVED_BY_CHOICES


def test_an_unknown_origin_is_refused_rather_than_picking_a_ceiling(
    tmp_path: Path,
) -> None:
    """A typo must stop the publish, not fall through to either branch."""
    switch = tmp_path / "served-by"
    switch.write_text("cloudfrnt\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cloudfrnt"):
        publish_limits.read_served_by(switch)
    switch.write_text(" cloudfront \n", encoding="utf-8")
    assert publish_limits.read_served_by(switch) == "cloudfront"
    with pytest.raises(ValueError):
        refusals(tmp_path, "s3")


def test_the_pages_budget_binds_only_while_pages_serves_the_domain() -> None:
    """The same tree, refused on one origin and admitted on the other.

    This is the whole relaxation, and it is one branch: CloudFront's origin is
    an S3 bucket with no total-size ceiling.
    """
    tree = _over_the_pages_ceiling()
    assert publish_limits._size_refusal(tree) is not None
    assert publish_limits._size_refusal(tree, "github-pages") is not None
    assert publish_limits._size_refusal(tree, "cloudfront") is None


def test_the_per_file_ceiling_binds_on_either_origin() -> None:
    """GitHub refuses a pushed file over 100 MiB whatever serves the result."""
    files = ((Path("index.html"), 10), (Path("x.json"), PAGES_FILE_LIMIT_BYTES + 1))
    assert publish_limits._file_refusal(files) is not None
    assert not publish_limits.pages_can_take(files)


def test_a_cloudfront_tree_over_the_pages_ceiling_publishes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real path: measure, admit, and say what it means for the rollback."""
    tree = _tree(
        tmp_path / "stage",
        {"index.html": "<html></html>", "sitemap.xml": _sitemap(3)},
    )
    assert refusals(tree, "cloudfront") == []
    assert main([str(tree), "--served-by", "cloudfront"]) == 0
    out = capsys.readouterr().out
    assert "no total-size" in out
    assert "rollback copy" in out


def test_pages_can_take_a_tree_up_to_its_ceiling_and_not_past_it() -> None:
    """The ceiling, not the budget: that is the rollback copy's question."""
    tenth = publish_limits.PAGES_SITE_LIMIT_BYTES // 10
    at = tuple((Path(f"{n}.html"), tenth) for n in range(10))
    past = (*at, (Path("one-more.html"), 1))
    assert total_bytes(at) == publish_limits.PAGES_SITE_LIMIT_BYTES
    assert publish_limits.pages_can_take(at)
    assert not publish_limits.pages_can_take(past)


def test_the_pages_verdict_fails_while_pages_is_the_origin(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pages cannot take it and families are on Pages: an error, never a skip.

    A skip here would leave families on an older tree with every run green,
    which is the failure #82 was opened about.
    """
    assert publish_limits._pages_verdict(_over_the_pages_ceiling(), "github-pages") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("::error::")


def test_the_pages_verdict_skips_the_rollback_copy_once_cloudfront_serves(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stdout is appended to $GITHUB_OUTPUT, so it carries name=value and nothing else."""
    assert publish_limits._pages_verdict(_over_the_pages_ceiling(), "cloudfront") == 0
    captured = capsys.readouterr()
    assert captured.out == "deploy=false\n"
    assert captured.err.startswith("::warning::")
    assert "older tree" in captured.err


def test_the_pages_verdict_deploys_a_tree_that_fits_on_either_origin(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """While both fit, both origins get every commit: the rollback is one record."""
    fits = ((Path("index.html"), 10),)
    for served_by in publish_limits.SERVED_BY_CHOICES:
        assert publish_limits._pages_verdict(fits, served_by) == 0
        assert capsys.readouterr().out == "deploy=true\n"


def test_make_holds_the_render_to_the_ceiling_the_switch_names() -> None:
    """`make publish` reads the committed switch rather than a hand-passed word."""
    body = MAKEFILE.read_text(encoding="utf-8")
    assert "SERVED_BY := $(shell tr -d '[:space:]' < deploy/site/served-by)" in body
    assert (
        "uv run python -m homeroom.publish_limits $(PUBLISH_TREE) "
        "--served-by $(SERVED_BY)" in body
    )


def test_pages_yml_asks_the_same_module_before_uploading() -> None:
    """The deploy reads the same switch and the same ceiling, and gates on them.

    Comment lines are dropped first, so a mention in prose cannot pass for a
    step, the way `tools/config_audit.py` reads workflows.
    """
    source = "\n".join(
        line
        for line in PAGES_WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "deploy/site/served-by" in source
    assert "-m homeroom.publish_limits site" in source
    assert "--pages-verdict" in source
    # The upload sits in its own job behind the verdict, so a skipped commit
    # creates no github-pages deployment for tools/deploy_staleness.py to read
    # as served.
    publish = source[source.index("\n  publish:\n") :]
    assert (
        "    needs: verdict\n    if: needs.verdict.outputs.deploy == 'true'" in publish
    )
    assert "name: github-pages" in publish
    assert "actions/deploy-pages@" in publish
    verdict = source[source.index("\n  verdict:\n") : source.index("\n  publish:\n")]
    assert "environment:" not in verdict
    assert "pages: write" not in verdict
