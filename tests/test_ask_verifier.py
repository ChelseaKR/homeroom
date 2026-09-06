"""The verifier: every failure class withheld, every honest claim shown.

The fixture school (Example Elementary) publishes a total of 100 students
against a district 600 and state 1,000; a chronic absenteeism rate of 12.5%
against a district 11 and a state 19; a genuine zero for Asian students'
absenteeism; and withholds its African American and male enrollment counts.
Every claim below is written against those real fixture cells.
"""

from __future__ import annotations

import json

import pytest

from homeroom.ask.corpus import Corpus
from homeroom.ask.evidence import SchoolEvidence
from homeroom.ask.verifier import (
    REASONS,
    Claim,
    ShownClaim,
    WithheldClaim,
    parse_claims,
    verify,
)

EXAMPLE = "01100170112345"
TOTAL = f"{EXAMPLE}|enrollment.total|2025-26"
RATE = f"{EXAMPLE}|absenteeism.total|2024-25"
WITHHELD = f"{EXAMPLE}|enrollment.group.RE_B|2025-26"
ZERO = f"{EXAMPLE}|absenteeism.group.RA|2024-25"
# Grade rows, whose labels carry a digit of their own: 16, 9, 0 and 0 students.
GRADE_1 = f"{EXAMPLE}|enrollment.grade.GR_01|2025-26"
GRADE_4 = f"{EXAMPLE}|enrollment.grade.GR_04|2025-26"
GRADE_7 = f"{EXAMPLE}|enrollment.grade.GR_07|2025-26"
GRADE_8 = f"{EXAMPLE}|enrollment.grade.GR_08|2025-26"
# Grade 9: 0 students against the district's 20, a figure whose digits are also
# a run of digits in every academic year the narration writes (issue #63).
GRADE_9 = f"{EXAMPLE}|enrollment.grade.GR_09|2025-26"
SUPPRESSION_PASSAGE = "fsabd#4"
SUPPRESSION_QUOTE = (
    "data are suppressed (*) on the Chronic Absenteeism downloadable files if "
    "the cell size within a selected student population (Chronic Absenteeism "
    "Eligible Cumulative Enrollment) is 10 or less"
)


def one(
    claim: Claim, example: SchoolEvidence, corpus: Corpus, locale: str = "en"
) -> ShownClaim | WithheldClaim:
    result = verify([claim], example, corpus, "es" if locale == "es" else "en")
    assert len(result.shown) + len(result.withheld) == 1
    return result.shown[0] if result.shown else result.withheld[0]


def reason(
    claim: Claim, example: SchoolEvidence, corpus: Corpus, locale: str = "en"
) -> str:
    result = one(claim, example, corpus, locale)
    assert isinstance(result, WithheldClaim), result
    assert result.reason in REASONS
    return result.reason


# ----------------------------------------------------------------------------------
# Honest claims are shown
# ----------------------------------------------------------------------------------


def test_a_figure_with_its_number_and_its_cell_is_shown(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "figure",
            "In 2025-26, Example Elementary enrolled 100 students on Census Day.",
            (f"{TOTAL}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    assert shown.citations[0].anchor == "students"
    assert shown.citations[0].scope == "school"
    assert shown.citations[0].label == "All students"
    assert shown.citations[0].year == "2025-26"


def test_a_true_comparison_in_the_right_direction_is_shown(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "comparison",
            "The school's chronic absenteeism rate, 12.5%, is higher than the "
            "district figure of 11%.",
            (f"{RATE}|school", f"{RATE}|district"),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    lower = one(
        Claim(
            "comparison",
            "La tasa de la escuela, 12.5 %, es más baja que la del estado, 19 %.",
            (f"{RATE}|school", f"{RATE}|state"),
        ),
        example,
        corpus,
        "es",
    )
    assert isinstance(lower, ShownClaim)
    assert lower.citations[0].label == "Todos los estudiantes"


def test_an_honest_sentence_about_a_withheld_cell_is_shown(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "figure",
            "The number of African American students was withheld by the state "
            "to protect student privacy, so no figure is published.",
            (f"{WITHHELD}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


def test_a_genuine_published_zero_may_be_stated_as_zero(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "figure",
            "For Asian students the published chronic absenteeism rate is 0%, "
            "reported as zero by the state.",
            (f"{ZERO}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


def test_a_definition_with_a_verbatim_quote_is_shown(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "definition",
            "CDE withholds a figure when the group behind it is very small.",
            (SUPPRESSION_PASSAGE,),
            quote=SUPPRESSION_QUOTE,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    assert shown.quote == SUPPRESSION_QUOTE
    assert shown.citations[0].type == "passage"
    assert shown.citations[0].url is not None
    assert shown.citations[0].url.startswith("https://www.cde.ca.gov/")


def test_coverage_counts_and_years_are_numbers_a_claim_may_state(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "note",
            "Across the 3 schools in this build, 1 publishes a total enrollment "
            "figure for 2025-26, 1 has it withheld, and 1 publishes nothing.",
            (f"{TOTAL}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


# ----------------------------------------------------------------------------------
# A number is licensed by the fact it came from, not by proximity to it
# ----------------------------------------------------------------------------------


def test_a_figure_may_not_state_the_coverage_tally_as_the_school_own_value(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """Issue #34: the school's rate is 12.5%, and its coverage tally happens to
    contain 1. A figure claim saying "1%" states a number this school's cell
    never published, and it must be withheld rather than shown as verified."""
    assert (
        reason(
            Claim(
                "figure",
                "In 2024-25, Example Elementary's chronic absenteeism rate for "
                "all students was 1%.",
                (f"{RATE}|school",),
            ),
            example,
            corpus,
        )
        == "unverifiable_number"
    )


def test_a_figure_may_not_borrow_the_build_size_as_the_school_own_value(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """`schools_in_build` is 3. It is not this school's enrollment."""
    assert (
        reason(
            Claim(
                "figure",
                "Example Elementary enrolled 3 students on Census Day 2025-26.",
                (f"{TOTAL}|school",),
            ),
            example,
            corpus,
        )
        == "unverifiable_number"
    )


def test_a_figure_may_not_state_a_measure_label_digit_as_the_school_own_value(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """Issue #34, the label instance: Grade 4's enrolment at this school is 9,
    and the row is called "Grade 4". Licensing the label's digit as a bare token
    let the sentence state ``4`` as the count, next to the very name it came
    from. The 4 that names the row is fine; the 4 that claims to be the figure
    is not, and the two are told apart by where they are written."""
    assert (
        reason(
            Claim(
                "figure",
                "In 2025-26, Example Elementary enrolled 4 students in Grade 4.",
                (f"{GRADE_4}|school",),
            ),
            example,
            corpus,
        )
        == "unverifiable_number"
    )


def test_a_figure_may_not_swap_one_cited_grade_label_for_another_value(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """Grade 1 enrols 16 and Grade 4 enrols 9. Naming Grade 1 does not license
    Grade 4's figure, and the label does not license a number of its own."""
    assert (
        reason(
            Claim("figure", "Grade 1 has 9 students.", (f"{GRADE_1}|school",)),
            example,
            corpus,
        )
        == "unverifiable_number"
    )


@pytest.mark.parametrize(
    ("text", "cites", "locale"),
    [
        ("Grade 4 has 9 students.", (f"{GRADE_4}|school",), "en"),
        ("4th grade has 9 students.", (f"{GRADE_4}|school",), "en"),
        ("Grade 1 has 16 students.", (f"{GRADE_1}|school",), "en"),
        (
            "Grades 7 and 8 are not served at Example Elementary, so both "
            "counts are 0.",
            (f"{GRADE_7}|school", f"{GRADE_8}|school"),
            "en",
        ),
        (
            "En 2025-26, Grado 4 tenía 9 estudiantes.",
            (f"{GRADE_4}|school",),
            "es",
        ),
    ],
)
def test_naming_a_grade_row_is_still_shown(
    example: SchoolEvidence,
    corpus: Corpus,
    text: str,
    cites: tuple[str, ...],
    locale: str,
) -> None:
    """The digit that names the row has to be sayable, in either language and
    in the shapes narration actually writes: the verbatim label, an ordinal, and
    a list of rows sharing one verb. A fix that withheld these would have made
    the enrolment-by-grade answer unwritable."""
    shown = one(Claim("figure", text, cites), example, corpus, locale)
    assert isinstance(shown, ShownClaim), shown


def test_a_note_may_still_state_the_coverage_tally_it_cites(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """The context sentence the coverage numbers exist for keeps working."""
    shown = one(
        Claim(
            "note",
            "Across the 3 schools in this build, 1 publishes a total enrollment "
            "figure for 2025-26, 1 has it withheld, and 1 publishes nothing.",
            (f"{TOTAL}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


def test_a_figure_still_shows_the_value_its_own_cell_publishes(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """The narrowing must not withhold the true figure it exists to protect."""
    shown = one(
        Claim(
            "figure",
            "In 2024-25, Example Elementary's chronic absenteeism rate for all "
            "students was 12.5%.",
            (f"{RATE}|school",),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


# ----------------------------------------------------------------------------------
# Every failure class is withheld
# ----------------------------------------------------------------------------------


def test_no_citation(example: SchoolEvidence, corpus: Corpus) -> None:
    assert reason(
        Claim("figure", "The school has 100 students.", ()), example, corpus
    ) == ("no_citation")


@pytest.mark.parametrize(
    "text",
    [
        "With 100 students, this is a good school.",
        "Its 12.5% rate is better than the district's 11%.",
        "I would give it a B.",
        "Con 100 estudiantes, es una buena escuela.",
        "Su tasa de 12.5 % es mejor que la del distrito.",
    ],
)
def test_judgment_language(text: str, example: SchoolEvidence, corpus: Corpus) -> None:
    claim = Claim(
        "figure", text, (f"{TOTAL}|school", f"{RATE}|school", f"{RATE}|district")
    )
    assert reason(claim, example, corpus) == "judgment_language"


def test_unresolved_citation(example: SchoolEvidence, corpus: Corpus) -> None:
    other_school = "01100170154321|enrollment.total|2025-26|school"
    assert (
        reason(Claim("figure", "100 students.", (other_school,)), example, corpus)
        == "unresolved_citation"
    )
    assert (
        reason(Claim("figure", "100 students.", ("fsabd#99999",)), example, corpus)
        == "unresolved_citation"
    )
    assert (
        reason(
            Claim("figure", "100 students.", (f"{TOTAL}|school", "nonsense")),
            example,
            corpus,
        )
        == "unresolved_citation"
    )


@pytest.mark.parametrize(
    "text",
    [
        "About 105 students attend.",
        "Roughly one in eight students, 13%, were chronically absent.",
        "The district enrolls 600 students.",  # cites only the school cell
        "The rate is 12%.",  # 12.5 rounded
        "Asistieron 105 estudiantes.",
    ],
)
def test_unverifiable_number(
    text: str, example: SchoolEvidence, corpus: Corpus
) -> None:
    claim = Claim("figure", text, (f"{TOTAL}|school", f"{RATE}|school"))
    assert reason(claim, example, corpus) == "unverifiable_number"


@pytest.mark.parametrize(
    "text",
    [
        "There are zero African American students.",
        "No students in this group.",
        "The figure is 0.",
        "Hay cero estudiantes afroamericanos.",
        "No hay estudiantes en este grupo.",
    ],
)
def test_absence_as_value(text: str, example: SchoolEvidence, corpus: Corpus) -> None:
    claim = Claim("figure", text, (f"{WITHHELD}|school",))
    assert reason(claim, example, corpus) in ("absence_as_value", "unverifiable_number")


def test_absence_unstated(example: SchoolEvidence, corpus: Corpus) -> None:
    claim = Claim(
        "figure",
        "The school also reports on its African American students.",
        (f"{WITHHELD}|school",),
    )
    assert reason(claim, example, corpus) == "absence_unstated"


def test_comparison_shape(example: SchoolEvidence, corpus: Corpus) -> None:
    # Two different records.
    assert (
        reason(
            Claim(
                "comparison",
                "The 12.5% rate is higher than the 100 students.",
                (f"{RATE}|school", f"{TOTAL}|school"),
            ),
            example,
            corpus,
        )
        == "comparison_shape"
    )
    # District against state, no school cell.
    assert (
        reason(
            Claim(
                "comparison",
                "The district's 11% is lower than the state's 19%.",
                (f"{RATE}|district", f"{RATE}|state"),
            ),
            example,
            corpus,
        )
        == "comparison_shape"
    )
    # Three cells.
    assert (
        reason(
            Claim(
                "comparison",
                "At 12.5% the school is higher than the district's 11% and lower "
                "than the state's 19%.",
                (f"{RATE}|school", f"{RATE}|district", f"{RATE}|state"),
            ),
            example,
            corpus,
        )
        == "comparison_shape"
    )
    # A figure claim that compares in prose without citing the other cell.
    assert (
        reason(
            Claim(
                "figure",
                "The school's 12.5% is higher than the district's.",
                (f"{RATE}|school",),
            ),
            example,
            corpus,
        )
        == "comparison_shape"
    )


def test_comparison_unpublished(example: SchoolEvidence, corpus: Corpus) -> None:
    claim = Claim(
        "comparison",
        "The school's count is not published, lower than the district.",
        (f"{WITHHELD}|school", f"{WITHHELD}|district"),
    )
    assert reason(claim, example, corpus) == "comparison_unpublished"


def test_comparison_direction_missing_ambiguous_and_wrong(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    cites = (f"{RATE}|school", f"{RATE}|district")
    assert (
        reason(
            Claim(
                "comparison", "The school is at 12.5% and the district at 11%.", cites
            ),
            example,
            corpus,
        )
        == "comparison_direction_missing"
    )
    assert (
        reason(
            Claim(
                "comparison",
                "The school's 12.5% is higher, or perhaps lower, than the "
                "district's 11%.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_ambiguous"
    )
    assert (
        reason(
            Claim(
                "comparison",
                "The school's 12.5% is lower than the district's 11%.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )
    assert (
        reason(
            Claim(
                "comparison",
                "La tasa de la escuela, 12.5 %, es mayor que la del estado, 19 %.",
                (f"{RATE}|school", f"{RATE}|state"),
            ),
            example,
            corpus,
            "es",
        )
        == "comparison_direction_wrong"
    )


def test_definition_without_quote_and_quote_not_verbatim(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    assert (
        reason(
            Claim("definition", "Small groups are hidden.", (SUPPRESSION_PASSAGE,)),
            example,
            corpus,
        )
        == "definition_without_quote"
    )
    assert (
        reason(
            Claim(
                "definition",
                "Small groups are hidden.",
                (SUPPRESSION_PASSAGE,),
                quote="data are hidden when a group has fewer than ten students",
            ),
            example,
            corpus,
        )
        == "quote_not_verbatim"
    )
    # A real quote cited against the wrong page is not verbatim there.
    assert (
        reason(
            Claim(
                "definition",
                "Small groups are hidden.",
                ("fspubschls#0",),
                quote=SUPPRESSION_QUOTE,
            ),
            example,
            corpus,
        )
        == "quote_not_verbatim"
    )


def test_a_number_inside_a_verified_quote_is_allowed_but_not_one_outside(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "definition",
            "A group of 10 or fewer students is withheld.",
            (SUPPRESSION_PASSAGE,),
            quote=SUPPRESSION_QUOTE,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    assert (
        reason(
            Claim(
                "definition",
                "A group of 11 or fewer students is withheld.",
                (SUPPRESSION_PASSAGE,),
                quote=SUPPRESSION_QUOTE,
            ),
            example,
            corpus,
        )
        == "unverifiable_number"
    )


# ----------------------------------------------------------------------------------
# Parsing the model's tool input
# ----------------------------------------------------------------------------------


def test_malformed_tool_input_is_withheld_not_dropped() -> None:
    assert [c.reason for c in parse_claims("nope") if isinstance(c, WithheldClaim)] == [
        "malformed"
    ]
    assert [
        c.reason for c in parse_claims({"claims": "x"}) if isinstance(c, WithheldClaim)
    ] == ["malformed"]
    parsed = parse_claims(
        {
            "claims": [
                "not an object",
                {"kind": "verdict", "text": "x", "cites": []},
                {"kind": "figure", "text": "", "cites": []},
                {"kind": "figure", "text": "x" * 701, "cites": []},
                {"kind": "figure", "text": "ok", "cites": "not a list"},
                {
                    "kind": "figure",
                    "text": " ok ",
                    "cites": ["a", "a", "b"],
                    "quote": " ",
                },
            ]
        }
    )
    assert [c.reason for c in parsed if isinstance(c, WithheldClaim)] == [
        "malformed"
    ] * 5
    good = [c for c in parsed if isinstance(c, Claim)]
    assert good == [Claim("figure", "ok", ("a", "b"), None)]


def test_withheld_reasons_are_counted(example: SchoolEvidence, corpus: Corpus) -> None:
    result = verify(
        [
            Claim("figure", "100 students.", ()),
            Claim("figure", "A great school.", (f"{TOTAL}|school",)),
            Claim("figure", "A good school.", (f"{TOTAL}|school",)),
            WithheldClaim("malformed", ""),
        ],
        example,
        corpus,
        "en",
    )
    assert result.shown == ()
    assert result.withheld_reasons == {
        "judgment_language": 2,
        "malformed": 1,
        "no_citation": 1,
    }


def test_a_comparison_written_from_the_district_side_is_read_from_that_side(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    cites = (f"{TOTAL}|school", f"{TOTAL}|district")
    shown = one(
        Claim(
            "comparison",
            "The district enrolls 600 students, more than the school's 100.",
            cites,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    es = one(
        Claim(
            "comparison",
            "El distrito tiene 600 estudiantes, cifra más alta que la de la escuela.",
            cites,
        ),
        example,
        corpus,
        "es",
    )
    assert isinstance(es, ShownClaim)
    assert (
        reason(
            Claim(
                "comparison",
                "The district enrolls 600 students, fewer than the school's 100.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )
    # No number at all: the school is the subject.
    assert (
        reason(
            Claim("comparison", "The school has more than the district.", cites),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )


def test_an_academic_year_does_not_decide_which_side_a_comparison_speaks_from(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """A year opening the sentence used to flip the direction check (issue #63).

    The verifier reads a comparison from the school's side unless the sentence
    names the other figure first, and swaps subject and object when it does.
    That question was answered by a substring search over the claim, so the
    district's 20 was "found" at index 3 of "In 2025-26" -- inside the year --
    the operands were swapped, and "the school enrolled 0 students in Grade 9,
    more than the district's 20" passed the direction check against a school
    that enrolls none of them. A false sentence was shown to a reader as a
    verified one, by the check that exists to catch a model writing a
    comparison backwards, while the true sentence carrying the same year was
    withheld in its place.

    Grade 9 is the fixture row that makes it reproducible: the school's 0
    against the district's 20, both published, and "20" is a run of digits in
    every academic year the pages write. All four sentences open with that year
    because dropping it was enough to make all four behave, which is what
    isolated the substring hit.
    """
    cites = (f"{GRADE_9}|school", f"{GRADE_9}|district")
    assert (
        reason(
            Claim(
                "comparison",
                "In 2025-26, Example Elementary enrolled 0 students in Grade 9, "
                "more than the district's 20.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )
    shown = one(
        Claim(
            "comparison",
            "In 2025-26, Example Elementary enrolled 0 students in Grade 9, "
            "fewer than the district's 20.",
            cites,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    # And the district's side is still read from the district's side: the fix
    # must not answer "school" to everything that carries a year.
    from_the_district = one(
        Claim(
            "comparison",
            "In 2025-26, the district enrolled 20 students in Grade 9, more "
            "than Example Elementary's 0.",
            cites,
        ),
        example,
        corpus,
    )
    assert isinstance(from_the_district, ShownClaim)
    assert (
        reason(
            Claim(
                "comparison",
                "In 2025-26, the district enrolled 20 students in Grade 9, fewer "
                "than Example Elementary's 0.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )


def test_a_comma_grouped_thousand_still_names_the_side_a_comparison_speaks_from(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    """The state's 1,000 is the state's 1000, which the fix must not lose.

    The side check used to strip every comma from the claim before looking for
    the other figure, which is how it matched "1,000" against the cell's 1000.
    It reads numbers through :data:`homeroom.ask.guards.NUMBER` now, and that
    pattern takes the thousands comma itself -- so the state cell the fixture
    publishes as 1000.0 is still recognised in the one spelling a page or the
    narration would ever give it.
    """
    cites = (f"{TOTAL}|school", f"{TOTAL}|state")
    shown = one(
        Claim(
            "comparison",
            "Across the state 1,000 students were enrolled in 2025-26, more "
            "than Example Elementary's 100.",
            cites,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    assert (
        reason(
            Claim(
                "comparison",
                "Across the state 1,000 students were enrolled in 2025-26, fewer "
                "than Example Elementary's 100.",
                cites,
            ),
            example,
            corpus,
        )
        == "comparison_direction_wrong"
    )


def test_a_note_may_cite_a_source_file_for_its_year_and_nothing_more(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    shown = one(
        Claim(
            "note",
            "The chronic absenteeism figures come from the 2024-25 file, a "
            "different year from the 2025-26 enrollment figures.",
            ("d3", "d2"),
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)
    assert [c.type for c in shown.citations] == ["source", "source"]
    assert shown.citations[0].anchor == "sources"
    assert (
        reason(
            Claim("note", "The 2024-25 file covers 10,534 schools.", ("d3",)),
            example,
            corpus,
        )
        == "unverifiable_number"
    )
    assert (
        reason(Claim("note", "From the 2024-25 file.", ("d9",)), example, corpus)
        == "unresolved_citation"
    )


def test_comparative_words_in_a_definition_are_not_a_cell_comparison(
    example: SchoolEvidence, corpus: Corpus
) -> None:
    quote = (
        "Students that are expected to attend less than 31 instructional days "
        "at the selected entity or who were enrolled but did not attend the "
        "selected entity are not eligible to be considered chronically absent "
        "at that entity."
    )
    shown = one(
        Claim(
            "definition",
            "Students expected to attend fewer than 31 days are not counted as "
            "eligible, compared with those enrolled for the year.",
            ("fsabd#59",),
            quote=quote,
        ),
        example,
        corpus,
    )
    assert isinstance(shown, ShownClaim)


def test_a_claims_array_sent_as_a_json_string_is_parsed_strictly() -> None:
    stringified = json.dumps(
        [{"kind": "figure", "text": "100 students.", "cites": ["x"]}]
    )
    parsed = parse_claims({"claims": stringified})
    assert parsed == [Claim("figure", "100 students.", ("x",), None)]
    broken = parse_claims(
        {"claims": '[{"kind": "figure", "text": "a "b" c", "cites": []}]'}
    )
    assert [c.reason for c in broken if isinstance(c, WithheldClaim)] == ["malformed"]
