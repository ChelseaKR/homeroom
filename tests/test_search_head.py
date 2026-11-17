"""What a search result is built from: titles, descriptions and hreflang (ADR 0006).

Three things are held here. A school page's title and description name the city
(many California schools share a name) and say the page is enrollment, with the
earlier wording kept for a directory row that has no city or county. A hosted
build's hreflang links are absolute and carry an ``x-default``, because search
engines ignore hreflang that is not a fully qualified URL; a build given no
origin keeps the sibling file names and claims no address. And none of the new
copy ranks, scores or compares a school (ADR 0002).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from homeroom.browse import county_page_name, district_page_name
from homeroom.i18n import LOCALES, OTHER_LOCALE, Locale, text
from homeroom.profiles import assemble_profiles
from homeroom.render import page_name, school_description, school_title
from homeroom.site import build_site
from tests.test_pages import (
    ABSENTEEISM,
    DIRECTORY,
    ENROLLMENT,
    SCHOOLS,
    parse,
)

ORIGIN = "https://homeroom.example"


def _build(out: Path, site_url: str | None) -> Path:
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        landing=True,
        site_url=site_url,
    )
    return out


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("search-hosted"), ORIGIN)


@pytest.fixture(scope="module")
def unhosted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("search-unhosted"), None)


def _paired_pages(built: Path) -> list[tuple[str, Locale]]:
    """Every school, county and district page, as (path from root, locale)."""
    paths = [page_name(cds, locale) for cds in SCHOOLS for locale in LOCALES]
    paths += [
        str(p.relative_to(built))
        for sub in ("county", "district")
        for p in sorted((built / sub).glob("*.html"))
    ]
    assert any(p.startswith("county/") for p in paths)
    assert any(p.startswith("district/") for p in paths)
    return [(p, p.rsplit(".", 2)[1]) for p in paths]  # type: ignore[misc]


def _in(path: str, locale: Locale) -> str:
    return f"{path.rsplit('.', 2)[0]}.{locale}.html"


def test_a_hosted_page_names_both_languages_and_x_default_absolutely(
    hosted: Path,
) -> None:
    for path, locale in _paired_pages(hosted):
        document = parse(hosted / path)
        other = OTHER_LOCALE[locale]
        assert sorted(document.alternates) == sorted(
            [
                (locale, f"{ORIGIN}/{path}"),
                (other, f"{ORIGIN}/{_in(path, other)}"),
                ("x-default", f"{ORIGIN}/{_in(path, 'en')}"),
            ]
        ), path
        # The pair agrees with the page's own canonical, so a crawler reading
        # either sees the same address for the same page.
        assert document.canonical == f"{ORIGIN}/{path}", path


def test_an_unhosted_page_keeps_sibling_names_and_claims_no_address(
    unhosted: Path,
) -> None:
    for path, _locale in _paired_pages(unhosted):
        document = parse(unhosted / path)
        siblings = {loc: _in(path, loc).rsplit("/", 1)[-1] for loc in LOCALES}
        assert sorted(document.alternates) == sorted(siblings.items()), path
        assert all("://" not in href for _, href in document.alternates), path


def test_the_landing_page_carries_no_hreflang(hosted: Path) -> None:
    """One bilingual page has no other-language twin to point at."""
    assert parse(hosted / "index.html").alternates == []


def test_a_school_title_names_the_city_the_year_and_enrollment(hosted: Path) -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    for profile in assembly.profiles:
        school = profile.school
        assert school.city and school.county, "the fixture must carry a city"
        for locale in LOCALES:
            document = parse(hosted / page_name(school.cds_code, locale))
            expected = text(locale, "page_title_with_city").format(
                school=school.name, city=school.city, year=profile.academic_year
            )
            assert document.title == f"{expected} · {text(locale, 'site_name')}"
            assert f"{school.city} CA" in document.title
            assert profile.academic_year in document.title
            description = document.metas["description"]
            assert school.city in description and school.county in description
            assert profile.academic_year in description


def test_the_published_wording_is_the_reviewed_copy() -> None:
    """The exact strings the owner approved on 2026-11-17, Shafter High as the case."""
    values = {"school": "Shafter High", "city": "Shafter", "year": "2025-26"}
    assert (
        text("en", "page_title_with_city").format(**values)
        == "Shafter High, Shafter CA: 2025-26 enrollment"
    )
    assert (
        text("es", "page_title_with_city").format(**values)
        == "Shafter High, Shafter CA: matrícula 2025-26"
    )
    assert text("en", "meta_description_with_city").format(**values, county="Kern") == (
        "Shafter High in Shafter, Kern County: 2025-26 enrollment by grade and "
        "student group, and chronic absenteeism where the state publishes it. "
        "From California Department of Education files. No score, no ranking."
    )
    assert text("es", "meta_description_with_city").format(**values, county="Kern") == (
        "Shafter High en Shafter, condado de Kern: matrícula 2025-26 por grado y "
        "grupo de estudiantes, y ausentismo crónico donde el estado lo publica. "
        "De archivos del Departamento de Educación de California. Sin puntaje, "
        "sin clasificación."
    )


@pytest.mark.parametrize("missing", ["city", "county"])
def test_a_row_without_a_place_keeps_the_earlier_wording(missing: str) -> None:
    """CDE writes "No Data" in some columns and the parser makes it empty. A title
    with a hole in it ("Example Elementary,  CA") is worse than the old title."""
    profile = assemble_profiles(DIRECTORY, ENROLLMENT).profiles[0]
    school = dataclasses.replace(profile.school, **{missing: ""})
    bare = dataclasses.replace(profile, school=school)
    for locale in LOCALES:
        description = school_description(bare, locale)
        assert description == text(locale, "meta_description").format(
            school=school.name, district=school.district
        )
        title = school_title(bare, locale)
        if missing == "city":
            assert title == text(locale, "page_title").format(
                school=school.name, year=profile.academic_year
            )
        else:
            assert school.city in title
        assert " CA" not in description
        assert ",  " not in title and ",  " not in description


def test_no_search_copy_ranks_or_scores_a_school() -> None:
    """ADR 0002 binds titles too: they say what is on the page, not how it ranks."""
    banned = ("best", "top ", "rank", "rated", "rating", "score:", "safe")
    for key in ("page_title_with_city", "meta_description_with_city"):
        english = text("en", key).lower()
        # "No score, no ranking." is the refusal itself, so drop it first.
        english = english.replace("no score, no ranking.", "")
        for word in banned:
            assert word not in english, (key, word)
    for key in ("page_title_with_city", "meta_description_with_city"):
        spanish = text("es", key).lower().replace("sin puntaje, sin clasificación.", "")
        for word in ("mejor", "clasificad", "calificaci", "segur"):
            assert word not in spanish, (key, word)


def test_browse_page_names_still_resolve() -> None:
    """The pair the hreflang lines are built from is the pair browse.py writes."""
    assert _in(county_page_name("01", "en"), "es") == county_page_name("01", "es")
    assert _in(district_page_name("0110017", "es"), "en") == district_page_name(
        "0110017", "en"
    )
