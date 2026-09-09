"""``homeroom explain``: one school's record, cell by cell, in the states the page shows.

A reporter looking at a school page can read what Homeroom says. What they cannot do
is cite it: there are 21,069 pages and no machine-readable statement of what any one
of them claims, where the figure came from, which year it is for, or which cells the
state withheld. This prints that statement for one school, from the artifacts the
pages are rendered from.

Four properties, each one a way this could quietly lie.

**A number is present only where the state published one.** A cell carries a
``value`` key when, and only when, its status is ``reported``. There is no
``"value": 0`` for a withheld cell and no ``"value": null`` either -- a null in a
JSON record is something a consumer coerces to zero on the next line. The key is
absent, so reading it raises rather than answers. This mirrors ``schools.json``,
which is where the discipline already lives.

**The record carries the four states the page shows, not the three the data has.**
``Measure`` has three statuses; ``render.py`` renders *four* cells, because a
published zero is labelled in words as a genuine zero and not left to look like any
other number. A record that collapsed those two would be making a different claim
from the page it is supposed to describe. So each cell carries both ``status`` (the
measure's, as in ``schools.json``) and ``rendered_state`` (the page's, one of
``number``, ``zero``, ``withheld``, ``nothing``).

**Cells are discovered, not enumerated.** The walk below treats any object with a
``status`` key as a cell, wherever it appears. Listing the blocks by hand would mean
a measure added to ``artifacts.py`` and not added here is silently missing from a
record that presents itself as complete -- a subset published as the whole thing,
which is this project's own failure mode. A new block appears in ``explain`` the day
it appears in the artifact.

That paragraph was true of the *cells* and false of the *blocks* until issue #109.
The walk was reached once per entry of ``SOURCE_OF_BLOCK``, five keys typed by hand
and derived from nothing, so discovery began one level below the place a measure is
actually added. A sixth block in ``schools.json`` was dropped from the record, from
the citable dataset release and from ``make diff``, all three exiting 0 -- and the
test written to catch exactly that summed *over the same hand-written list*, so both
sides of its equality shrank together. The blocks are now discovered too, by
:func:`measure_blocks`, and a block nobody registered is refused rather than
skipped: a record that omits a measure while presenting itself as the whole school
is the failure this file exists to prevent, and it must not be reachable by
forgetting to edit a dict.

**A fixture record says so, and an artifact that does not say is refused.** The
``is_fixture`` flag is read from ``coverage.json`` and required to be a real boolean.
An absent flag is not ``False``: it is an artifact that does not state what it is,
and the answer to that is to refuse, not to assume the reassuring one.

Usage::

    python -m homeroom.explain --artifacts data/out --cds 01100170112345

Output is JSON on stdout with sorted keys and no wall clock, so two runs over the
same artifacts are byte-identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "CELL_UNITS",
    "SOURCE_OF_BLOCK",
    "ExplainError",
    "explain",
    "load_artifacts",
    "main",
    "measure_blocks",
    "registered_blocks",
    "rendered_state",
    "walk_cells",
]


class ExplainError(ValueError):
    """The artifacts cannot support the record that was asked for."""


#: Which acquired file each top-level measure block comes from. Keyed on the block
#: name in ``schools.json``; the values are the keys of ``coverage.json``'s
#: ``sources`` object, so the file name, academic year and access date are read from
#: the artifact rather than restated here where they could drift.
SOURCE_OF_BLOCK: dict[str, str] = {
    "total_enrollment": "D2_enrollment",
    "grades": "D2_enrollment",
    "subgroups": "D2_enrollment",
    "chronic_absenteeism": "D3_chronic_absenteeism",
    "teacher_assignments": "D5_teacher_assignments",
}

#: The unit a figure is in, by measure block. ``teacher_assignments`` splits: CDE
#: publishes a count and a percent for every outcome, and they are different units
#: of the same fact, so the leaf name decides.
CELL_UNITS: dict[str, str] = {
    "total_enrollment": "students",
    "grades": "students",
    "subgroups": "students",
    "chronic_absenteeism": "percent",
    "teacher_assignments.count": "teachers",
    "teacher_assignments.percent": "percent",
    "teacher_assignments.total_assignments": "assignments",
}

#: Units the page prints as a ``%`` suffix after the number. ``render.py`` appends
#: it only to a published figure; a withheld cell carries no digit and so no unit.
#: ``tests/test_explain.py`` holds this against the renderer.
PERCENT_UNITS = frozenset({"percent"})


def rendered_state(cell: dict[str, Any]) -> str:
    """The state ``render.py`` puts on the page for this cell.

    ``m-number``, ``m-zero``, ``m-withheld`` and ``m-nothing`` are the four classes
    ``_measure_cell`` emits; this returns the part after ``m-``. The split between
    the first two is on the value being zero, which is the distinction the page
    makes in words and a three-state record would lose.
    """
    status = cell.get("status")
    if status == "reported":
        if "value" not in cell:
            raise ExplainError(
                "a cell is reported but carries no value; the artifact is malformed"
            )
        return "zero" if float(cell["value"]) == 0.0 else "number"
    if status == "suppressed":
        return "withheld"
    if status == "not_reported":
        return "nothing"
    raise ExplainError(f"unknown measure status {status!r}")


def _unit_for(path: tuple[str, ...]) -> str:
    """The unit for a cell at ``path``, most specific match first."""
    block = path[0]
    leaf = f"{block}.{path[-1]}"
    if leaf in CELL_UNITS:
        return CELL_UNITS[leaf]
    if block in CELL_UNITS:
        return CELL_UNITS[block]
    raise ExplainError(
        f"no unit is declared for the measure block {block!r}. A cell whose unit "
        "nobody has stated must not be printed as though its unit were known: add "
        "it to CELL_UNITS and SOURCE_OF_BLOCK."
    )


def walk_cells(
    node: Any, path: tuple[str, ...]
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    """Every cell under ``node``, as ``(path, cell)`` pairs, in key order.

    Public because :mod:`homeroom.diff` walks the same artifacts, and two walks that
    disagreed about what counts as a cell would let a diff miss exactly the figures a
    record reports.

    A cell is any object carrying a ``status``. Recursion stops there rather than
    descending into it, so a future ``status`` field inside a cell cannot be read as
    a nested cell of its own.
    """
    found: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    if isinstance(node, dict):
        if "status" in node:
            return [(path, node)]
        for key in sorted(node):
            found.extend(walk_cells(node[key], (*path, key)))
    return found


def measure_blocks(school: dict[str, Any]) -> tuple[str, ...]:
    """The measure blocks this school entry actually carries, in key order.

    A measure block is a top-level key whose subtree holds at least one cell, so
    this is the same structural test :func:`walk_cells` applies one level down
    rather than a second list to keep in step with it. The identity fields
    (``cds_code``, ``name``, ``grades_served`` and the rest) carry no ``status``
    anywhere beneath them and are not blocks.

    A block present but *empty* is not reported, because there is no cell in it to
    lose. That is the one case this cannot see, and it is the case where seeing it
    would change nothing.
    """
    return tuple(key for key in sorted(school) if walk_cells(school[key], (key,)))


def registered_blocks(school: dict[str, Any]) -> tuple[str, ...]:
    """:func:`measure_blocks`, refusing any block no consumer knows about.

    Issue #109. Every consumer of ``schools.json`` -- the record, the dataset
    release, the manifest, ``measure_paths`` and ``make diff`` -- reads the blocks
    through here, so a measure added to ``artifacts.py`` and not registered in
    ``SOURCE_OF_BLOCK`` and ``CELL_UNITS`` fails loudly in all of them instead of
    disappearing from all of them.

    Refusing is the right direction and it is worth saying why. The alternative --
    carry the block with its source and unit left blank -- publishes a figure whose
    provenance nobody stated into a dataset whose entire argument is that every
    figure carries its file, its year and its access date. There is no honest blank
    for that, so the build stops and names the block.
    """
    blocks = measure_blocks(school)
    unregistered = [block for block in blocks if block not in SOURCE_OF_BLOCK]
    if unregistered:
        raise ExplainError(
            f"schools.json carries the measure block(s) {', '.join(unregistered)}, "
            f"which nothing registers. Add each one to SOURCE_OF_BLOCK (which CDE "
            f"file it came from) and to CELL_UNITS (what its figures are counted "
            f"in). Until then the record, the dataset release and the diff would "
            f"each omit it while presenting themselves as the whole school."
        )
    return blocks


def load_artifacts(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """``schools.json`` and ``coverage.json`` from an artifacts directory.

    Both are required. ``explain`` cannot describe a cell without saying which file
    and which year it came from, and that is only in ``coverage.json``; producing a
    record with the provenance quietly missing would be worse than producing none.
    """
    schools_path = directory / "schools.json"
    coverage_path = directory / "coverage.json"
    for path in (schools_path, coverage_path):
        if not path.is_file():
            raise ExplainError(
                f"{path} does not exist; run `make data` or `make data-offline`"
            )
    schools = json.loads(schools_path.read_text(encoding="utf-8"))
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    return schools, coverage


def explain(
    schools: dict[str, Any], coverage: dict[str, Any], cds: str
) -> dict[str, Any]:
    """The record for one school.

    Raises :class:`ExplainError` when the school is not in the artifacts. That is
    deliberate: an empty record for an unknown CDS is a statement that Homeroom
    published nothing about a school, which is a different fact from the school not
    being in the file at all.
    """
    entries = schools.get("schools")
    if not isinstance(entries, list):
        raise ExplainError("schools.json has no `schools` list")

    matches = [entry for entry in entries if entry.get("cds_code") == cds]
    if not matches:
        raise ExplainError(
            f"no school with CDS code {cds} is in these artifacts. "
            f"They hold {len(entries)} school(s); this is not a school with nothing "
            "published, it is a school the build never saw."
        )
    school = matches[0]

    is_fixture = coverage.get("is_fixture")
    if not isinstance(is_fixture, bool):
        raise ExplainError(
            "coverage.json does not state `is_fixture` as a boolean, so this record "
            "cannot say whether it describes acquired data or fixtures. Refusing "
            "rather than assuming it is real."
        )

    sources = coverage.get("sources")
    if not isinstance(sources, dict):
        raise ExplainError("coverage.json has no `sources` object")

    identity_keys = ("cds_code", "name", "district", "county", "city")
    record: dict[str, Any] = {key: school.get(key) for key in identity_keys}
    record["is_fixture"] = is_fixture

    cells: list[dict[str, Any]] = []
    # Discovered from the entry, not enumerated from `SOURCE_OF_BLOCK` (issue #109).
    # A block the school does not carry is simply not in this tuple: `artifacts.py`
    # omits a block whose source was not supplied to the build rather than emitting
    # a school-shaped set of zeros, and `sources` below records the file as
    # unsupplied, so the absence is stated rather than implied.
    for block in registered_blocks(school):
        source_key = SOURCE_OF_BLOCK[block]
        source = sources.get(source_key, {})
        for path, cell in walk_cells(school[block], (block,)):
            entry: dict[str, Any] = {
                "measure": ".".join(path),
                "status": cell["status"],
                "rendered_state": rendered_state(cell),
                "unit": _unit_for(path),
                "source": source_key,
                "source_file": source.get("file"),
                "academic_year": source.get("academic_year"),
                "access_date": source.get("access_date"),
            }
            # Only where the state published a number. Never a zero for an absence,
            # and never a null a consumer will coerce into one.
            if cell["status"] == "reported":
                entry["value"] = cell["value"]
            cells.append(entry)

    record["cells"] = cells
    record["sources"] = {
        key: sources[key]
        for key in sorted(sources)
        if key in set(SOURCE_OF_BLOCK.values())
    }
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom explain",
        description=(
            "Print one school's record cell by cell: each figure's state, its unit, "
            "and the CDE file and year it came from. A withheld or unreported cell "
            "carries no number."
        ),
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("data/out"),
        help="directory holding schools.json and coverage.json (default: data/out)",
    )
    parser.add_argument(
        "--cds", required=True, help="the 14-digit CDS code of one school"
    )
    args = parser.parse_args(argv)

    try:
        schools, coverage = load_artifacts(args.artifacts)
        record = explain(schools, coverage, args.cds)
    except ExplainError as error:
        print(f"explain: {error}", file=sys.stderr)
        return 2

    # Sorted keys and a trailing newline: two runs over one artifact are byte-equal.
    print(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
