"""The lexical guards: judgment language, numbers, absence, years."""

from __future__ import annotations

import re

import pytest

from homeroom.ask.catalog import CATALOG
from homeroom.ask.guards import (
    judgment_hits,
    label_reference,
    number_forms,
    numbers_in,
    renders_absence_as_value,
    says_not_published,
    strip_label_references,
    year_tokens,
)
from homeroom.i18n import LOCALES


@pytest.mark.parametrize(
    "sentence",
    [
        "This is a good school.",
        "Attendance here is better than the district.",
        "It ranks among the top schools in the county.",
        "I would give it a B+.",
        "Overall grade: A",
        "On a scale out of 10 it is a 7.",
        "The school scores well.",
        "Its rating is strong.",
        "I recommend enrolling.",
        "You should send your child here.",
        "This is one of the worst schools around.",
        "Above average for the district.",
        "It outperforms the state.",
        "Es una buena escuela.",
        "La asistencia es mejor que en el distrito.",
        "Le doy una calificación de 8.",
        "Su puntaje es alto.",
        "Recomiendo inscribir a su hijo.",
        "Está por encima del promedio.",
        "Es una de las mejores escuelas.",
        "Es peor que el estado.",
    ],
)
def test_judgment_language_is_caught_in_both_languages(sentence: str) -> None:
    assert judgment_hits(sentence), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Grade 3 has 45 students.",
        "The chronic absenteeism rate is 12.5%, higher than the district's 11%.",
        "The rate is lower than the statewide figure.",
        "The state withheld this figure to protect student privacy.",
        "El grado 3 tiene 45 estudiantes.",
        "La tasa es más alta que la del distrito.",
        "El estado retuvo esta cifra para proteger la privacidad.",
        "Enrollment on Census Day was 512 students.",
        "La escuela mejoró su sistema de datos.",
    ],
)
def test_plain_figures_and_directions_are_not_judgment(sentence: str) -> None:
    assert judgment_hits(sentence) == [], sentence


def test_numbers_are_extracted_and_normalised() -> None:
    assert numbers_in("1,234 students, 12.5% and 7") == ["1234", "12.5", "7"]
    assert numbers_in("no digits here") == []
    assert numbers_in("Grade 3: 45") == ["3", "45"]


def test_academic_years_are_not_read_as_two_numbers() -> None:
    assert numbers_in("in 2024-25 the rate was 12.5%") == ["12.5"]
    assert numbers_in("en 2024\u201325 la tasa fue 12.5%") == ["12.5"]
    assert numbers_in("2025/26 enrollment: 512") == ["512"]
    assert year_tokens("2024-25") == {"2024-25", "2024", "25", "2025"}
    assert year_tokens("2025-26") == {"2025-26", "2025", "26", "2026"}


GRADES = ["Grade 4", "Grado 4", "Grade 7", "Grado 7", "Grade 8", "Grado 8"]


@pytest.mark.parametrize(
    ("sentence", "left"),
    [
        # The digit written against the row's name is the row's name.
        ("Grade 4 has 9 students.", ["9"]),
        ("4th grade has 9 students.", ["9"]),
        ("Grado 4 tiene 9 estudiantes.", ["9"]),
        ("Grades 7 and 8 are not served, so both counts are 0.", ["0"]),
        ("Grados 7 y 8 no se ofrecen.", []),
        # The same digit written anywhere else is a number the sentence asserts.
        ("Example Elementary enrolled 4 students in Grade 4.", ["4"]),
        ("Grade 4 enrolled 4 students.", ["4"]),
        ("Grade 8 has 7 students.", ["7"]),
    ],
)
def test_a_label_digit_is_licensed_where_it_names_the_row_and_nowhere_else(
    sentence: str, left: list[str]
) -> None:
    """Issue #34: "Grade 4" names a row, so its 4 is not a figure; a 4 written
    anywhere else in the same sentence still is, and must survive to be checked
    against the cited cell."""
    assert numbers_in(strip_label_references(sentence, GRADES)) == left


def test_every_digit_bearing_label_in_the_catalog_can_be_anchored() -> None:
    """`label_reference` licenses a label's digit only where the label's *word*
    is written next to it, so a label whose digits it cannot anchor licenses
    nothing at all and every sentence naming that row would be withheld. That
    is the safe direction, but it should be a decision rather than a surprise:
    this holds the docstring's count to the catalog it describes."""
    digit_labels = [
        spec.label(locale)
        for spec in CATALOG.values()
        for locale in LOCALES
        if re.search(r"\d", spec.label(locale))
    ]
    assert len(digit_labels) == 24, digit_labels
    assert all(label.split()[0] in {"Grade", "Grado"} for label in digit_labels)
    assert all(label_reference(label) is not None for label in digit_labels)


def test_a_label_without_a_number_licenses_nothing_and_removes_nothing() -> None:
    """Most labels are words. "All students" must not swallow any digit, and a
    label that is only digits has no name to be written against."""
    sentence = "All students: 100 enrolled, 12.5% chronically absent."
    assert numbers_in(strip_label_references(sentence, ["All students", "12"])) == [
        "100",
        "12.5",
    ]


def test_number_forms_are_exact_not_rounded() -> None:
    assert number_forms(512.0) == {"512"}
    assert "12.5" in number_forms(12.5)
    assert "12" not in number_forms(12.5)
    assert "13" not in number_forms(12.5)


@pytest.mark.parametrize(
    "sentence",
    [
        "This figure was not published.",
        "The state withheld it to protect privacy.",
        "CDE did not publish a figure for this group.",
        "No figure is published for this school.",
        "The rate for this school has not been published.",
        "This figure is not available for the school.",
        "El estado no publicó esta cifra.",
        "Esta cifra fue retenida para proteger la privacidad.",
        "No se publicó ningún dato para este grupo.",
        "Sin dato publicado.",
    ],
)
def test_absence_stated_honestly_is_recognised(sentence: str) -> None:
    assert says_not_published(sentence), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "There are zero English learners.",
        "None of the students are homeless.",
        "No students in this group.",
        "The rate is 0%.",
        "Hay cero estudiantes.",
        "Ningún estudiante es migrante.",
        "No hay estudiantes en este grupo.",
    ],
)
def test_absence_rendered_as_a_value_is_caught(sentence: str) -> None:
    assert renders_absence_as_value(sentence), sentence


def test_an_honest_absence_sentence_is_not_a_value() -> None:
    assert not renders_absence_as_value(
        "The figure for this group was withheld to protect student privacy."
    )
    assert not says_not_published("The rate is 12.5%.")


def test_an_explicit_negation_of_the_zero_reading_is_not_a_value() -> None:
    assert not renders_absence_as_value(
        "The state withholds it to protect privacy, not because there are no students."
    )
    assert renders_absence_as_value("There are no students in this group.")


@pytest.mark.parametrize(
    "sentence",
    [
        "La escuela no aparece en el archivo de ausentismo.",
        "No hay datos publicados para esta escuela.",
        "El archivo no incluye a esta escuela.",
        "El estado no la menciona en el archivo.",
    ],
)
def test_spanish_ways_of_saying_the_file_has_nothing(sentence: str) -> None:
    assert says_not_published(sentence), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "The state withholds it to protect privacy, not because the number is zero.",
        "It is not possible to say whether the rate is zero, small, or large.",
        "Withheld to protect privacy, not because no students were absent.",
        "A withheld figure does not mean zero students.",
        "Retenido para proteger la privacidad, no porque haya cero estudiantes.",
        "No es posible saber si hay cero estudiantes ausentes.",
    ],
)
def test_a_denial_of_the_zero_reading_is_not_a_value(sentence: str) -> None:
    assert not renders_absence_as_value(sentence), sentence


def test_withholds_and_suppresses_are_absence_phrases() -> None:
    assert says_not_published("The state withholds figures like this one.")
    assert says_not_published("CDE suppresses the cell.")
