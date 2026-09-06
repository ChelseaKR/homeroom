"""Read an .xlsx workbook with the standard library: bytes in, rows of cells out.

This is a *format* reader and nothing else. It exists because of one line in the
M5 source survey (docs/ROADMAP.md, 2026-09-05): D6, ESSA Per-Pupil Expenditure,
publishes XLSX only, with no TXT or CSV, so every other source's ``csv`` reader
has nothing to point at. Reading that format needs ``zipfile`` plus
``xml.etree`` over the shared string table, which stays inside ADR 0001's
stdlib-only rule -- no new dependency -- but is new surface, and the survey said
it was worth writing deliberately rather than as a side effect of a parser.

**What this module does not do**, deliberately and permanently:

* It is not a D6 parser. It does not know what ``DNR`` means, which columns hold
  per-pupil dollars, that a workbook might have a header on row 7, or that CDS
  codes exist. Sentinels, joins, and :class:`homeroom.measures.Measure` semantics
  belong to a parser somebody writes when D6 is acquired, and they must not leak
  back into this file.
* It publishes nothing. No artifact, no page, no number. D6 is not acquired: it
  is not in ``data/raw/``, it has no access date, and nothing here fetches it.
* It converts nothing. A numeric cell comes back as the digits the workbook
  holds, as text, because deciding what a number *is* -- reported, suppressed,
  not reported -- is :func:`homeroom.measures.parse_cell`'s job and is a
  decision about a data source, not about a file format. For the same reason a
  date comes back as the serial number Excel stored (``45444``), unconverted:
  converting it needs the styles part, an epoch that differs between workbooks,
  and a decision this module has no standing to make.

**The hazard this format actually has** is that it omits what is empty. A row
with values only in the first and eleventh columns writes two ``<c>`` elements,
not eleven, and a sheet whose first data row is row 7 writes no rows 1-6. Column
position therefore comes from each cell's own ``r`` attribute (``C7`` is column
3 of row 7) and never from counting the cells present. Getting that wrong does
not raise: it shifts every value left into the wrong column, and the result is a
plausible table of numbers filed under the wrong headings, which is the single
worst failure this project could ship. So the reader refuses to count. A ``<row>``
or ``<c>`` with no ``r`` attribute is an error rather than an assumption, and
:meth:`Row.values` places cells by index and raises on one that falls outside the
width the caller says it verified.

**Refusals over guesses**, the same rule :class:`~homeroom.directory.DirectoryDriftError`
and :func:`homeroom.measures.parse_cell` already carry. A missing sheet, a shared
string index that does not resolve, a cell reference that does not parse, a cell
type this reader has not been verified against, or XML carrying a document type
declaration all raise a named error. Nothing here returns ``None`` or ``""`` to
paper over a file it did not understand.

**Bounds**, because a zip is attacker-shaped input even when a state agency
published it. The archive's declared uncompressed size and member count are
checked before anything is read, and then every part is streamed under a hard
byte cap that does not trust what the zip header declared, in the shape
``tools/verify_live_site.py`` already uses for HTTP bodies (read past the limit,
refuse). Rows and columns are bounded by the format's own limits, 1,048,576 and
16,384. Parts are parsed incrementally rather than read whole into a tree, and
a part carrying a DTD is refused: ``xml.etree`` expands internal general
entities (measured 2026-09-05 on this interpreter -- a four-entity billion-laughs
prolog expanded rather than raising), which is the one XML expansion vector
reachable from a file like this.

Determinism falls out of the above: the same bytes yield the same rows, in the
order the sheet writes them.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# `xml.etree` is the only XML parser the standard library offers, and ADR 0001
# forbids adding `defusedxml` (or anything else) to read one state file. The
# exposure the audit rules against this import exist for is entity expansion,
# and it is closed below rather than accepted: `_BoundedPart` refuses any part
# carrying a DTD, so no entity is ever defined for the parser to expand, and
# external entities ElementTree does not resolve at all. Both parse sites carry
# the same reasoning at the line the rule fires on.
# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree import ElementTree as ET

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
"""The transitional SpreadsheetML namespace, which is what Excel and LibreOffice
write and what CDE's published workbook carries. A workbook in the *strict*
OOXML namespace is refused by name rather than read on the assumption that the
two are interchangeable."""

DOCUMENT_RELS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
SHARED_STRINGS_PART = "xl/sharedStrings.xml"

_WORKBOOK_TAG = f"{{{SPREADSHEET_NS}}}workbook"
_SHEET_TAG = f"{{{SPREADSHEET_NS}}}sheet"
_SHEET_DATA_TAG = f"{{{SPREADSHEET_NS}}}sheetData"
_ROW_TAG = f"{{{SPREADSHEET_NS}}}row"
_CELL_TAG = f"{{{SPREADSHEET_NS}}}c"
_VALUE_TAG = f"{{{SPREADSHEET_NS}}}v"
_INLINE_TAG = f"{{{SPREADSHEET_NS}}}is"
_RUN_TAG = f"{{{SPREADSHEET_NS}}}r"
_TEXT_TAG = f"{{{SPREADSHEET_NS}}}t"
_RELATIONSHIP_TAG = f"{{{PACKAGE_RELS_NS}}}Relationship"
_RELATIONSHIP_ID_ATTRIBUTE = f"{{{DOCUMENT_RELS_NS}}}id"

MAXIMUM_ROW = 1_048_576
MAXIMUM_COLUMN = 16_384
"""The format's own limits, so they are the reader's. A reference past either is
not a cell any spreadsheet wrote."""

CELL_REFERENCE = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})", re.ASCII)
"""``C7``: uppercase column letters then a 1-based row. Anchored with
:meth:`re.Pattern.fullmatch`, so ``$C$7``, ``c7``, ``C7:D9`` and ``C0`` are drift
rather than references to reinterpret."""

ROW_NUMBER = re.compile(r"[1-9][0-9]{0,6}", re.ASCII)
"""A ``<row r="7">`` attribute: 1-based, no sign, no padding."""

SHARED_STRING_INDEX = re.compile(r"[0-9]{1,9}", re.ASCII)
""":data:`re.ASCII` for the reason :data:`homeroom.measures.PUBLISHED_NUMBER`
gives: ``str.isdigit`` is true of Arabic-Indic and fullwidth digits, so a
mojibaked index would otherwise select a shared string nobody pointed at."""

READ_CHUNK_BYTES = 64 * 1024

CELL_TYPES = frozenset({"n", "s", "str", "inlineStr"})
"""The four cell types this reader was verified against: numeric (the default
when ``t`` is absent), an index into the shared string table, a formula's cached
string result, and a string stored in the cell itself. ``b`` (boolean), ``e``
(error, ``#DIV/0!``) and ``d`` (ISO date) are real parts of the format and are
refused rather than rendered, because each would need a decision about what it
*means* in a data file, and a spreadsheet of published figures containing one is
a surprise worth stopping for."""


class XlsxError(ValueError):
    """This workbook is not one the reader will read. Never a partial answer."""


class MalformedWorkbookError(XlsxError):
    """The container, its XML, or a reference in it is not what the format says."""


class SheetNotFoundError(XlsxError):
    """The workbook has no sheet under the name the caller asked for."""


class WorkbookTooLargeError(XlsxError):
    """Reading this workbook would cost more than the caller allowed."""


@dataclass(frozen=True)
class Limits:
    """What the reader will spend on one workbook before refusing.

    The defaults are far above CDE's own file -- the 2024-25 ESSA workbook is
    1,035,042 bytes over two sheets (PROVENANCE.md D6) -- and far below what a
    zip bomb needs. They are a parameter rather than a constant so a caller with
    a genuinely larger file raises them deliberately, in code somebody reviews,
    and so the tests can exercise a refusal without building a bomb.
    """

    maximum_archive_bytes: int = 256 * 1024 * 1024
    maximum_member_bytes: int = 64 * 1024 * 1024
    maximum_members: int = 4096


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Cell:
    """One cell the sheet actually wrote.

    ``value`` is the text the workbook holds, verbatim and unconverted: the
    digits of a number, the resolved shared string, the cached result of a
    formula. It is ``None`` when the cell exists but carries no value at all,
    which the format writes for a cell that has only formatting.
    """

    reference: str
    row: int
    column: int
    value: str | None


@dataclass(frozen=True)
class Row:
    """One row the sheet actually wrote, and only the cells it actually wrote.

    ``number`` is the row's own number from the file, not a count of the rows
    yielded so far: a sheet whose data starts on row 7 yields 7 first, and a
    sheet that skips row 8 yields 7 then 9. Callers that care about position must
    use :attr:`Cell.column`, :meth:`value` or :meth:`values`, never the index of
    a cell within :attr:`cells`.
    """

    number: int
    cells: tuple[Cell, ...]

    def value(self, column: int) -> str | None:
        """The text at a 1-based column, or ``None`` if this row publishes none.

        ``None`` covers both a cell the sheet omitted and a cell it wrote with no
        value, because XLSX means the same thing by them. It is a fact about the
        file, not a failure: a reader that cannot tell "no cell" from "no number"
        would be guessing, and every failure this module *can* detect raises.
        """
        for cell in self.cells:
            if cell.column == column:
                return cell.value
        return None

    def values(self, width: int) -> tuple[str | None, ...]:
        """This row as ``width`` positional values, gaps included.

        This is the shape a parser wants once it has read a header row, and it is
        where the skipped-cell hazard is closed: values land at the column their
        own reference names, so a row that wrote columns 1 and 11 comes back with
        nine ``None`` between them rather than two values side by side.

        A cell beyond ``width`` raises. Dropping it would be the silent
        column-shift this module exists to prevent, one step later.
        """
        if not 1 <= width <= MAXIMUM_COLUMN:
            raise ValueError(f"width {width} is not between 1 and {MAXIMUM_COLUMN}")
        row: list[str | None] = [None] * width
        for cell in self.cells:
            if cell.column > width:
                raise MalformedWorkbookError(
                    f"row {self.number} carries {cell.reference}, past the {width} "
                    "columns this caller verified; the sheet has a column the "
                    "layout does not, and dropping it silently is the failure "
                    "this reader exists to prevent"
                )
            row[cell.column - 1] = cell.value
        return tuple(row)


class _BoundedPart:
    """One zip member, read in chunks under a hard cap and refusing a DTD.

    The cap is enforced on bytes actually produced, not on the size the zip
    header declares, because the header is written by whoever made the file. The
    DTD check is the entity-expansion defence named in the module docstring; the
    marker can straddle a chunk boundary, so the tail of each chunk is carried
    into the next.
    """

    _MARKERS = (b"<!DOCTYPE", b"<!ENTITY")
    _CARRY = max(len(marker) for marker in _MARKERS) - 1

    def __init__(self, name: str, stream: IO[bytes], limit: int) -> None:
        self._name = name
        self._stream = stream
        self._limit = limit
        self._read = 0
        self._carry = b""

    def read(self, size: int = -1) -> bytes:
        wanted = READ_CHUNK_BYTES if size < 0 else size
        chunk = self._stream.read(min(wanted, self._limit - self._read + 1))
        self._read += len(chunk)
        if self._read > self._limit:
            raise WorkbookTooLargeError(
                f"{self._name} is larger than the {self._limit} byte limit this "
                "reader will spend on one part, whatever the archive declared"
            )
        self._refuse_a_document_type(chunk)
        return chunk

    def _refuse_a_document_type(self, chunk: bytes) -> None:
        window = self._carry + chunk
        for marker in self._MARKERS:
            if marker in window:
                raise MalformedWorkbookError(
                    f"{self._name} carries {marker.decode()}; a spreadsheet part "
                    "has no use for a document type declaration, and an internal "
                    "entity is how an XML parser is made to expand a small file "
                    "into a large one"
                )
        self._carry = window[-self._CARRY :]

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> _BoundedPart:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@contextmanager
def _open_workbook(source: Path | bytes, limits: Limits) -> Iterator[zipfile.ZipFile]:
    """The archive, with its declared cost checked before anything is read."""
    handle: IO[bytes] = (
        io.BytesIO(source) if isinstance(source, bytes) else source.open("rb")
    )
    try:
        archive = zipfile.ZipFile(handle)
    except zipfile.BadZipFile as exc:
        handle.close()
        raise MalformedWorkbookError(
            f"this is not a zip container, so it is not an .xlsx workbook: {exc}"
        ) from exc
    try:
        members = archive.infolist()
        if len(members) > limits.maximum_members:
            raise WorkbookTooLargeError(
                f"the archive holds {len(members)} members, past the "
                f"{limits.maximum_members} this reader will open"
            )
        declared = sum(member.file_size for member in members)
        if declared > limits.maximum_archive_bytes:
            raise WorkbookTooLargeError(
                f"the archive declares {declared} bytes uncompressed, past the "
                f"{limits.maximum_archive_bytes} byte limit; a file that expands "
                "that far is refused rather than read"
            )
        yield archive
    finally:
        archive.close()
        handle.close()


def _open_part(archive: zipfile.ZipFile, name: str, limits: Limits) -> _BoundedPart:
    try:
        stream = archive.open(name)
    except KeyError as exc:
        raise MalformedWorkbookError(
            f"the workbook has no {name} part, so there is nothing there to read; "
            "the file is either damaged or not the format it claims to be"
        ) from exc
    return _BoundedPart(name, stream, limits.maximum_member_bytes)


def _parse_part(archive: zipfile.ZipFile, name: str, limits: Limits) -> ET.Element:
    """A small part, parsed whole. Only parts bounded by the format's own shape
    are read this way; the sheet itself is streamed."""
    with _open_part(archive, name, limits) as part:
        try:
            # The audit rule here is about entity expansion in untrusted XML.
            # `part` refuses a DTD before a byte of it reaches the parser, which
            # is the condition that rule exists to require; `defusedxml` is a
            # dependency ADR 0001 does not allow for it.
            # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse
            return ET.parse(part).getroot()  # noqa: S314
        except ET.ParseError as exc:
            raise MalformedWorkbookError(
                f"{name} is not well-formed XML: {exc}"
            ) from exc


def _part_path(target: str) -> str:
    """A relationship target as a member name, refusing one that leaves the part.

    Nothing here writes to disk, so this is not a path-traversal fix; it is the
    same refusal as everywhere else. A target pointing outside ``xl/`` is not a
    worksheet, and following it would mean reading whatever it did point at.
    """
    path = target[1:] if target.startswith("/") else f"xl/{target}"
    if ".." in path.split("/") or "\\" in path:
        raise MalformedWorkbookError(
            f"relationship target {target!r} points outside the workbook part; "
            "refusing to follow it"
        )
    return path


def _relationship_targets(archive: zipfile.ZipFile, limits: Limits) -> dict[str, str]:
    root = _parse_part(archive, WORKBOOK_RELS_PART, limits)
    targets: dict[str, str] = {}
    for element in root.iter(_RELATIONSHIP_TAG):
        identifier, target = element.get("Id"), element.get("Target")
        if not identifier or not target:
            raise MalformedWorkbookError(
                f"{WORKBOOK_RELS_PART} carries a relationship with no Id or no "
                "Target, so no sheet it names can be located"
            )
        targets[identifier] = _part_path(target)
    return targets


def _sheets(archive: zipfile.ZipFile, limits: Limits) -> tuple[tuple[str, str], ...]:
    """Every sheet as (name, member path), in the order the workbook lists them."""
    root = _parse_part(archive, WORKBOOK_PART, limits)
    if root.tag != _WORKBOOK_TAG:
        raise MalformedWorkbookError(
            f"{WORKBOOK_PART} has root element {root.tag!r}, not {_WORKBOOK_TAG!r}; "
            "this reader was verified against transitional SpreadsheetML only"
        )
    targets = _relationship_targets(archive, limits)
    sheets: list[tuple[str, str]] = []
    for element in root.iter(_SHEET_TAG):
        name = element.get("name")
        identifier = element.get(_RELATIONSHIP_ID_ATTRIBUTE)
        if not name or not identifier:
            raise MalformedWorkbookError(
                f"{WORKBOOK_PART} lists a sheet with no name or no relationship id"
            )
        target = targets.get(identifier)
        if target is None:
            raise MalformedWorkbookError(
                f"sheet {name!r} points at relationship {identifier!r}, which "
                f"{WORKBOOK_RELS_PART} does not define"
            )
        sheets.append((name, target))
    if not sheets:
        raise MalformedWorkbookError(f"{WORKBOOK_PART} lists no sheets at all")
    return tuple(sheets)


def _runs_text(element: ET.Element) -> str:
    """The text of an ``<si>`` or ``<is>``, whose runs are a formatting artifact.

    A word bolded inside a header splits that string into several ``<r>`` runs
    with a ``<t>`` each; they are one value and are joined. ``<rPh>`` (phonetic
    guides) is text *about* the string rather than the string, so walking every
    descendant ``<t>`` would append it; only ``<t>`` and ``<r><t>`` are read.
    """
    parts: list[str] = []
    for child in element:
        if child.tag == _TEXT_TAG:
            parts.append(child.text or "")
        elif child.tag == _RUN_TAG:
            parts.extend(run.text or "" for run in child.findall(_TEXT_TAG))
    return "".join(parts)


def _shared_strings(archive: zipfile.ZipFile, limits: Limits) -> tuple[str, ...] | None:
    """The shared string table, or ``None`` when the workbook carries no part.

    XLSX stores most text once here and writes an index in the cell, so this
    table is what makes a ``t="s"`` cell readable at all. ``None`` is not a
    silent empty table: a cell that indexes into a table that does not exist
    raises rather than reading as blank.
    """
    if SHARED_STRINGS_PART not in archive.namelist():
        return None
    root = _parse_part(archive, SHARED_STRINGS_PART, limits)
    return tuple(_runs_text(item) for item in root.findall(f"{{{SPREADSHEET_NS}}}si"))


def _reference(reference: str, where: str) -> tuple[int, int]:
    """A cell reference as (column, row), both 1-based. ``C7`` is (3, 7)."""
    match = CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise MalformedWorkbookError(
            f"{where}: cell reference {reference!r} does not parse; the column a "
            "value belongs in is read from the reference and never counted, so "
            "there is nothing to fall back on"
        )
    letters, digits = match.groups()
    column = 0
    for letter in letters:
        column = column * 26 + (ord(letter) - ord("A") + 1)
    row = int(digits)
    if column > MAXIMUM_COLUMN or row > MAXIMUM_ROW:
        raise MalformedWorkbookError(
            f"{where}: cell reference {reference!r} is column {column} row {row}, "
            f"past the {MAXIMUM_COLUMN} by {MAXIMUM_ROW} the format allows"
        )
    return column, row


def _shared_string(
    text: str, strings: tuple[str, ...] | None, where: str, reference: str
) -> str:
    if strings is None:
        raise MalformedWorkbookError(
            f"{where}: cell {reference} indexes the shared string table, and this "
            f"workbook has no {SHARED_STRINGS_PART} part to index"
        )
    if not SHARED_STRING_INDEX.fullmatch(text):
        raise MalformedWorkbookError(
            f"{where}: cell {reference} holds shared string index {text!r}, which "
            "is not an index"
        )
    index = int(text)
    if index >= len(strings):
        raise MalformedWorkbookError(
            f"{where}: cell {reference} indexes shared string {index}, past the "
            f"{len(strings)} the table holds"
        )
    return strings[index]


def _cell_value(
    element: ET.Element,
    kind: str,
    strings: tuple[str, ...] | None,
    where: str,
    reference: str,
) -> str | None:
    if kind not in CELL_TYPES:
        raise MalformedWorkbookError(
            f"{where}: cell {reference} has type {kind!r}, which this reader has "
            f"not been verified against; it reads {sorted(CELL_TYPES)} and refuses "
            "the rest rather than deciding on its own what one means"
        )
    if kind == "inlineStr":
        inline = element.find(_INLINE_TAG)
        return None if inline is None else _runs_text(inline)
    value = element.find(_VALUE_TAG)
    if value is None:
        return None
    text = value.text or ""
    if kind != "s":
        return text
    return _shared_string(text, strings, where, reference)


def _cell(
    element: ET.Element,
    number: int,
    strings: tuple[str, ...] | None,
    where: str,
) -> Cell:
    reference = element.get("r")
    if reference is None:
        raise MalformedWorkbookError(
            f"{where}: row {number} holds a cell with no r attribute, so its column "
            "would have to be counted; this reader does not count columns"
        )
    column, row = _reference(reference, where)
    if row != number:
        raise MalformedWorkbookError(
            f"{where}: cell {reference} appears inside row {number}, and a cell "
            "that names a different row than the one it sits in makes both "
            "unreliable"
        )
    return Cell(
        reference=reference,
        row=row,
        column=column,
        value=_cell_value(element, element.get("t") or "n", strings, where, reference),
    )


def _row(element: ET.Element, strings: tuple[str, ...] | None, where: str) -> Row:
    reference = element.get("r")
    if reference is None:
        raise MalformedWorkbookError(
            f"{where}: a row carries no r attribute, so which row it is would have "
            "to be counted; rows are skipped in this format, which is exactly why "
            "counting them is wrong"
        )
    if not ROW_NUMBER.fullmatch(reference) or int(reference) > MAXIMUM_ROW:
        raise MalformedWorkbookError(
            f"{where}: row number {reference!r} is not a row number between 1 and "
            f"{MAXIMUM_ROW}"
        )
    number = int(reference)
    cells: list[Cell] = []
    previous = 0
    for child in element.findall(_CELL_TAG):
        cell = _cell(child, number, strings, where)
        if cell.column <= previous:
            raise MalformedWorkbookError(
                f"{where}: row {number} lists {cell.reference} after column "
                f"{previous}; cells out of order, or a column written twice, mean "
                "one of the two values would quietly win"
            )
        previous = cell.column
        cells.append(cell)
    return Row(number=number, cells=tuple(cells))


def _stream_rows(
    archive: zipfile.ZipFile,
    part: str,
    strings: tuple[str, ...] | None,
    limits: Limits,
) -> Iterator[Row]:
    """Rows in document order, parsed incrementally and released as they go."""
    with _open_part(archive, part, limits) as stream:
        container: ET.Element | None = None
        previous = 0
        try:
            # Same rule, same answer as `_parse_part`: `stream` refuses a DTD
            # before the parser sees one, so there is no entity to expand.
            for event, element in ET.iterparse(  # noqa: S314
                stream, events=("start", "end")
            ):
                if event == "start":
                    if element.tag == _SHEET_DATA_TAG:
                        container = element
                    continue
                if element.tag != _ROW_TAG:
                    continue
                if container is None:
                    raise MalformedWorkbookError(
                        f"{part}: a row appears outside <sheetData>; the sheet's "
                        "rows live there, and one somewhere else is a document "
                        "this reader has not been verified against"
                    )
                row = _row(element, strings, part)
                if row.number <= previous:
                    raise MalformedWorkbookError(
                        f"{part}: row {row.number} follows row {previous}; rows out "
                        "of order would make document order and row number two "
                        "different answers to the same question"
                    )
                previous = row.number
                # The row is now an immutable `Row`; drop the parsed elements so a
                # long sheet costs what one row costs, not what the sheet does.
                container.clear()
                yield row
        except ET.ParseError as exc:
            raise MalformedWorkbookError(
                f"{part} is not well-formed XML: {exc}"
            ) from exc


def sheet_names(
    source: Path | bytes, *, limits: Limits = DEFAULT_LIMITS
) -> tuple[str, ...]:
    """Every sheet name in the workbook, in the order the workbook lists them.

    The names are what :func:`read_rows` takes, and reading them first is how a
    caller notices that a sheet was renamed upstream rather than discovering it
    as an empty result.
    """
    with _open_workbook(source, limits) as archive:
        return tuple(name for name, _ in _sheets(archive, limits))


def read_rows(
    source: Path | bytes, sheet: str, *, limits: Limits = DEFAULT_LIMITS
) -> Iterator[Row]:
    """Yield the rows one sheet actually wrote, in document order.

    ``source`` is the workbook: a path to it, or its bytes. ``sheet`` is the name
    as the workbook spells it; a name it does not have raises
    :class:`SheetNotFoundError` naming the ones it does.

    Rows the sheet omitted are not yielded and are not invented, and cells a row
    omitted are not in :attr:`Row.cells`. Every value is text, exactly as the
    workbook holds it. Nothing here classifies a value, and nothing here knows
    what the sheet is about.
    """
    with _open_workbook(source, limits) as archive:
        sheets = _sheets(archive, limits)
        part = next((path for name, path in sheets if name == sheet), None)
        if part is None:
            raise SheetNotFoundError(
                f"the workbook has no sheet named {sheet!r}; it carries "
                f"{[name for name, _ in sheets]}"
            )
        yield from _stream_rows(archive, part, _shared_strings(archive, limits), limits)
