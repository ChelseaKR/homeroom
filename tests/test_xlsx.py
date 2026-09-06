"""XLSX reading: the format's real hazards, and the refusals that replace guesses.

Every fixture here is assembled in the test with ``zipfile`` and hand-written
XML, rather than committed as a binary blob, so each one states on its face which
hazard it encodes and a reader can check the claim without a spreadsheet.

The shapes mirror the workbook the M5 survey opened (PROVENANCE.md D6,
``essappe2425data.xlsx``, 1,035,042 bytes, two sheets, header on row 7): a shared
string table most text lives in, a sheet that starts well below row 1, and rows
that write only the cells they have. Nothing here is a D6 parser and nothing here
knows what a D6 column means; the module under test reads a file format.

The hazard the whole file is organised around is that XLSX omits what is empty. A
reader that takes a value's column from its position among the cells present,
rather than from its own ``r`` attribute, shifts every value left into the wrong
column and raises nothing while doing it.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from homeroom.xlsx import (
    MAXIMUM_COLUMN,
    SHARED_STRINGS_PART,
    Limits,
    MalformedWorkbookError,
    SheetNotFoundError,
    WorkbookTooLargeError,
    read_rows,
    sheet_names,
)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SHEET = "ESSA School Data"
LEA_SHEET = "ESSA LEA Data"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
)


def sheet_xml(rows: str) -> str:
    return f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>'


def shared_strings_xml(strings: Sequence[str]) -> str:
    items = "".join(f"<si><t>{text}</t></si>" for text in strings)
    return f'<sst xmlns="{NS}" count="{len(strings)}">{items}</sst>'


def parts(
    rows: str = "",
    *,
    shared: Sequence[str] | None = None,
    sheet: str = SHEET,
    second_sheet_rows: str | None = None,
) -> dict[str, str]:
    """The members of a minimal but genuine .xlsx package.

    Returned as a dict so a test can delete a part, replace one with a broken
    one, or add its own, which is how the refusals below are provoked.
    """
    sheets = [(sheet, "rId1", "xl/worksheets/sheet1.xml")]
    members = {
        "[Content_Types].xml": CONTENT_TYPES,
        "xl/worksheets/sheet1.xml": sheet_xml(rows),
    }
    if second_sheet_rows is not None:
        sheets.append((LEA_SHEET, "rId2", "xl/worksheets/sheet2.xml"))
        members["xl/worksheets/sheet2.xml"] = sheet_xml(second_sheet_rows)
    members["xl/workbook.xml"] = (
        f'<workbook xmlns="{NS}" xmlns:r="{DOCUMENT_RELS_NS}"><sheets>'
        + "".join(
            f'<sheet name="{name}" sheetId="{index}" r:id="{rid}"/>'
            for index, (name, rid, _) in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    )
    members["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{PACKAGE_RELS_NS}">'
        + "".join(
            f'<Relationship Id="{rid}" Target="{target[len("xl/") :]}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet"/>'
            for _, rid, target in sheets
        )
        + "</Relationships>"
    )
    if shared is not None:
        members[SHARED_STRINGS_PART] = shared_strings_xml(shared)
    return members


def package(members: Mapping[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def workbook(rows: str = "", **kwargs: object) -> bytes:
    return package(parts(rows, **kwargs))  # type: ignore[arg-type]


# --- the format's hazards -------------------------------------------------


def test_a_shared_string_cell_reads_the_table_not_its_index() -> None:
    """`t="s"` cells hold an index, not text. A reader that returned the cell's
    own contents would publish `1` where the workbook says `Alameda`, and `1` is
    a perfectly plausible thing to see in a spreadsheet, so nothing downstream
    would notice."""
    rows = '<row r="1"><c r="A1" t="s"><v>1</v></c></row>'
    parsed = list(read_rows(workbook(rows, shared=["Alpine", "Alameda"]), SHEET))
    assert parsed[0].cells[0].value == "Alameda"


def test_a_shared_string_split_into_runs_reads_as_one_value() -> None:
    """One bolded word inside a header splits that string into several `<r>` runs
    with a `<t>` each. They are one value; reading only the first would silently
    truncate a column heading to its first fragment."""
    sst = (
        f'<sst xmlns="{NS}" count="1"><si>'
        "<r><rPr><b/></rPr><t>Per-Pupil </t></r><r><t>Expenditures</t></r>"
        "</si></sst>"
    )
    members = parts('<row r="7"><c r="A7" t="s"><v>0</v></c></row>')
    members[SHARED_STRINGS_PART] = sst
    parsed = list(read_rows(package(members), SHEET))
    assert parsed[0].cells[0].value == "Per-Pupil Expenditures"


def test_a_phonetic_guide_is_not_part_of_the_string_it_annotates() -> None:
    """`<rPh>` holds a reading guide *about* a string, in its own `<t>`. A reader
    that walked every descendant `<t>` would append it to the value, so a cell
    would come back with text the spreadsheet does not show in it."""
    sst = (
        f'<sst xmlns="{NS}" count="1"><si>'
        '<t>Yolo</t><rPh sb="0" eb="4"><t>guide</t></rPh><phoneticPr fontId="1"/>'
        "</si></sst>"
    )
    members = parts('<row r="1"><c r="A1" t="s"><v>0</v></c></row>')
    members[SHARED_STRINGS_PART] = sst
    parsed = list(read_rows(package(members), SHEET))
    assert parsed[0].cells[0].value == "Yolo"


def test_an_inline_string_reads_without_any_shared_table() -> None:
    """`t="inlineStr"` stores its text in the cell instead of the table. Writers
    that export rather than save use it, so a reader that only understood `t="s"`
    would find a sheet of empty cells and call it a sheet of empty cells."""
    rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>Napa</t></is></c></row>'
    parsed = list(read_rows(workbook(rows), SHEET))
    assert parsed[0].cells[0].value == "Napa"


def test_a_formula_result_reads_as_the_cached_string_it_holds() -> None:
    """`t="str"` is a formula whose result is text. The cell carries both the
    formula and its last computed value; the value is what the workbook
    publishes, and this reader does not evaluate anything."""
    rows = '<row r="1"><c r="A1" t="str"><f>A2&amp;""</f><v>Statewide</v></c></row>'
    parsed = list(read_rows(workbook(rows), SHEET))
    assert parsed[0].cells[0].value == "Statewide"


def test_a_cell_with_no_value_publishes_nothing_and_still_holds_its_column() -> None:
    """A cell written for its formatting alone carries no `<v>`. It is a real
    cell at a real column with no value, and saying so is different from
    dropping it, which would move every cell after it."""
    rows = (
        '<row r="1"><c r="A1"><v>3</v></c><c r="B1" s="2"/><c r="C1"><v>5</v></c></row>'
    )
    row = next(iter(read_rows(workbook(rows), SHEET)))
    assert [(cell.column, cell.value) for cell in row.cells] == [
        (1, "3"),
        (2, None),
        (3, "5"),
    ]
    assert row.values(3) == ("3", None, "5")


def test_skipped_cells_keep_every_value_in_the_column_it_was_written_in() -> None:
    """The hazard this module exists for. This row writes three of eleven cells;
    counting them puts the eleventh column's value in the third, which raises
    nothing and produces a full, wrong table. Column position comes from `K7`."""
    rows = (
        '<row r="7">'
        '<c r="A7"><v>1</v></c><c r="D7"><v>4</v></c><c r="K7"><v>11</v></c>'
        "</row>"
    )
    row = next(iter(read_rows(workbook(rows), SHEET)))
    assert len(row.cells) == 3
    assert [cell.column for cell in row.cells] == [1, 4, 11]
    assert row.values(11) == (
        "1",
        None,
        None,
        "4",
        None,
        None,
        None,
        None,
        None,
        None,
        "11",
    )
    assert row.value(11) == "11"
    assert row.value(2) is None


def test_skipped_rows_keep_their_own_numbers_and_invent_no_others() -> None:
    """Sheets skip rows as readily as cells -- the workbook the survey opened
    starts its header on row 7. Row numbers are the file's own, so a caller can
    say "the header is row 7" and mean it, and the six rows above it are absent
    rather than yielded empty."""
    rows = (
        '<row r="7"><c r="A7" t="inlineStr"><is><t>header</t></is></c></row>'
        '<row r="9"><c r="A9"><v>9</v></c></row>'
        '<row r="1048576"><c r="A1048576"><v>last</v></c></row>'
    )
    parsed = list(read_rows(workbook(rows), SHEET))
    assert [row.number for row in parsed] == [7, 9, 1048576]


def test_numbers_stay_the_text_the_workbook_wrote() -> None:
    """A numeric cell and a number stored as text are different cells, and this
    reader converts neither. `0123` keeps its leading zero, which is what makes
    an identifier survive; `1.2E-2` is not turned into a float here, because
    what a number *is* -- published, withheld, absent -- is `parse_cell`'s
    decision about a data source, not a decision about a file format."""
    rows = (
        '<row r="1">'
        '<c r="A1"><v>1234.56</v></c>'
        '<c r="B1" t="s"><v>0</v></c>'
        '<c r="C1" t="n"><v>1.2E-2</v></c>'
        '<c r="D1"><v>0</v></c>'
        "</row>"
    )
    row = next(iter(read_rows(workbook(rows, shared=["0123"]), SHEET)))
    assert row.values(4) == ("1234.56", "0123", "1.2E-2", "0")
    assert all(isinstance(cell.value, str) for cell in row.cells)


def test_both_sheets_are_readable_and_named_in_workbook_order() -> None:
    """A workbook is not one table. The survey's file carries a school sheet and
    an LEA sheet on different layouts, and picking the wrong one is a mistake a
    caller can only avoid by asking for a sheet by name."""
    book = workbook(
        '<row r="1"><c r="A1"><v>school</v></c></row>',
        second_sheet_rows='<row r="1"><c r="A1"><v>lea</v></c></row>',
    )
    assert sheet_names(book) == (SHEET, LEA_SHEET)
    assert next(iter(read_rows(book, LEA_SHEET))).cells[0].value == "lea"


def test_the_same_bytes_read_the_same_rows_twice() -> None:
    """Determinism, asserted rather than assumed: every artifact this project
    builds is byte-identical across re-runs, and a reader that iterated a dict
    or a set somewhere would break that from underneath."""
    book = workbook(
        '<row r="7"><c r="A7" t="s"><v>0</v></c><c r="C7"><v>2</v></c></row>'
        '<row r="8"><c r="B8" t="inlineStr"><is><t>x</t></is></c></row>',
        shared=["Yolo"],
    )
    assert list(read_rows(book, SHEET)) == list(read_rows(book, SHEET))


def test_a_workbook_reads_the_same_from_a_path_as_from_bytes(tmp_path: Path) -> None:
    """Acquired files live on disk in `data/raw/`, and holding a 1MB workbook in
    memory to read it is a choice the caller should not have to make."""
    book = workbook('<row r="1"><c r="A1"><v>7</v></c></row>')
    path = tmp_path / "workbook.xlsx"
    path.write_bytes(book)
    assert list(read_rows(path, SHEET)) == list(read_rows(book, SHEET))


# --- refusals -------------------------------------------------------------


def test_a_sheet_that_is_not_there_names_the_sheets_that_are() -> None:
    """A renamed sheet upstream is the D5 lesson in miniature: the failure has to
    be loud, and the message has to say what the file does carry, or the next
    step is guessing at a name."""
    with pytest.raises(SheetNotFoundError, match="ESSA School Data"):
        list(read_rows(workbook(), "School Data"))


def test_a_shared_string_index_past_the_table_refuses() -> None:
    """An index nothing answers is a hole in the file. Returning `""` would put
    an empty cell where the workbook has an unreadable one."""
    rows = '<row r="1"><c r="A1" t="s"><v>4</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="past the 2 the table holds"):
        list(read_rows(workbook(rows, shared=["a", "b"]), SHEET))


def test_a_shared_string_cell_with_no_table_at_all_refuses() -> None:
    """A workbook whose `sharedStrings.xml` is missing cannot resolve a single
    `t="s"` cell, and a sheet of unresolvable text must not read as a sheet of
    blanks."""
    rows = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match=r"no xl/sharedStrings\.xml part"):
        list(read_rows(workbook(rows), SHEET))


# "\u0661" is ARABIC-INDIC DIGIT ONE, written as an escape so the source stays
# unambiguous. It is here because `str.isdigit` says it is a digit and `int`
# reads it as 1, which is exactly the confusion the ASCII pattern refuses.
@pytest.mark.parametrize("index", ["two", "", "-1", "\u0661"])
def test_a_shared_string_index_that_is_not_an_index_refuses(index: str) -> None:
    """`str.isdigit` is true of Arabic-Indic digits, so a mojibaked cell would
    otherwise select a real string nobody pointed at -- the same trap
    `measures.PUBLISHED_NUMBER` documents, one layer down."""
    rows = f'<row r="1"><c r="A1" t="s"><v>{index}</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="is not an index"):
        list(read_rows(workbook(rows, shared=["a"]), SHEET))


@pytest.mark.parametrize("reference", ["C-7", "$C$7", "c7", "C0", "7C", "C7:D7"])
def test_a_cell_reference_that_does_not_parse_refuses(reference: str) -> None:
    """The reference is the only thing that says which column a value belongs to.
    If it cannot be read there is no fallback, because the fallback would be
    counting, which is the failure this reader is built to avoid."""
    rows = f'<row r="7"><c r="{reference}"><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="does not parse"):
        list(read_rows(workbook(rows), SHEET))


def test_a_reference_past_the_formats_own_limits_refuses() -> None:
    """`XFD` is the last column a spreadsheet has. A reference past it is not a
    cell any writer produced, so it is drift rather than a very wide sheet."""
    rows = '<row r="1"><c r="XFE1"><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="past the 16384"):
        list(read_rows(workbook(rows), SHEET))


def test_a_cell_with_no_reference_refuses() -> None:
    """The `r` attribute is optional in the format and mandatory here. Without it
    a reader must count, and a counted column in a format that omits empties is
    wrong exactly when the row is sparse -- which is most of them."""
    rows = '<row r="1"><c><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="no r attribute"):
        list(read_rows(workbook(rows), SHEET))


def test_a_row_with_no_number_refuses() -> None:
    """Same rule one level up. Rows are skipped in this format, so counting the
    rows that are present names them wrong the moment one is absent."""
    rows = '<row><c r="A1"><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="carries no r attribute"):
        list(read_rows(workbook(rows), SHEET))


@pytest.mark.parametrize("number", ["0", "1048577", "seven", "007"])
def test_a_row_number_that_is_not_a_row_number_refuses(number: str) -> None:
    """1,048,576 is the format's own last row. Anything outside that range, or
    not a plain number, is a row this reader will not place."""
    rows = f'<row r="{number}"/>'
    with pytest.raises(MalformedWorkbookError, match="is not a row number"):
        list(read_rows(workbook(rows), SHEET))


def test_a_cell_that_names_a_different_row_than_it_sits_in_refuses() -> None:
    """`<row r="7">` holding `A9` means the row number and the cell reference
    disagree about where the value is. Trusting either one silently files the
    value under a row it may not belong to."""
    rows = '<row r="7"><c r="A9"><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="appears inside row 7"):
        list(read_rows(workbook(rows), SHEET))


@pytest.mark.parametrize("second", ["A1", "B1"])
def test_cells_out_of_column_order_or_written_twice_refuse(second: str) -> None:
    """A column written twice in one row means one of the two values wins and
    nothing says which. Refusing is the only answer that does not pick."""
    rows = f'<row r="1"><c r="C1"><v>3</v></c><c r="{second}"><v>1</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="after column 3"):
        list(read_rows(workbook(rows), SHEET))


def test_rows_out_of_order_refuse() -> None:
    """Document order and row number have to be the same answer. If they are not,
    "the row after the header" and "row 8" stop meaning the same thing."""
    rows = (
        '<row r="9"><c r="A9"><v>1</v></c></row><row r="8"><c r="A8"><v>2</v></c></row>'
    )
    with pytest.raises(MalformedWorkbookError, match="follows row 9"):
        list(read_rows(workbook(rows), SHEET))


@pytest.mark.parametrize(
    ("kind", "value"),
    [("b", "1"), ("e", "#DIV/0!"), ("d", "2026-06-30T00:00:00")],
    ids=["boolean", "error", "iso-date"],
)
def test_a_cell_type_this_reader_has_not_been_verified_against_refuses(
    kind: str, value: str
) -> None:
    """Booleans, error cells and ISO dates are real parts of the format and none
    of them has an obvious text. `#DIV/0!` read as the string `#DIV/0!` would be
    a spreadsheet error rendered as data, and `1` read from a boolean would be a
    number nobody published."""
    rows = f'<row r="1"><c r="A1" t="{kind}"><v>{value}</v></c></row>'
    with pytest.raises(MalformedWorkbookError, match="has not been verified against"):
        list(read_rows(workbook(rows), SHEET))


def test_values_refuses_a_cell_past_the_width_the_caller_verified() -> None:
    """A twelfth column in an eleven-column layout is upstream drift. Dropping it
    to fit is the same silent shift as counting cells, one call later."""
    rows = '<row r="1"><c r="A1"><v>1</v></c><c r="L1"><v>12</v></c></row>'
    row = next(iter(read_rows(workbook(rows), SHEET)))
    with pytest.raises(MalformedWorkbookError, match="past the 11 columns"):
        row.values(11)


def test_values_refuses_a_width_that_is_not_a_width() -> None:
    """A caller asking for zero or a million columns has a bug, and padding to
    whatever they asked for would hide it."""
    row = next(iter(read_rows(workbook('<row r="1"/>'), SHEET)))
    with pytest.raises(ValueError, match="not between 1"):
        row.values(0)
    with pytest.raises(ValueError, match="not between 1"):
        row.values(MAXIMUM_COLUMN + 1)


def test_bytes_that_are_not_a_zip_refuse() -> None:
    """An .xlsx is a zip. A download that returned an HTML error page, or a file
    saved as .xls, fails here rather than somewhere less obvious."""
    with pytest.raises(MalformedWorkbookError, match="not a zip container"):
        list(read_rows(b"<html>404</html>", SHEET))


@pytest.mark.parametrize(
    "part",
    ["xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml"],
)
def test_a_missing_part_refuses(part: str) -> None:
    """Every .xlsx has all three. A zip that is missing one is damaged or is not
    this format, and either way there is nothing to read."""
    members = parts('<row r="1"><c r="A1"><v>1</v></c></row>')
    del members[part]
    with pytest.raises(MalformedWorkbookError, match="has no"):
        list(read_rows(package(members), SHEET))


def test_a_sheet_naming_a_relationship_that_is_not_defined_refuses() -> None:
    """The sheet's name lives in one part and its file in another. A workbook
    whose halves disagree cannot be read, and reading zero rows would look
    exactly like an empty sheet."""
    members = parts()
    members["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{PACKAGE_RELS_NS}"/>'
    )
    with pytest.raises(MalformedWorkbookError, match="does not define"):
        list(read_rows(package(members), SHEET))


def test_a_relationship_pointing_outside_the_workbook_refuses() -> None:
    """A target is a member name this reader would open. `../` is not a
    worksheet, and following one would mean reading whatever it pointed at."""
    members = parts()
    members["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{PACKAGE_RELS_NS}">'
        '<Relationship Id="rId1" Target="../../secrets.xml" Type="x"/>'
        "</Relationships>"
    )
    with pytest.raises(MalformedWorkbookError, match="points outside"):
        list(read_rows(package(members), SHEET))


def test_a_relationship_with_no_id_or_target_refuses() -> None:
    """Half a relationship locates nothing."""
    members = parts()
    members["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{PACKAGE_RELS_NS}"><Relationship Id="rId1"/>'
        "</Relationships>"
    )
    with pytest.raises(MalformedWorkbookError, match="no Id or no"):
        list(read_rows(package(members), SHEET))


def test_a_workbook_listing_no_sheets_refuses() -> None:
    """An empty `<sheets>` is not a workbook with nothing in it; it is a workbook
    this reader cannot address."""
    members = parts()
    members["xl/workbook.xml"] = f'<workbook xmlns="{NS}"><sheets/></workbook>'
    with pytest.raises(MalformedWorkbookError, match="lists no sheets"):
        sheet_names(package(members))


def test_a_sheet_entry_with_no_name_refuses() -> None:
    """A sheet nobody can name is a sheet nobody can ask for."""
    members = parts()
    members["xl/workbook.xml"] = (
        f'<workbook xmlns="{NS}" xmlns:r="{DOCUMENT_RELS_NS}"><sheets>'
        '<sheet sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    with pytest.raises(MalformedWorkbookError, match="no name or no relationship"):
        sheet_names(package(members))


def test_a_workbook_in_the_strict_ooxml_namespace_refuses_by_name() -> None:
    """Excel can save "Strict Open XML Spreadsheet", which is a different
    namespace and not what this reader was verified against. Refusing names the
    root element found, so the next person knows what they have."""
    members = parts()
    members["xl/workbook.xml"] = (
        '<workbook xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main"/>'
    )
    with pytest.raises(MalformedWorkbookError, match="transitional SpreadsheetML"):
        sheet_names(package(members))


@pytest.mark.parametrize(
    "part", ["xl/workbook.xml", "xl/worksheets/sheet1.xml"], ids=["workbook", "sheet"]
)
def test_xml_that_is_not_well_formed_refuses(part: str) -> None:
    """Truncated XML is what a half-written download looks like. Both the parts
    read whole and the sheet read incrementally have to fail on it."""
    members = parts('<row r="1"><c r="A1"><v>1</v></c></row>')
    members[part] = f'<worksheet xmlns="{NS}"><sheetData><row r="1">'
    with pytest.raises(MalformedWorkbookError, match="not well-formed XML"):
        list(read_rows(package(members), SHEET))


def test_a_row_outside_the_sheet_data_refuses() -> None:
    """Rows live in `<sheetData>`. One outside it is a document shape this reader
    was not verified against, and reading it anyway would mean guessing that a
    row somewhere else in the part means the same thing."""
    members = parts()
    members["xl/worksheets/sheet1.xml"] = (
        f'<worksheet xmlns="{NS}"><row r="1"><c r="A1"><v>1</v></c></row>'
        "<sheetData/></worksheet>"
    )
    with pytest.raises(MalformedWorkbookError, match="outside <sheetData>"):
        list(read_rows(package(members), SHEET))


def test_a_part_carrying_a_document_type_declaration_refuses() -> None:
    """`xml.etree` expands internal general entities -- measured on this
    interpreter, not assumed -- so a spreadsheet part with a DTD is how a tiny
    file becomes a large one inside the parser. A spreadsheet has no use for a
    DTD, so refusing costs nothing and closes the one expansion vector a file
    like this can reach."""
    members = parts()
    members["xl/worksheets/sheet1.xml"] = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE worksheet [<!ENTITY lol "lol">'
        '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;">]>'
        f'<worksheet xmlns="{NS}"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>&lol1;</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    with pytest.raises(MalformedWorkbookError, match="DOCTYPE"):
        list(read_rows(package(members), SHEET))


# --- bounds ---------------------------------------------------------------


def test_a_zip_bomb_is_refused_on_what_it_declares_before_anything_is_read() -> None:
    """A zip is attacker-shaped input even from a state agency. This fixture is a
    real one in miniature: five million zero bytes in a package of a few
    kilobytes. The refusal reads the central directory only, so the expansion
    never happens."""
    members: dict[str, str | bytes] = dict(parts())
    members["xl/bomb.bin"] = b"\0" * 5_000_000
    book = package(members)
    assert len(book) < 50_000, "the fixture is not compressed the way a bomb is"
    with pytest.raises(WorkbookTooLargeError, match="bytes uncompressed"):
        list(read_rows(book, SHEET, limits=Limits(maximum_archive_bytes=1_000_000)))


def test_a_part_larger_than_the_limit_refuses_while_it_is_being_read() -> None:
    """The per-part bound counts bytes actually produced rather than the size the
    zip header declares, because the header is written by whoever made the file.
    A sheet that keeps coming is cut off at the cap rather than read to the end
    to find out how big it was."""
    rows = "".join(
        f'<row r="{number}"><c r="A{number}"><v>{number}</v></c></row>'
        for number in range(1, 1_000)
    )
    with pytest.raises(WorkbookTooLargeError, match="byte limit"):
        list(
            read_rows(workbook(rows), SHEET, limits=Limits(maximum_member_bytes=2_000))
        )


def test_an_archive_with_more_members_than_the_limit_refuses() -> None:
    """A workbook is a handful of parts. Tens of thousands of them is a shape
    nobody publishes and every reader of it pays for."""
    with pytest.raises(WorkbookTooLargeError, match="members, past the"):
        sheet_names(workbook(), limits=Limits(maximum_members=2))


def test_the_defaults_read_a_workbook_the_size_the_survey_measured() -> None:
    """The bounds have to be above the real file or they are a gate on the wrong
    thing. CDE's 2024-25 workbook is 1,035,042 bytes over two sheets
    (PROVENANCE.md D6); the defaults leave two orders of magnitude of room."""
    defaults = Limits()
    assert defaults.maximum_archive_bytes >= 100 * 1024 * 1024
    assert defaults.maximum_member_bytes >= 16 * 1024 * 1024
    rows = "".join(
        f'<row r="{number}"><c r="A{number}"><v>{number}</v></c></row>'
        for number in range(1, 5_001)
    )
    assert len(list(read_rows(workbook(rows), SHEET))) == 5_000
