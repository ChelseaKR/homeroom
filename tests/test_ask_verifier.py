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
