"""The EN/ES parity gate.

English and Spanish are peers here, not a language and its afterthought. These
tests fail when a key exists in one locale and not the other, when a Spanish
string was copied from the English and never translated, when a translated
template loses a placeholder (which is how a number quietly vanishes from a
sentence), and when the pipeline gains a category, grade, or subgroup family that
only one language can name.

What no test can check is whether the Spanish is *good*. CONTRIBUTING.md says
Spanish review is the most valuable outside contribution this repo can receive.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest

from homeroom.enrollment import GRADE_COLUMNS
from homeroom.i18n import (
    ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE,
    CATEGORY_NAMES_BY_LOCALE,
    DELIBERATELY_SHARED,
    FAMILY_NAMES,
    GRADE_NAMES,
    LOCALE_NAMES,
    LOCALES,
    OTHER_LOCALE,
    PLURAL_SAFE_CATALOGS,
    UI,
    Locale,
    absenteeism_category_name,
    category_name,
    cde_text_lang,
    family_name,
    format_number,
    grade_name,
    strings,
    text,
)
from homeroom.profiles import (
    ABSENTEEISM_CATEGORY_NAMES,
    ABSENTEEISM_SUBGROUP_CODES,
    ABSENTEEISM_SUBGROUP_FAMILIES,
    CATEGORY_NAMES,
    SUBGROUP_CODES,
    SUBGROUP_FAMILIES,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS_STATING_THE_KEY_COUNT = ("README.md", "CHANGELOG.md", "docs/ROADMAP.md")
KEYS_PER_LOCALE = re.compile(r"(\d[\d,]*) keys per locale")
STRINGS = re.compile(r"(\d[\d,]*)\s+strings\b")


def placeholders(template: str) -> set[str]:
    return {
        name for _, name, _, _ in string.Formatter().parse(template) if name is not None
    }


def test_every_catalog_carries_every_locale() -> None:
    for catalog in PLURAL_SAFE_CATALOGS:
        assert set(catalog) == set(LOCALES)


def test_no_key_exists_in_one_locale_and_not_the_other() -> None:
    """The gate the roadmap wires at M4: parity of keys, catalog by catalog."""
    for catalog in PLURAL_SAFE_CATALOGS:
        english = set(catalog["en"])
        for locale in LOCALES:
            assert set(catalog[locale]) == english


def test_no_spanish_string_was_left_as_its_english_original() -> None:
    untranslated = sorted(
        key
        for catalog in PLURAL_SAFE_CATALOGS
        for key, value in catalog["en"].items()
        if catalog["es"][key] == value and key not in DELIBERATELY_SHARED
    )
    assert untranslated == []


def test_the_shared_string_list_stays_short_and_stays_true() -> None:
    """Guards the exception list itself, both ways.

    Short, so it cannot become a parking space for anything that fails the test
    above; and still accurate, so a key that later diverged does not sit here
    quietly exempting a string that no longer needs exempting.
    """
    assert len(DELIBERATELY_SHARED) <= 3
    shared = {
        key
        for catalog in PLURAL_SAFE_CATALOGS
        for key, value in catalog["en"].items()
        if catalog["es"][key] == value
    }
    assert shared >= DELIBERATELY_SHARED


def test_templates_keep_their_placeholders_in_both_languages() -> None:
    for key, english in UI["en"].items():
        assert placeholders(UI["es"][key]) == placeholders(english), key


def test_no_string_is_empty_in_either_language() -> None:
    for catalog in PLURAL_SAFE_CATALOGS:
        for locale in LOCALES:
            for key, value in catalog[locale].items():
                assert value.strip(), (locale, key)


def test_every_reporting_category_the_pipeline_knows_has_both_names() -> None:
    """A category added upstream cannot reach a Spanish page as an English label.

    ``profiles.CATEGORY_NAMES`` is what the build already refuses to run without;
    this ties the Spanish catalog to it, so the two move together or the gate
    fails.
    """
    assert set(CATEGORY_NAMES_BY_LOCALE["es"]) == set(CATEGORY_NAMES)
    for code in SUBGROUP_CODES:
        for locale in LOCALES:
            assert category_name(locale, code)


def test_every_grade_column_and_subgroup_family_has_both_names() -> None:
    for locale in LOCALES:
        assert set(GRADE_NAMES[locale]) == set(GRADE_COLUMNS)
        assert set(FAMILY_NAMES[locale]) == set(SUBGROUP_FAMILIES)
        for grade in GRADE_COLUMNS:
            assert grade_name(locale, grade)
        for family in SUBGROUP_FAMILIES:
            assert family_name(locale, family)


def test_every_absenteeism_category_the_pipeline_knows_has_both_names() -> None:
    """The D3 analogue of the D2 parity check above."""
    assert set(ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE["es"]) == set(
        ABSENTEEISM_CATEGORY_NAMES
    )
    for code in ABSENTEEISM_SUBGROUP_CODES:
        for locale in LOCALES:
            assert absenteeism_category_name(locale, code)


def test_absenteeism_subgroup_families_are_a_subset_of_d2s_family_names() -> None:
    """D3 renders three of D2's four subgroup families (no English-language-
    acquisition breakdown in this file) and reuses their existing names rather
    than duplicating a translation catalog for the same family labels."""
    assert set(ABSENTEEISM_SUBGROUP_FAMILIES) < set(SUBGROUP_FAMILIES)
    for locale in LOCALES:
        for family in ABSENTEEISM_SUBGROUP_FAMILIES:
            assert family_name(locale, family)


def test_a_missing_key_raises_rather_than_falling_back_to_english() -> None:
    """A silent English fallback is what makes a half-translated page shippable."""
    with pytest.raises(KeyError):
        text("es", "no_such_key")


def test_each_locale_is_named_in_its_own_language_and_links_to_the_other() -> None:
    assert set(LOCALE_NAMES) == set(LOCALES)
    for locale in LOCALES:
        assert OTHER_LOCALE[locale] != locale
        assert OTHER_LOCALE[OTHER_LOCALE[locale]] == locale


def test_cde_text_is_marked_english_on_spanish_pages_only() -> None:
    """WCAG 2.2 SC 3.1.2: CDE publishes school names in English only."""
    assert cde_text_lang("es") == "en"
    assert cde_text_lang("en") is None


def test_strings_returns_the_catalog_for_one_locale() -> None:
    for locale in LOCALES:
        assert strings(locale) is UI[locale]
        assert strings(locale)["site_name"] == "Homeroom"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0"), (1, "1"), (1234, "1,234"), (5731260, "5,731,260"), (85.5, "85.5")],
)
def test_counts_are_grouped_the_way_both_locales_write_them(
    value: float, expected: str
) -> None:
    assert format_number(value) == expected


@pytest.mark.parametrize("locale", LOCALES)
def test_every_ui_string_is_reachable_through_the_public_helper(
    locale: Locale,
) -> None:
    for key in UI["en"]:
        assert text(locale, key)


# ----------------------------------------------------------------------------------
# The figures the documents state about the catalogs
# ----------------------------------------------------------------------------------


def test_the_key_count_the_documents_state_is_the_count_that_exists() -> None:
    """A number in the prose is a claim, and this project counts its claims.

    README.md, CHANGELOG.md and docs/ROADMAP.md all state how many keys each
    locale carries. Nothing tied those figures to the catalogs, and all three
    drifted the moment the district and statewide columns added two interface
    keys. A document that stops making the claim fails here too, rather than
    passing on an empty match: the assertion is that each file states the
    count, and states it correctly.
    """
    keys_per_locale = sum(len(catalog["en"]) for catalog in PLURAL_SAFE_CATALOGS)
    total_strings = keys_per_locale * len(LOCALES)
    for name in DOCS_STATING_THE_KEY_COUNT:
        body = (ROOT / name).read_text(encoding="utf-8")
        stated = {
            int(match.group(1).replace(",", ""))
            for match in KEYS_PER_LOCALE.finditer(body)
        }
        assert stated, f"{name} no longer states a key count"
        assert stated == {keys_per_locale}, (name, sorted(stated), keys_per_locale)
        counted_strings = {
            int(match.group(1).replace(",", "")) for match in STRINGS.finditer(body)
        }
        assert counted_strings <= {total_strings}, (name, sorted(counted_strings))


def test_the_roadmap_ledger_breaks_the_key_count_down_correctly() -> None:
    """The ledger row splits the total four ways; each part is counted here."""
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    row = next(line for line in roadmap.splitlines() if KEYS_PER_LOCALE.search(line))
    keys_per_locale = sum(len(catalog["en"]) for catalog in PLURAL_SAFE_CATALOGS)
    assert (
        f"{keys_per_locale} keys per locale, "
        f"{keys_per_locale * len(LOCALES)} strings" in row
    )
    for count, label in (
        (len(UI["en"]), "interface"),
        (len(CATEGORY_NAMES_BY_LOCALE["en"]), "reporting categories"),
        (len(GRADE_NAMES["en"]), "grade spans"),
        (len(FAMILY_NAMES["en"]), "subgroup families"),
        (
            len(ABSENTEEISM_CATEGORY_NAMES_BY_LOCALE["en"]),
            "chronic-absenteeism categories",
        ),
    ):
        assert f"{count} {label}" in row, (label, count, row)


def test_the_roadmap_states_how_many_strings_are_deliberately_shared() -> None:
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    row = next(
        line
        for line in roadmap.splitlines()
        if line.startswith("| Spanish strings left identical")
    )
    assert f"| {len(DELIBERATELY_SHARED)}," in row, (row, sorted(DELIBERATELY_SHARED))
