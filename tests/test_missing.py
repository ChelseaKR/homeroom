"""The page a missing address answers with (`homeroom.missing`).

Until 2026-11-17 the build wrote none. On GitHub Pages a missing address got
GitHub's stock page; on CloudFront, from the day it took the domain, it got
S3's `<Error><Code>NoSuchKey</Code>` document, the right status and a tree of
XML tags for a body. Nothing in the suite could notice either, because every
gate reads pages that exist.

What is particular about this page is that it is served at an address that is
not its own, at any depth, to a reader whose language nobody knows. Each test
here is one consequence of that. That the status stays 404 is the
distribution's to keep and is held in `tests/test_deploy_site_template.py`;
that the committed `site/404.html` is this renderer's output is held in
`tests/test_published_site.py`.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

from homeroom import analytics
from homeroom.i18n import LOCALES, text
from homeroom.missing import (
    FRONT_DOOR,
    MISSING_PAGE_NAME,
    missing_title,
    published_missing,
    render_missing,
)
from homeroom.render import STYLESHEET_NAME
from homeroom.site import build_site
from tests.test_pages import (
    ABSENTEEISM,
    DIRECTORY,
    ENROLLMENT,
    FETCHING_ATTRIBUTES,
    SUBRESOURCE_TAGS,
    parse,
    parse_markup,
)

HOSTED_ORIGIN = "https://homeroom.example"


def build(out: Path, *, landing: bool, site_url: str | None = None) -> Path:
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        ask_endpoint="https://ask.example.invalid",
        landing=landing,
        site_url=site_url,
    )
    return out


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """What `make site-offline` builds: a front door, an origin, every page kind."""
    return build(
        tmp_path_factory.mktemp("missing-hosted"), landing=True, site_url=HOSTED_ORIGIN
    )


@pytest.fixture(scope="module")
def page(hosted: Path) -> Path:
    return hosted / MISSING_PAGE_NAME


def test_it_is_written_with_the_front_door_and_not_without(
    hosted: Path, tmp_path: Path
) -> None:
    """A site with a root has addresses that are not there; a bare build has no root."""
    assert (hosted / MISSING_PAGE_NAME).is_file()
    assert (hosted / "index.html").is_file()
    bare = build(tmp_path / "bare", landing=False)
    assert not (bare / MISSING_PAGE_NAME).exists()
    assert not (bare / "index.html").exists()


def test_it_is_named_what_github_pages_and_the_distribution_both_look_for() -> None:
    """One name does both jobs, so the rollback copy needs no setting of its own."""
    assert MISSING_PAGE_NAME == "404.html"


def test_every_address_on_it_starts_at_the_site_root(page: Path, hosted: Path) -> None:
    """It is shown at `/county/no-such.en.html` as readily as at `/no-such`.

    Every other page links relatively, and `tests/test_pages.py` holds them to
    it. Here a relative `homeroom.css` would be asked for at
    `/county/homeroom.css`, which is missing too: the page would arrive
    unstyled, and its way back would lead to a second missing page.
    """
    document = parse(page)
    sheets = [
        attr.get("href", "")
        for tag, attr in document.elements
        if tag == "link" and attr.get("rel") == "stylesheet"
    ]
    assert sheets == [f"/{STYLESHEET_NAME}"]
    assert (hosted / STYLESHEET_NAME).is_file()
    links = [href for href in document.hrefs if not href.startswith("#")]
    assert set(links) == set(FRONT_DOOR.values()), links
    for href in links:
        assert href.startswith("/") and not href.startswith("//"), href
    index = (hosted / "index.html").read_text(encoding="utf-8")
    for href in links:
        if "#" in href:
            assert f'id="{href.split("#", 1)[1]}"' in index, href
    assert "#main" in document.hrefs


def test_the_spanish_way_back_lands_in_the_spanish_half_of_the_front_door() -> None:
    """The front door is English first; `/` alone would drop a Spanish reader there."""
    assert FRONT_DOOR["en"] == "/"
    assert FRONT_DOOR["es"] == "/#h-es"


def test_it_speaks_both_languages_each_marked(page: Path) -> None:
    """A missing address has no language, so the page that answers it has both."""
    source = page.read_text(encoding="utf-8")
    assert '<html lang="en">' in source
    for locale in LOCALES:
        opening = f'<section lang="{locale}" aria-labelledby="missing-{locale}">'
        assert source.count(opening) == 1, locale
        half = source[source.index(opening) :].split("</section>", 1)[0]
        assert f'<h2 id="missing-{locale}">' in half
        for key in (
            "missing_heading",
            "missing_body",
            "missing_where",
            "landing_counties_heading",
            "footer_no_ranking",
            "footer_unaffiliated",
        ):
            assert text(locale, key) in half, (locale, key)
        other = "es" if locale == "en" else "en"
        for key in ("missing_heading", "missing_body", "missing_where"):
            assert text(other, key) not in half, (locale, key)
        assert f'<a href="{FRONT_DOOR[locale]}">' in half


def test_the_title_says_both_headings(page: Path) -> None:
    """The tab is the first place the page can tell a Spanish reader it speaks Spanish."""
    title = parse(page).title
    assert title == missing_title()
    assert title == "Page not found / Página no encontrada · Homeroom"
    assert len(title) <= 70


def test_it_has_the_landmarks_and_headings_a_reader_needs(page: Path) -> None:
    document = parse(page)
    assert document.lang == "en"
    assert document.metas["charset"] == "utf-8"
    assert document.metas["viewport"].startswith("width=device-width")
    assert document.metas["description"]
    assert document.landmarks["main"] == 1
    assert document.landmarks["header"] == 1
    levels = [int(tag[1]) for tag, _ in document.headings]
    assert levels == [1, 2, 2], document.headings
    for previous, current in pairwise(levels):
        assert current - previous <= 1
    assert document.ids.count("main") == 1
    assert len(document.ids) == len(set(document.ids))


def test_it_claims_no_address_and_is_in_no_sitemap(page: Path, hosted: Path) -> None:
    """Served at an address that is not its own, it has none to hand a crawler."""
    document = parse(page)
    assert document.metas.get("robots") == "noindex"
    assert document.canonical is None
    assert not document.alternates
    assert not document.properties, sorted(document.properties)
    assert not [name for name in document.metas if name.startswith("twitter:")]
    assert HOSTED_ORIGIN not in page.read_text(encoding="utf-8")
    sitemap = (hosted / "sitemap.xml").read_text(encoding="utf-8")
    assert MISSING_PAGE_NAME not in sitemap
    assert "<loc>" in sitemap, "the sitemap lists nothing, so this proves nothing"


def test_it_carries_no_script_and_reaches_nowhere(page: Path) -> None:
    """ADR 0001, as on every rendered page: one stylesheet, nothing else fetched."""
    document = parse(page)
    assert not [tag for tag, _ in document.elements if tag in SUBRESOURCE_TAGS]
    fetching = {
        (tag, name)
        for tag, attr in document.elements
        for name in attr
        if name in FETCHING_ATTRIBUTES
    }
    assert not fetching, sorted(fetching)
    assert not [
        name for _, attr in document.elements for name in attr if name.startswith("on")
    ]
    assert "http://" not in page.read_text(encoding="utf-8")
    assert "https://" not in page.read_text(encoding="utf-8")


def test_it_names_no_school_and_publishes_no_figure() -> None:
    """The same bytes for every address, so a digit could only be about nobody."""
    source = render_missing(is_fixture=False)
    visible = re.sub(r"<[^>]+>", " ", source.split("<body>", 1)[1])
    assert not re.search(r"\d", visible), visible
    assert render_missing(is_fixture=False) == source


def test_a_fixture_build_says_so_and_an_acquired_one_does_not(page: Path) -> None:
    fixture = page.read_text(encoding="utf-8")
    acquired = render_missing(is_fixture=False)
    for locale in LOCALES:
        assert text(locale, "fixture_banner_body") in fixture, locale
        assert text(locale, "fixture_banner_body") not in acquired, locale
    assert text("en", "fixture_banner_title") not in acquired


def test_the_build_is_the_same_twice(tmp_path: Path) -> None:
    first = build(tmp_path / "a", landing=True, site_url=HOSTED_ORIGIN)
    second = build(tmp_path / "b", landing=True, site_url=HOSTED_ORIGIN)
    assert (first / MISSING_PAGE_NAME).read_bytes() == (
        second / MISSING_PAGE_NAME
    ).read_bytes()


# ----------------------------------------------------------------------------------
# What `homeroom.analytics` adds to it, which is what the published copy carries
# ----------------------------------------------------------------------------------


def test_analytics_reaches_it_from_the_site_root_in_each_language() -> None:
    """The loader and the disclosure link, at the one kind of address that works.

    `add_to_page` gives every other page a relative `analytics.js`, climbing by
    the page's own depth. This page has no depth of its own: at
    `/county/no-such.en.html` a relative loader is `/county/analytics.js`,
    which is missing, so the note would promise a button that never arrives.
    """
    pinned = analytics.integrity("stand-in loader")
    page = analytics.add_to_page(
        render_missing(is_fixture=False), Path(MISSING_PAGE_NAME), pinned
    )
    document = parse_markup(page)
    scripts = [attr for tag, attr in document.elements if tag == "script"]
    assert len(scripts) == 1
    assert scripts[0]["src"] == f"/{analytics.SCRIPT_NAME}"
    assert scripts[0]["integrity"] == pinned
    for locale in LOCALES:
        opening = f'<section lang="{locale}"'
        half = page[page.index(opening) :].split("</section>", 1)[0]
        assert text(locale, "analytics_note") in half, locale
        assert f'<a href="/index.html#privacy-{locale}">' in half, locale
        assert half.count('class="analytics-opt-out"') == 1, locale
    assert page.count('class="analytics-opt-out"') == len(LOCALES)


def test_analytics_refuses_to_add_itself_to_it_twice() -> None:
    once = published_missing()
    if analytics.measurement_id() is None:  # pragma: no cover - GA configured off
        pytest.skip("no measurement ID configured; nothing is added")
    with pytest.raises(ValueError, match="already carries Google Analytics"):
        analytics.add_to_page(once, Path(MISSING_PAGE_NAME), "sha384-x")


def test_the_published_copy_is_the_render_plus_the_analytics_step(
    tmp_path: Path,
) -> None:
    """`published_missing` has to be what `make publish` would leave in `site/`."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / MISSING_PAGE_NAME).write_text(
        render_missing(is_fixture=False), encoding="utf-8"
    )
    analytics.add_to_tree(tree)
    assert (tree / MISSING_PAGE_NAME).read_text(encoding="utf-8") == published_missing()
