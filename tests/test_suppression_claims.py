"""The documents' claim about which subgroup CDE withholds most often.

This project's argument is that suppression falls hardest on the smallest
groups. The single most-withheld category in the acquired 2024-25 chronic
absenteeism file is `GX`, Non-binary, at 97.3% of the schools that report it at
all. Until 2026-08-29 no document in this repository named it: README.md,
docs/ROADMAP.md, CHANGELOG.md, the residual-risk register and the showcase
table all called `RI` the maximum, which it is not, and the risk register said
two categories exceed 94% when three do. `GX` is a rendered subgroup, in
`ABSENTEEISM_SUBGROUP_FAMILIES`' `gender` family and on Birch Lane's published
page in both languages, so nothing about it was parse-only or invisible. The
project's own thesis omitted the group its own thesis is about.

Nothing was gating any of it, so this file does, on the shape
`tests/test_i18n.py::test_the_key_count_the_documents_state_is_the_count_that_exists`
uses for the i18n key count: derive the figure, hold every document that states
it to that figure, and fail if a document stops making the claim.

What plays the part of the catalog here is the table in
`docs/SUPPRESSION-SHOWCASE.md`. The live source is `coverage.json`, which is
built from acquired files that are never in git and that CI never has, so the
showcase table is the committed record of those counts and is checked three
ways: its own arithmetic, against the rendered subgroup codes, and -- on a
machine that does hold the acquired files -- against `data/out/coverage.json`
itself. The other documents are then held to the table.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeroom.profiles import (
    ABSENTEEISM_CATEGORY_NAMES,
    ABSENTEEISM_SUBGROUP_CODES,
    ABSENTEEISM_SUBGROUP_FAMILIES,
)

ROOT = Path(__file__).resolve().parent.parent
SHOWCASE = ROOT / "docs" / "SUPPRESSION-SHOWCASE.md"
COVERAGE = ROOT / "data" / "out" / "coverage.json"

# Every document that states which subgroup is withheld most often. A document
# dropping the claim fails here rather than passing on an empty match.
DOCS_NAMING_THE_MOST_WITHHELD = (
    "README.md",
    "CHANGELOG.md",
    "docs/ROADMAP.md",
    "docs/SUPPRESSION-SHOWCASE.md",
    "docs/audits/residual-risk-register.md",
)

# `| `GX` (Non-binary) | 2,045 | 55 | 1,990 | 97.3% |`
SHOWCASE_ROW = re.compile(
    r"^\|\s*`([A-Z]{2})`[^|]*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|"
    r"\s*([\d.]+)%\s*\|$",
    re.M,
)

# The withheld share, wherever a document states one.
PERCENT = re.compile(r"([0-9]{1,3}\.[0-9])%")

# Every subgroup code a document mentions in backticks.
CODE = re.compile(r"`([A-Z]{2})`")

# A correction here quotes the figure it corrects. Quoted text is history, the
# same convention `tests/test_published_site.py` reads around.
QUOTED = re.compile(r'"[^"\n]*"')

ABOVE = 94.0


def showcase_table() -> dict[str, tuple[int, int, int, float]]:
    """Each row of the showcase table: code -> (with any row, published, withheld, %)."""
    rows = {
        m.group(1): (
            int(m.group(2).replace(",", "")),
            int(m.group(3).replace(",", "")),
            int(m.group(4).replace(",", "")),
            float(m.group(5)),
        )
        for m in SHOWCASE_ROW.finditer(SHOWCASE.read_text(encoding="utf-8"))
    }
    return rows


def most_withheld() -> tuple[str, tuple[int, int, int, float]]:
    return max(showcase_table().items(), key=lambda item: item[1][3])


def test_the_showcase_table_is_readable_at_all() -> None:
    """The floor: every check below reads this table, so an unparsed table is a pass."""
    rows = showcase_table()
    assert len(rows) >= 6, sorted(rows)
    assert "GX" in rows, sorted(rows)
    assert "RI" in rows, sorted(rows)


def test_every_showcase_row_adds_up_and_rounds_correctly() -> None:
    """A row is three counts and a percentage, and the percentage is derivable.

    `RD` read 79.7% here where 7,806 of 9,801 is 79.6449, rounding to 79.6.
    Every other row rounded correctly, which is what makes a hand-kept table
    worth gating rather than trusting.
    """
    for code, (with_row, published, withheld, stated) in showcase_table().items():
        assert published + withheld == with_row, (code, published, withheld, with_row)
        assert stated == round(withheld / with_row * 100, 1), (
            code,
            stated,
            withheld / with_row * 100,
        )


def test_the_showcase_table_names_only_codes_that_are_real() -> None:
    for code in showcase_table():
        assert code in ABSENTEEISM_CATEGORY_NAMES, code


def test_the_most_withheld_category_is_one_the_pages_actually_render() -> None:
    """A parse-only code would be a different, weaker claim.

    `GX` is in the `gender` family, so it renders on every school page in both
    languages. Grade-span codes are recognized but never rendered; if the
    maximum were ever one of those, the sentence in the README would have to
    say so instead of implying a family reads it.
    """
    code, _ = most_withheld()
    assert code in ABSENTEEISM_SUBGROUP_CODES, code
    assert any(code in family for family in ABSENTEEISM_SUBGROUP_FAMILIES.values())


def test_every_document_naming_the_most_withheld_subgroup_names_the_same_one() -> None:
    """The claim, held across every document that makes it.

    Each document must name the maximum's code and state its share. `RI`'s
    95.4% is allowed to appear beside it -- it is a true figure and the honest
    sentence carries both -- but the maximum's own figure has to be there.
    """
    code, (_, _, _, share) = most_withheld()
    for name in DOCS_NAMING_THE_MOST_WITHHELD:
        body = (ROOT / name).read_text(encoding="utf-8")
        assert f"`{code}`" in body, (
            f"{name} no longer names `{code}`, the most-withheld subgroup"
        )
        assert f"{share}%" in body, (
            f"{name} no longer states {share}%, the share `{code}` is withheld at"
        )


def test_no_document_states_a_withheld_share_the_table_does_not_carry() -> None:
    """A percentage in the prose is a claim, and this is where they are checked.

    Bounded on purpose: only shares at or above the table's smallest one are
    considered, so an unrelated figure elsewhere in a document is not swept in.
    """
    known = {stated for *_, stated in showcase_table().values()}
    floor = min(known)
    for name in DOCS_NAMING_THE_MOST_WITHHELD:
        body = QUOTED.sub('""', (ROOT / name).read_text(encoding="utf-8"))
        for line in body.splitlines():
            if not CODE.search(line):
                continue
            for match in PERCENT.finditer(line):
                stated = float(match.group(1))
                if stated < floor:
                    continue
                assert stated in known, (name, stated, sorted(known))


def test_the_count_of_categories_over_94_percent_is_the_count_stated() -> None:
    """The risk register said two. Three exceed 94%, and the maximum was one of them."""
    over = sorted(
        code for code, (*_, stated) in showcase_table().items() if stated > ABOVE
    )
    assert len(over) == 3, over
    register = (ROOT / "docs" / "audits" / "residual-risk-register.md").read_text(
        encoding="utf-8"
    )
    assert "three subgroup categories" in register, (
        "RR-05 no longer states how many categories exceed 94%"
    )
    for code in over:
        assert f"`{code}`" in SHOWCASE.read_text(encoding="utf-8"), code


def test_the_documents_do_not_share_one_denominator_between_categories() -> None:
    """9,801 is `TA`'s and the race codes'. It is not `GX`'s, and was written as if.

    The showcase said "Among the 9,801 schools that publish any row for a given
    category", which is true of every row it happened to list and false of the
    file. Each row now carries its own.
    """
    rows = showcase_table()
    assert len({with_row for with_row, *_ in rows.values()}) > 1, rows
    assert rows["GX"][0] != rows["RI"][0], rows


def test_the_showcase_table_matches_coverage_json_where_it_can_be_read() -> None:
    """The committed table against the artifact, on a machine that has the files.

    CI has neither `data/raw/` nor `data/out/`, so this cannot be the only check
    and is not: everything above runs everywhere. This one runs where the
    acquired files are, which is where the table is edited.
    """
    if not COVERAGE.is_file():
        return
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    if coverage.get("is_fixture", True):
        return
    live = coverage["measures"]["chronic_absenteeism"]["subgroups"]
    for code, (with_row, published, withheld, _) in showcase_table().items():
        if code not in live:
            continue
        assert live[code]["reported"] == published, (code, live[code])
        assert live[code]["suppressed"] == withheld, (code, live[code])
        assert live[code]["reported"] + live[code]["suppressed"] == with_row, code
    ranked = {
        code: value["suppressed"] / (value["reported"] + value["suppressed"])
        for code, value in live.items()
        if value["reported"] + value["suppressed"]
    }
    assert max(ranked, key=lambda code: ranked[code]) == most_withheld()[0], ranked
