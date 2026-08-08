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

import string

import pytest

from homeroom.enrollment import GRADE_COLUMNS
from homeroom.i18n import (
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
    category_name,
    cde_text_lang,
    family_name,
    format_number,
    grade_name,
    strings,
    text,
)
from homeroom.profiles import CATEGORY_NAMES, SUBGROUP_CODES, SUBGROUP_FAMILIES


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
