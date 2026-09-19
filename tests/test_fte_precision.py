"""D5's FTE counts, printed as CDE published them: no rounding (issue #131).

The D5 section says "every figure here is printed exactly as the state published
it", and ADR 0005 rule 1 says the counts are copied. Until 2026-09-18 the pages
printed every non-integer to one decimal, and ``tamo2324.txt`` publishes FTE
counts to two: 20,844 of its 80,512 whole-school count cells (25.9%) printed a
different number from the file, and 184 non-zero cells printed as ``0.0``.

The check that already existed could not see it.
``test_every_assignment_cell_is_exactly_what_the_pipeline_holds`` builds its
expected digits with ``format_number``, the function that rounded, so the page
and the expectation rounded together and agreed. Every value in
``fixtures/tamo.sample.txt`` is also a whole number, and a whole number prints
the same at any precision.

So the expected value here comes from the file's own text, read with ``csv``
and compared as a :class:`~decimal.Decimal`, and never from anything in
``homeroom``. The page-side digits are read back out of the rendered markup.
The two are compared as numbers, so ``0.40`` in the file and ``0.4`` on the
page agree (the same number, written without the trailing zero) while ``29.76``
and ``29.8`` do not.

``fixtures/tamo.fte-precision.sample.txt`` is shaped like the acquired file.
Its statewide row is CDE's own whole-state row from ``tamo2324.txt``, copied as
published. Every other value is synthetic, chosen for its digits: ``0.1``,
``0.125``, ``0.25``, ``0.33``, ``0.5``, ``0.667`` and ``1.0``, the two-decimal
counts from the issue, a non-zero figure that one decimal printed as ``0.0``,
CDE's trailing zeros, a genuine zero, a masked school, an empty cell, and a
school the file never mentions.
"""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from homeroom import render
from homeroom.i18n import LOCALES, Locale, format_number
from homeroom.measures import MeasureStatus, parse_cell
from homeroom.site import build_site
from tests.test_pages import (
    ABSENT,
    CHARTER,
    DIRECTORY,
    ENROLLMENT,
    EXAMPLE,
    NUMBER,
    SCHOOLS,
    named_section,
    page,
    parse_markup,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "fixtures" / "tamo.fte-precision.sample.txt"
ACQUIRED = ROOT / "data" / "raw" / "tamo2324.txt"

#: The fifteen cells of a D5 column, in the order the page prints them: the total,
#: the seven outcome counts, then the seven outcome shares. Written out from the
#: file's header rather than imported from ``homeroom.assignments``, so a parser
#: that read the wrong column would disagree with this list instead of agreeing
#: with itself.
COUNT_COLUMNS = (
    "Total FTE",
    "Clear FTE (count)",
    "Out-of-Field FTE (count)",
    "Intern FTE (count)",
    "Ineffective FTE (count)",
    "Incomplete FTE (count)",
    "Unknown FTE (count)",
    "N/A FTE (count)",
)
PERCENT_COLUMNS = (
    "Clear FTE (percent)",
    "Out-of-Field FTE (percent)",
    "Intern FTE (percent)",
    "Ineffective FTE (percent)",
    "Incomplete FTE (percent)",
    "Unknown FTE FTE (percent)",
    "N/A FTE (percent)",
)
PAGE_COLUMNS = COUNT_COLUMNS + PERCENT_COLUMNS

#: The values the issue and the brief named, each of which the fixture carries and
#: the round trip below must actually compare, not merely be able to.
REQUIRED_VALUES = frozenset(
    Decimal(v)
    for v in (
        "0.1",
        "0.125",
        "0.25",
        "0.33",
        "0.5",
        "0.667",
        "1.0",
        "29.76",
        "27.06",
        "0.04",
        "278927.09",
    )
)


def one_decimal(value: float) -> str:
    """``format_number`` as it was until issue #131: every non-integer to one place."""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}"


# ----------------------------------------------------------------------------------
# The file's side, read without homeroom
# ----------------------------------------------------------------------------------


def whole_row(row: dict[str, str]) -> bool:
    """CDE's own aggregate for an entity: every dimension at its "all" value."""
    return (
        row["Teacher Experience Level"].strip() == "ALL"
        and row["Teacher Credential Level"].strip() == "ALL"
        and row["Subject Area"].strip() == "TA"
    )


def context_row(row: dict[str, str]) -> bool:
    """A district or statewide row a page reads beside the school's own."""
    return (
        whole_row(row)
        and row["Charter School"].strip() == "All"
        and row["DASS"].strip() == "All"
        and row["School Grade Span"].strip() == "ALL"
    )


def source_rows(path: Path) -> dict[str, dict[str, str]]:
    """The rows a page reads: ``"state"``, ``"district:<CC><DDDDD>"``, or a CDS.

    Decoded the way the pipeline decodes: the acquired file is not valid UTF-8 in
    some school names, which no figure read here depends on.
    """
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            level = row["Aggregate Level"].strip()
            county, district = row["County Code"].strip(), row["District Code"].strip()
            if level == "T" and context_row(row):
                rows["state"] = row
            elif level == "D" and context_row(row):
                rows[f"district:{county:0>2}{district:0>5}"] = row
            elif level == "S" and whole_row(row):
                school = row["School Code"].strip()
                rows[f"{county:0>2}{district:0>5}{school:0>7}"] = row
    return rows


def expected_cell(raw: str | None) -> tuple[str, Decimal | None]:
    """The state a cell must render in, and the number it must state if any."""
    text = (raw or "").strip()
    if text == "":
        return "m-nothing", None
    if text == "*":
        return "m-withheld", None
    value = Decimal(text)
    return ("m-zero" if value == 0 else "m-number"), value


# ----------------------------------------------------------------------------------
# The page's side
# ----------------------------------------------------------------------------------


def printed_cells(markup: str, scope: str) -> list[tuple[str, str]]:
    """``(state class, digits as printed)`` for one column of the D5 section."""
    document = parse_markup(named_section(markup, "assignments"))
    cells: list[tuple[str, str]] = []
    for classes, body in document.cells:
        if f"c-{scope}" not in classes:
            continue
        state = next(name for name in classes if name.startswith("m-"))
        digits = NUMBER.search(body)
        cells.append((state, digits.group(0) if digits else ""))
    return cells


def round_trip(
    built: Path, rows: dict[str, dict[str, str]]
) -> tuple[list[str], Counter[str], set[Decimal]]:
    """Every D5 cell, on every page, against the file's own text.

    Returns the disagreements, how many cells were compared in each state, and
    every published number that was compared, so a caller can check the
    comparison reached what it was meant to rather than trusting an empty list.
    """
    problems: list[str] = []
    states: Counter[str] = Counter()
    compared: set[Decimal] = set()
    for cds in SCHOOLS:
        district = rows.get(f"district:{cds[:7]}")
        for locale in LOCALES:
            markup = page(built, cds, locale).read_text(encoding="utf-8")
            for scope, row in (
                ("school", rows.get(cds)),
                ("district", district),
                ("state", rows.get("state")),
            ):
                printed = printed_cells(markup, scope)
                where = f"{cds} {locale} {scope}"
                if len(printed) != len(PAGE_COLUMNS):
                    problems.append(f"{where}: {len(printed)} cells printed")
                    continue
                for column, (state, digits) in zip(PAGE_COLUMNS, printed, strict=True):
                    want_state, want = expected_cell(
                        row.get(column) if row is not None else None
                    )
                    states[want_state] += 1
                    got = Decimal(digits.replace(",", "")) if digits else None
                    if state != want_state or got != want:
                        problems.append(
                            f"{where} {column}: file {want} ({want_state}), "
                            f"page {digits or 'no digits'} ({state})"
                        )
                    elif want is not None:
                        compared.add(want)
    return problems, states, compared


def build(out: Path) -> Path:
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        assignments=SOURCE,
    )
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("fte-precision"))


# ----------------------------------------------------------------------------------
# The round trip, on the committed fixture: runs everywhere, CI included
# ----------------------------------------------------------------------------------


def test_the_fixture_is_the_one_the_round_trip_is_written_against() -> None:
    """The cases below depend on the rows being there; say so if they are not."""
    rows = source_rows(SOURCE)
    assert set(rows) == {"state", "district:0110017", EXAMPLE, CHARTER}
    assert ABSENT not in rows
    assert rows[EXAMPLE]["Total FTE"] == "1.0"
    assert rows[EXAMPLE]["N/A FTE (count)"] == ""
    assert {rows[CHARTER][column] for column in PAGE_COLUMNS} == {"*"}


def test_every_fte_cell_on_every_page_is_the_number_in_the_file(built: Path) -> None:
    """School, district and statewide columns, both languages, all three schools.

    And it has to have compared something. An empty list of disagreements over
    no cells is what a broken reader would also return, so the states and the
    values actually reached are checked as well: every value the fixture was
    written to carry, the genuine zero, the empty cells, the masked school and
    the school the file never mentions.
    """
    problems, states, compared = round_trip(built, source_rows(SOURCE))
    assert problems == []
    assert compared >= REQUIRED_VALUES, sorted(REQUIRED_VALUES - compared)
    assert states["m-number"] and states["m-zero"]
    assert states["m-nothing"] and states["m-withheld"]
    assert sum(states.values()) == len(SCHOOLS) * len(LOCALES) * 3 * len(PAGE_COLUMNS)


def test_the_round_trip_fails_on_the_one_decimal_format(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control: the pre-#131 formatter, put back, is caught.

    The renderer reads ``format_number`` from its own module namespace at call
    time, so replacing it there is the whole of the old behavior. The mutation
    is checked to have landed (it was called, and the pages it wrote differ from
    the real build's) before its failure is counted as the round trip's doing.
    """
    calls: list[float] = []

    def rounded(value: float) -> str:
        calls.append(value)
        return one_decimal(value)

    monkeypatch.setattr(render, "format_number", rounded)
    sabotaged = build(tmp_path / "one-decimal")
    monkeypatch.undo()

    assert calls, "the one-decimal formatter was never called; nothing was tested"
    example = page(sabotaged, EXAMPLE, "en").read_text(encoding="utf-8")
    assert example != page(built, EXAMPLE, "en").read_text(encoding="utf-8")

    problems, _, _ = round_trip(sabotaged, source_rows(SOURCE))
    joined = "\n".join(problems)
    for column, file_value, page_value in (
        ("Out-of-Field FTE (count)", "0.125", "0.1"),
        ("Unknown FTE (count)", "0.667", "0.7"),
        ("Ineffective FTE (count)", "0.33", "0.3"),
    ):
        assert (
            f"{EXAMPLE} en school {column}: file {file_value} (m-number), "
            + (f"page {page_value} (m-number)")
            in joined
        ), joined
    assert "district Total FTE: file 29.76 (m-number), page 29.8" in joined
    # The worst of it: a figure the state published as non-zero, printed as a zero.
    assert "district Ineffective FTE (count): file 0.04 (m-number), page 0.0" in joined
    assert "state Total FTE: file 278927.09 (m-number), page 278,927.1" in joined


@pytest.mark.parametrize(
    ("raw", "printed"),
    [
        ("0.1", "0.1"),
        ("0.125", "0.125"),
        ("0.25", "0.25"),
        ("0.33", "0.33"),
        ("0.5", "0.5"),
        ("0.667", "0.667"),
        ("1.0", "1"),
        ("1.00", "1"),
        ("0.40", "0.4"),
        ("0.04", "0.04"),
        ("29.76", "29.76"),
        ("278927.09", "278,927.09"),
        ("0.00", "0"),
    ],
)
def test_a_published_fte_prints_as_the_same_number(raw: str, printed: str) -> None:
    """One cell at a time, through the same parse the pipeline uses."""
    measure = parse_cell(raw, field="Total FTE", where="test")
    assert format_number(measure.number()) == printed
    assert Decimal(printed.replace(",", "")) == Decimal(raw)


@pytest.mark.parametrize("locale", LOCALES)
def test_missing_stays_nothing_published_never_zero(
    built: Path, locale: Locale
) -> None:
    """The empty N/A count, and the school the file never mentions, print no digit."""
    markup = page(built, EXAMPLE, locale).read_text(encoding="utf-8")
    na = printed_cells(markup, "school")[COUNT_COLUMNS.index("N/A FTE (count)")]
    assert na == ("m-nothing", "")
    absent = page(built, ABSENT, locale).read_text(encoding="utf-8")
    assert set(printed_cells(absent, "school")) == {("m-nothing", "")}


# ----------------------------------------------------------------------------------
# The round trip, on the acquired file: runs where `data/raw/` is
# ----------------------------------------------------------------------------------


def test_every_fte_cell_in_the_acquired_file_prints_as_published() -> None:
    """Every whole-school and context cell of ``tamo2324.txt``, as the pages print it.

    CI has no ``data/raw/`` and never will, so this skips there and says how much
    it did not compare; the fixture round trip above is what runs everywhere. On
    the machine that publishes, it covers every cell a publish can print --
    10,064 schools' whole-school rows and the district and statewide rows beside
    them -- and runs the one-decimal format over the same cells as its own control,
    so a pass here is a comparison that could have failed on this data.
    """
    if not ACQUIRED.is_file():
        pytest.skip(
            f"{ACQUIRED.relative_to(ROOT)} is absent (never in git or CI), so 0 "
            "acquired FTE cells were compared here; "
            "test_every_fte_cell_on_every_page_is_the_number_in_the_file compares "
            "the fixture's"
        )
    cells = 0
    after: list[str] = []
    before = 0
    with ACQUIRED.open(encoding="utf-8", errors="replace", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle, delimiter="\t"), start=2):
            level = row["Aggregate Level"].strip()
            if not (
                (level == "S" and whole_row(row))
                or (level in ("D", "T") and context_row(row))
            ):
                continue
            for column in PAGE_COLUMNS:
                measure = parse_cell(row[column], field=column, where=str(line))
                if measure.status is not MeasureStatus.REPORTED:
                    continue
                cells += 1
                source = Decimal(row[column].strip())
                if Decimal(format_number(measure.number()).replace(",", "")) != source:
                    after.append(f"line {line} {column}: {row[column]!r}")
                if Decimal(one_decimal(measure.number()).replace(",", "")) != source:
                    before += 1
    assert cells > 0, "the acquired file yielded no published FTE cell to compare"
    assert before > 0, (
        f"the one-decimal control found nothing wrong in {cells:,} cells, so "
        "this comparison cannot tell the two formats apart on this file"
    )
    assert after == [], (
        f"{len(after):,} of {cells:,} cells print a different number from the "
        f"file (the one-decimal format: {before:,}); first: {after[:5]}"
    )
