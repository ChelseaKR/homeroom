"""The landing page: the site's front door, and the claims it is allowed to make.

A hosted site needs a root. The risk a root page carries is not a rendering bug,
it is a claim: a front door that says "California school data" over a list of
three schools tells a family the state is covered when it is not. So these tests
check the structure the accessibility gates assume, and then they check that the
page names both languages, carries the non-affiliation and no-ranking notices,
reaches nowhere, and states that the list is what has been published so far
rather than what exists.

It linked every published school directly until 2026-09-05. At 10,534 schools
that made the front door a wall of 21,069 names, so it lists counties now and
`browse.py` carries the district and school steps. The invariant did not move
with the markup: a school is published for a family only if that family can
reach it from the root, so it is walked here rather than pattern-matched --
index, county, district, school -- in both languages.

``--landing`` is off by default, and a build without it is byte-identical to one
from before this module existed; that is asserted here too, because the fixture
gates compare against exactly that.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from homeroom.i18n import LOCALES, text
from homeroom.landing import render_landing
from homeroom.profiles import assemble_profiles
from homeroom.render import page_name
from homeroom.site import build_site
from tests.test_pages import (
    ABSENTEEISM,
    DIRECTORY,
    ENROLLMENT,
    FETCHING_ATTRIBUTES,
    NUMBER,
    SCHOOLS,
    SUBRESOURCE_TAGS,
    parse,
    parse_markup,
)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("landing")
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        landing=True,
    )
    return out


@pytest.fixture(scope="module")
def index(built: Path) -> Path:
    return built / "index.html"


def test_the_landing_page_is_written_only_when_it_is_asked_for(
    tmp_path: Path,
) -> None:
    """Off by default: a build without ``--landing`` has no root page at all."""
    without = tmp_path / "without"
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=without,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
    )
    assert not (without / "index.html").exists()


def test_a_landing_build_leaves_every_school_page_byte_identical(
    tmp_path: Path,
) -> None:
    """The front door must not change a single byte of a school page."""
    kwargs = dict(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
    )
    without = tmp_path / "without"
    with_landing = tmp_path / "with"
    build_site(out_dir=without, **kwargs)  # type: ignore[arg-type]
    build_site(out_dir=with_landing, landing=True, **kwargs)  # type: ignore[arg-type]
    for school_page in sorted(without.glob("*.html")):
        twin = with_landing / school_page.name
        assert twin.read_bytes() == school_page.read_bytes(), school_page.name


def test_the_landing_page_has_the_landmarks_and_head_a_reader_needs(
    index: Path,
) -> None:
    document = parse(index)
    assert document.title
    assert len(document.title) <= 110
    assert document.metas["charset"] == "utf-8"
    assert document.metas["viewport"].startswith("width=device-width")
    assert document.metas["description"]
    assert document.landmarks["main"] == 1
    assert document.landmarks["header"] == 1
    levels = [int(tag[1]) for tag, _ in document.headings]
    assert levels.count(1) == 1, levels
    assert levels[0] == 1, levels
    for previous, current in pairwise(levels):
        assert current - previous <= 1, levels
    assert document.ids.count("main") == 1
    assert len(document.ids) == len(set(document.ids))
    assert "#main" in document.hrefs


def test_the_landing_page_carries_both_languages_each_marked(index: Path) -> None:
    """Two sections, each with its own ``lang``, so a screen reader switches voice."""
    markup = index.read_text(encoding="utf-8")
    for locale in LOCALES:
        assert f'<section lang="{locale}"' in markup, locale
        assert text(locale, "landing_status") in markup, locale
        assert text(locale, "landing_counties_heading") in markup, locale


def reachable_schools(built: Path, locale: str) -> set[str]:
    """Every school page a reader can get to from the front door, in one locale.

    Walked rather than asserted against the markup, because the walk is the
    claim: three pages now stand between the root and a school, and a broken
    step anywhere in them takes a school off the site for a family without
    taking its file out of the build.
    """
    index = parse(built / "index.html")
    counties = [
        href
        for href in index.hrefs
        if href.startswith("county/") and href.endswith(f".{locale}.html")
    ]
    assert counties, f"the front door reaches no county in {locale}"
    reached: set[str] = set()
    for county_href in counties:
        county_page = built / county_href
        county = parse(county_page)
        districts = [h for h in county.hrefs if "district/" in h]
        assert districts, f"{county_href} reaches no district"
        for district_href in districts:
            district_page = (county_page.parent / district_href).resolve()
            for href in parse(district_page).hrefs:
                school = (district_page.parent / href).resolve()
                if school.parent == built and school.name.endswith(f".{locale}.html"):
                    reached.add(school.name)
    return reached


def test_every_published_school_is_reachable_from_the_front_door(built: Path) -> None:
    """Published and unreachable is not published, so the whole walk is checked."""
    for locale in LOCALES:
        assert reachable_schools(built, locale) == {
            page_name(cds, locale) for cds in SCHOOLS
        }, locale


def test_the_landing_page_links_nothing_it_did_not_publish(
    tmp_path: Path,
) -> None:
    """A link to a page this build did not write is a 404 with a school's name on it."""
    out = tmp_path / "one"
    only = SCHOOLS[0]
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        cds_codes=(only,),
        landing=True,
    )
    for locale in LOCALES:
        assert reachable_schools(out, locale) == {page_name(only, locale)}, locale
    written = {p.name for p in out.glob("*.html")}
    for locale in LOCALES:
        assert page_name(only, locale) in written


def test_the_landing_page_carries_the_two_notices_every_page_carries(
    index: Path,
) -> None:
    markup = index.read_text(encoding="utf-8")
    for locale in LOCALES:
        assert text(locale, "footer_unaffiliated") in markup, locale
        assert text(locale, "footer_no_ranking") in markup, locale


def test_the_landing_page_carries_no_script_and_reaches_nowhere(index: Path) -> None:
    source = index.read_text(encoding="utf-8")
    document = parse_markup(source)
    styles = [attr for tag, attr in document.elements if tag == "style"]
    assert len(styles) == 1
    assert "--surface" in source
    for tag, attr in document.elements:
        assert tag not in SUBRESOURCE_TAGS, tag
        for name in attr:
            assert name not in FETCHING_ATTRIBUTES, (tag, name)
            assert not name.startswith("on"), (tag, name)
    for smell in ("@import", "url(", "javascript:", "<script"):
        assert smell not in source.lower(), smell


def test_the_landing_page_publishes_no_figure(index: Path) -> None:
    """The front door lists schools; it does not carry a number about any of them.

    Every figure on this site sits beside its suppression state, its year, and its
    source. None of that fits in a list of links, so the rule here is that the
    list carries no digits at all rather than digits without their context.
    """
    document = parse(index)
    assert not NUMBER.findall(document.body_text), document.body_text


def test_a_fixture_landing_page_says_the_data_is_not_real(index: Path) -> None:
    markup = index.read_text(encoding="utf-8")
    assert text("en", "fixture_banner_title") in markup
    assert text("es", "fixture_banner_body") in markup


def test_an_acquired_landing_page_carries_no_fixture_banner() -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    markup = render_landing(list(assembly.profiles), is_fixture=False)
    assert text("en", "fixture_banner_title") not in markup
    levels = [int(tag[1]) for tag, _ in parse_markup(markup).headings]
    assert levels.count(1) == 1, levels


def test_the_landing_page_is_deterministic() -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    profiles = list(assembly.profiles)
    first = render_landing(profiles, is_fixture=True)
    assert first == render_landing(profiles, is_fixture=True)
