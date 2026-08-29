"""The bytes actually served at homeroom.chelseakr.com.

`site/` is committed rather than built in CI, because it cannot be built in CI:
the pages are rendered from CDE files acquired by hand into `data/raw/`, which
is never in git and which CI never fetches. That is a deliberate trade, and it
has one obvious hazard -- committed output can drift from the code that made it,
or from the truth, and nothing would notice.

So these tests read the published files themselves. They cannot re-derive the
figures (that needs the acquired files), and they do not pretend to. What they
can check is every claim the published bytes make that does not require the
source data: that the site says what it is, that nothing on it is fixture data
presented as real, that every link resolves to a file that exists, that no page
reaches off-origin except the ask page's one configured endpoint, and that the
notices this project promises on every page are on every page.

`make verify` runs this on a machine with no acquired file present, which is the
whole point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeroom.i18n import LOCALES, text
from tests.test_pages import FETCHING_ATTRIBUTES, SUBRESOURCE_TAGS, parse_markup

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOMAIN = "homeroom.chelseakr.com"


def test_the_published_directory_is_here_at_all() -> None:
    """Everything below reads `site/`, so this is the floor under all of it.

    This module used to open with
    `pytestmark = pytest.mark.skipif(not SITE.is_dir(), ...)`, on the reading
    that a checkout with nothing published has nothing to check. That is not
    what this repository is: `site/` is committed, it is the bytes served at
    homeroom.chelseakr.com, and `make publish` begins with `rm -rf`. So a
    missing `site/` is a half-finished publish or a bad merge, and the skip
    turned every test in this file green for exactly the tree that most needed
    them -- fourteen checks reporting success having read nothing.
    """
    assert SITE.is_dir(), (
        "site/ is missing. It is committed, and it is what GitHub Pages "
        "serves; if `make publish` was interrupted after its `rm -rf`, restore "
        "it with `git checkout -- site` rather than publishing from here."
    )
    assert (SITE / "index.html").is_file(), "site/ exists but holds no index"


def published() -> list[Path]:
    return sorted(SITE.rglob("*.html"))


def school_pages() -> list[Path]:
    return [p for p in published() if p.parent == SITE and p.name != "index.html"]


def ask_pages() -> list[Path]:
    return [p for p in published() if p.parent.name == "ask"]


# ----------------------------------------------------------------------------------
# What the site is
# ----------------------------------------------------------------------------------


def test_the_site_names_its_own_domain_for_pages() -> None:
    """Without CNAME in the artifact, a deploy silently unsets the custom domain."""
    assert (SITE / "CNAME").read_text(encoding="utf-8").strip() == DOMAIN


def test_the_site_has_a_root_page() -> None:
    """A domain with no index answers 404 at the address people are given."""
    assert (SITE / "index.html").is_file()


def test_something_was_actually_published() -> None:
    assert school_pages(), "no school page is published"
    assert ask_pages(), "the ask link would point at nothing"


# ----------------------------------------------------------------------------------
# What it must never be
# ----------------------------------------------------------------------------------


def test_no_published_page_was_built_from_fixtures() -> None:
    """Fixture data on a public site is a synthetic school presented as a real one.

    The renderer marks a fixture build with a banner in both languages. Its
    presence here means somebody published `make site-offline`'s output.
    """
    for path in published():
        markup = path.read_text(encoding="utf-8")
        for locale in LOCALES:
            banner = text(locale, "fixture_banner_title")
            assert banner not in markup, (path.name, locale)


def test_every_published_page_carries_the_notices_this_project_promises() -> None:
    for path in published():
        markup = path.read_text(encoding="utf-8")
        assert text("en", "footer_unaffiliated") in markup or any(
            text(locale, "footer_unaffiliated") in markup for locale in LOCALES
        ), path.name
        assert any(text(locale, "footer_no_ranking") in markup for locale in LOCALES), (
            path.name
        )


def test_no_published_link_points_at_a_page_that_was_not_published() -> None:
    """A dead internal link on a school site is a claim that something is there."""
    for path in published():
        document = parse_markup(path.read_text(encoding="utf-8"))
        for href in document.hrefs:
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = (path.parent / href.split("#", 1)[0]).resolve()
            assert target.is_file(), (path.name, href)


# ----------------------------------------------------------------------------------
# What it is allowed to reach
# ----------------------------------------------------------------------------------


def test_no_school_page_carries_a_script_or_reaches_off_the_page() -> None:
    """The promise is per-page, and the published pages are where it is kept."""
    for path in [*school_pages(), SITE / "index.html"]:
        source = path.read_text(encoding="utf-8")
        document = parse_markup(source)
        for tag, attr in document.elements:
            assert tag not in SUBRESOURCE_TAGS, (path.name, tag)
            for name in attr:
                assert name not in FETCHING_ATTRIBUTES, (path.name, tag, name)
                assert not name.startswith("on"), (path.name, tag, name)
        assert "<script" not in source.lower(), path.name


def test_each_ask_page_names_exactly_one_endpoint_and_it_is_https() -> None:
    """The ask page is the only page that reaches anywhere, and only on submit.

    A published ask page pointed at an unreachable placeholder would put a form
    on a family's screen that can only ever fail, so the endpoint is checked for
    being a real https origin rather than merely present.
    """
    assert ask_pages(), "no ask page published"
    endpoints = set()
    for path in ask_pages():
        source = path.read_text(encoding="utf-8")
        blob = re.search(
            r'<script type="application/json" id="ask-strings">(.*?)</script>',
            source,
            re.S,
        )
        assert blob, path.name
        endpoint = json.loads(blob.group(1))["endpoint"]
        assert endpoint.startswith("https://"), (path.name, endpoint)
        assert endpoint.endswith("/ask"), (path.name, endpoint)
        assert ".invalid" not in endpoint, (path.name, endpoint)
        endpoints.add(endpoint)
    assert len(endpoints) == 1, endpoints


def test_every_ask_page_script_is_inline_and_nothing_else_is_fetched() -> None:
    """The ask page is allowed a script. It is not allowed to load one.

    A `src` here would mean a family's browser fetching code from somewhere
    else to read about their own child's school, which is the thing every other
    page on this site is checked for not doing.
    """
    for path in ask_pages():
        source = path.read_text(encoding="utf-8")
        document = parse_markup(source)
        scripts = [attr for tag, attr in document.elements if tag == "script"]
        assert scripts, path.name
        for attr in scripts:
            assert "src" not in attr, (path.name, attr)
        for tag, attr in document.elements:
            if tag != "script":
                assert tag not in SUBRESOURCE_TAGS, (path.name, tag)
            for name in attr:
                assert name not in FETCHING_ATTRIBUTES, (path.name, tag, name)
                assert not name.startswith("on"), (path.name, tag, name)


def test_every_school_page_is_published_in_both_languages() -> None:
    """A Spanish family arriving at an English-only site is the failure this avoids."""
    for path in school_pages():
        stem = path.name.rsplit(".", 2)[0]
        for locale in LOCALES:
            assert (SITE / f"{stem}.{locale}.html").is_file(), (stem, locale)
