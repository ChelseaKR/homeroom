"""The county and district pages, and the two things they got wrong at birth.

The browse pages went live on 2026-09-05 so a family could reach one school out
of 10,534 (`src/homeroom/browse.py`). They shipped with two defects that the
school pages had never had, both of which land on Spanish-reading families
first, and both of which every automated gate passed:

  * the whole heading was marked as English, so a Spanish screen reader was told
    to read `Condado de Alameda` -- article and preposition included -- with
    English phonemes. Only `Alameda` is CDE's, and marking the phrase says the
    opposite of what the marking is for (WCAG 2.2 SC 3.1.2);
  * no language link at all, so a reader who arrived at a county in the wrong
    language had no way across but editing the URL.

axe-core cannot see either: the markup is valid and the contrast is fine, and
`lang` on the wrong span is a true statement about the wrong words. So they are
checked here, against the names the source file actually publishes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from homeroom.browse import county_code, county_page_name, district_page_name
from homeroom.directory import active_schools
from homeroom.i18n import LOCALES, OTHER_LOCALE, text
from homeroom.site import build_site
from tests.test_pages import ABSENTEEISM, DIRECTORY, ENROLLMENT

MARKED = re.compile(r'<span lang="en">(.*?)</span>', re.S)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("browse")
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        landing=True,
    )
    return out


def browse_pages(built: Path) -> list[Path]:
    return sorted(
        [*(built / "county").glob("*.html"), *(built / "district").glob("*.html")]
    )


def cde_names() -> set[str]:
    """Every name the directory file publishes, which is the English CDE owns."""
    names: set[str] = set()
    for school in active_schools(DIRECTORY):
        names.update({school.name, school.district, school.county})
    return names


def test_there_are_browse_pages_to_check(built: Path) -> None:
    """The floor: a fixture build that stopped writing them would pass silently."""
    assert browse_pages(built), "the fixture build published no browse page"


def test_only_cde_names_are_marked_as_english(built: Path) -> None:
    """A span one word too wide is a lie about the words it took in.

    The Spanish page says "Condado de Yolo". Three of those words are Spanish
    and one is CDE's. Marking all four tells a screen reader to pronounce the
    Spanish ones as English, which is worse than not marking at all: the reader
    hears their own language read badly rather than a foreign name read plainly.
    """
    published = cde_names()
    for page in browse_pages(built):
        if not page.name.endswith(".es.html"):
            continue
        for marked in MARKED.findall(page.read_text(encoding="utf-8")):
            assert marked in published, (page.name, marked)


def test_no_english_page_marks_anything(built: Path) -> None:
    """On an English page the attribute is redundant, and `_cde` omits it."""
    for page in browse_pages(built):
        if page.name.endswith(".en.html"):
            assert not MARKED.findall(page.read_text(encoding="utf-8")), page.name


def test_every_browse_page_offers_the_other_language(built: Path) -> None:
    """Spanish here is a launch requirement, not a later translation phase."""
    for page in browse_pages(built):
        stem, locale, _ = page.name.rsplit(".", 2)
        other = OTHER_LOCALE[locale]  # type: ignore[index]
        markup = page.read_text(encoding="utf-8")
        sibling = f"{stem}.{other}.html"
        assert f'hreflang="{other}" rel="alternate" href="{sibling}"' in markup, (
            page.name,
            sibling,
        )
        assert text(locale, "switch_language_hint") in markup, page.name  # type: ignore[arg-type]
        assert (page.parent / sibling).is_file(), (page.name, sibling)


def test_the_language_link_names_a_page_in_the_language_it_claims(
    built: Path,
) -> None:
    """A link to the other language that lands on this one is worse than none."""
    for page in browse_pages(built):
        stem, locale, _ = page.name.rsplit(".", 2)
        other = OTHER_LOCALE[locale]  # type: ignore[index]
        sibling = page.parent / f"{stem}.{other}.html"
        assert f'<html lang="{other}">' in sibling.read_text(encoding="utf-8"), (
            sibling.name
        )


def test_every_county_and_district_is_published_in_both_languages(
    built: Path,
) -> None:
    schools = active_schools(DIRECTORY)
    for locale in LOCALES:
        for school in schools:
            county = built / county_page_name(county_code(school.cds_code), locale)
            district = built / district_page_name(school.cds_code[:7], locale)
            assert county.is_file(), county.name
            assert district.is_file(), district.name
