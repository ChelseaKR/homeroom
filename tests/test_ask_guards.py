"""The lexical guards: judgment language, numbers, absence, years."""

from __future__ import annotations

import pytest

from homeroom.ask.guards import (
    judgment_hits,
    number_forms,
    numbers_in,
    renders_absence_as_value,
    says_not_published,
    year_tokens,
)


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
