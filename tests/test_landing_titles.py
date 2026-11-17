"""The front door's status line and the browse pages' search titles (ADR 0007).

The landing page used to say "Homeroom is in development. The schools published so
far..." long after all 10,534 active schools were published. It now says every
active school is published and gives the count the build rendered, never a typed
number. A build of fewer schools (``--cds``) keeps the "published so far" wording,
because "every" would then be a claim the page cannot back. The county and district
pages get titles and a district description that say where and what they are.
None of the new copy ranks or scores anything (ADR 0002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from homeroom.browse import county_page_name, district_page_name
from homeroom.i18n import LOCALES, format_number, text
from homeroom.site import build_site
from tests.test_pages import ABSENTEEISM, DIRECTORY, ENROLLMENT, SCHOOLS, parse

COUNTY = "01"  # the fixture's one county, Yolo
DISTRICT = "0110017"  # Davis Joint Unified


def _build(out: Path, cds_codes: tuple[str, ...] = ()) -> Path:
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        landing=True,
        cds_codes=cds_codes,
    )
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("landing-titles"))


def test_the_front_door_counts_what_the_build_rendered(built: Path) -> None:
    body = parse(built / "index.html").body_text
    for locale in LOCALES:
        status = text(locale, "landing_status").format(
            count=format_number(len(SCHOOLS))
        )
        assert status in body, locale
        assert text(locale, "landing_status_partial") not in body, locale
    assert "in development" not in body
    assert "en desarrollo" not in body


def test_a_build_of_fewer_schools_does_not_claim_every_school(tmp_path: Path) -> None:
    body = parse(_build(tmp_path / "one", (SCHOOLS[0],)) / "index.html").body_text
    for locale in LOCALES:
        assert text(locale, "landing_status_partial") in body, locale
    assert "every active" not in body
    assert "todas las escuelas públicas activas" not in body


def test_the_front_door_title_is_the_reviewed_english(built: Path) -> None:
    assert parse(built / "index.html").title == (
        "Homeroom: California public school enrollment, in English and Spanish"
    )


def test_county_and_district_titles_and_description(built: Path) -> None:
    county = {loc: parse(built / county_page_name(COUNTY, loc)) for loc in LOCALES}
    assert county["en"].title == "Yolo County schools by district · Homeroom"
    assert county["es"].title == "Escuelas del condado de Yolo por distrito · Homeroom"
    district = {
        loc: parse(built / district_page_name(DISTRICT, loc)) for loc in LOCALES
    }
    assert district["en"].title == (
        "Davis Joint Unified (Yolo County): public schools · Homeroom"
    )
    assert district["es"].title == (
        "Davis Joint Unified (condado de Yolo): escuelas públicas · Homeroom"
    )
    assert district["en"].metas["description"] == (
        "Each public school in Davis Joint Unified, Yolo County, with its 2025-26 "
        "enrollment and chronic absenteeism from California Department of Education "
        "files."
    )
    assert district["es"].metas["description"] == (
        "Cada escuela pública de Davis Joint Unified, en el condado de Yolo, con su "
        "matrícula 2025-26 y su ausentismo crónico, según archivos del Departamento "
        "de Educación de California."
    )


def test_the_new_copy_ranks_nothing() -> None:
    keys = (
        "landing_title",
        "landing_status",
        "browse_county_title",
        "browse_district_title",
        "browse_district_description",
    )
    for key in keys:
        english = text("en", key).lower()
        for word in ("best", "top ", "rank", "rated", "rating", "score", "safe"):
            assert word not in english, (key, word)
        spanish = text("es", key).lower()
        for word in ("mejor", "clasific", "calificaci", "puntaje", "segur"):
            assert word not in spanish, (key, word)
