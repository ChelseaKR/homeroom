"""``homeroom dataset``: the artifacts as a citable release, where no blank means anything.

The pages are for families. This is for the readers who will check them -- reporters,
districts, researchers -- and the whole point is that the honesty rules travel with the
data instead of stopping at the HTML.

CSV is where those rules are usually lost. A spreadsheet column of enrolment counts with
a few blank cells in it says nothing about *why* they are blank, and every consumer
supplies the missing reason themselves: a blank becomes a zero in the next sum. So every
measure in ``schools.csv`` is **two** columns, a state and a value:

    grades.GR_03__state    grades.GR_03__value
    reported               20
    zero                   0
    suppressed
    not_reported

The state column is never empty and is always one of those four words. The value column
is filled **exactly when** the state is ``reported`` or ``zero``, and is empty otherwise
-- and an empty cell there cannot be misread, because the word beside it says which of
the two absences it is. ``tests/test_export.py`` asserts that biconditional over every
cell of every row rather than asserting "no blanks", which a file of blanks with a
sentinel in them would also satisfy.

The four words are the four cells ``render.py`` puts on a page, not the three statuses
:class:`~homeroom.measures.Measure` carries, for the reason :mod:`homeroom.explain`
already gives: a published zero is labelled in words as a genuine zero, and a dataset
that collapsed ``zero`` into ``reported`` would be making a different claim from the page
it describes. They are derived from :func:`homeroom.explain.rendered_state` through one
table, so the CSV cannot drift from the markup.

What a release contains
-----------------------

``schools.csv``            one row per school, sorted by CDS code
``schools.schema.json``    a Frictionless Table Schema, generated in the same pass as
                           the header, so a column cannot exist without a declaration
``schools/<cds>.json``     one record per school -- exactly what ``homeroom explain``
                           prints, from the same function, so there is one record shape
``coverage.json``          copied verbatim from the artifacts
``manifest.json``          every file above with its byte count and SHA-256, plus the
                           acquired file names, academic years and access dates

and the whole directory as ``homeroom-dataset-<date>.tar.gz``, byte-identical on a
re-run: members sorted, every mtime, uid and gid zeroed, and gzip's own timestamp
zeroed too. A citable dataset whose digest moves is not citable.

What it refuses
---------------

*A fixture build*, unless ``--allow-fixture`` says so in as many words. Shipping the
fixture as a dataset release is the page-publishing-a-withheld-cell-as-a-number defect
at a much larger blast radius, and the flag exists only so the tests can exercise the
writer.

*A tarball with fewer schools than the build made.* ``coverage.json`` records
``profiles``, the number of active schools the pipeline assembled; a release whose row
count is not exactly that is a truncated dataset presenting itself as a complete one.

*Artifacts that do not say whether they are fixtures*, a school with no CDS code, a
duplicated CDS code, and schools that disagree about which measures they carry. The last
one is the subtle one: filling a missing column with a blank would publish "this school
has no such measure" when the truth is that the file this row came from is shaped
differently from its neighbours'.

*A real build with no access date.* The release is named by the date the sources were
acquired, which is the dataset's identity -- never by the build clock, which would give
two names to one dataset. A fixture has no access date at all, so an allowed fixture
export is named ``homeroom-dataset-fixture``: a false vintage on a file is worse than
no vintage.

Usage::

    python -m homeroom.export --artifacts data/out --out dist/dataset

The raw CDE files live only on the machine that acquired them (``data/raw/`` is in
``.gitignore`` and never reaches CI), so a real dataset is built here and uploaded, not
built by a workflow.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any

from homeroom.explain import ExplainError, explain, load_artifacts, rendered_state

__all__ = [
    "DATASET_STATES",
    "IDENTITY_COLUMNS",
    "STATE_OF_RENDERED",
    "ExportError",
    "build_table",
    "dataset_name",
    "main",
    "measure_paths",
    "table_schema",
    "write_dataset",
]


class ExportError(ValueError):
    """The artifacts cannot support the dataset that was asked for."""


#: The dataset's four states, in the order a reader meets them.
DATASET_STATES: tuple[str, ...] = ("reported", "zero", "suppressed", "not_reported")

#: The page's four rendered cells, mapped onto the dataset's four words. One table, so
#: the CSV states and the markup states cannot drift apart; ``tests/test_export.py``
#: asserts this covers every value :func:`~homeroom.explain.rendered_state` can return.
STATE_OF_RENDERED: dict[str, str] = {
    "number": "reported",
    "zero": "zero",
    "withheld": "suppressed",
    "nothing": "not_reported",
}

#: The directory fields every school entry carries, in column order. Read from the
#: artifact rather than re-derived, and required: a row that cannot name its school is
#: not a row.
IDENTITY_COLUMNS: tuple[str, ...] = (
    "cds_code",
    "name",
    "district",
    "county",
    "city",
    "charter",
    "virtual_code",
    "grades_served",
    "is_fixture",
)

#: The identity columns that come from the school entry. ``is_fixture`` is the one that
#: does not: it is a fact about the build, carried on every row so that a CSV opened
#: away from the release directory still says what it is. A fixture row loose in a
#: spreadsheet with nothing marking it is the whole failure this file guards against.
SCHOOL_IDENTITY_COLUMNS: tuple[str, ...] = tuple(
    column for column in IDENTITY_COLUMNS if column != "is_fixture"
)

#: What each identity column holds, for the Table Schema. A column with no description
#: is a column a citing reader has to guess at, so :func:`table_schema` refuses one.
IDENTITY_DESCRIPTIONS: dict[str, str] = {
    "cds_code": "The 14-digit California County-District-School code, CDE's key for a school.",
    "name": "The school's name as CDE's public schools directory publishes it.",
    "district": "The district the directory records for this school.",
    "county": "The county the directory records for this school.",
    "city": "The city the directory records for this school.",
    "charter": "Whether the directory records this school as a charter school.",
    "virtual_code": "CDE's virtual-instruction code for the school, as published.",
    "grades_served": "The grade span the directory records for this school.",
    "is_fixture": (
        "Whether this row came from a fixture build rather than from files acquired "
        "from CDE. True means the figures are samples and describe no real school."
    ),
}

#: Suffixes for the two columns each measure gets. Kept as constants because the schema
#: generator and the row writer must agree on them and are 200 lines apart.
STATE_SUFFIX = "__state"
VALUE_SUFFIX = "__value"


def _schools_of(schools: dict[str, Any]) -> list[dict[str, Any]]:
    """The school entries, refusing the shapes that would silently mis-key a row."""
    entries = schools.get("schools")
    if not isinstance(entries, list):
        raise ExportError("schools.json has no `schools` list")
    if not entries:
        raise ExportError(
            "schools.json holds no schools; an empty dataset release would state that "
            "California published nothing, which is not what an empty artifact means"
        )
    seen: set[str] = set()
    for entry in entries:
        code = entry.get("cds_code")
        if not isinstance(code, str) or code == "":
            raise ExportError(
                "a school entry has no `cds_code`. Rows cannot be identified by "
                "position: two files' nth entries are not the same school."
            )
        if code in seen:
            raise ExportError(
                f"CDS code {code} appears twice. One row per school is the whole "
                "contract of this file, and resolving a duplicate by guessing which "
                "one is real is not available here."
            )
        seen.add(code)
    return sorted(entries, key=lambda entry: str(entry["cds_code"]))


def _cells_of(school: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every measure cell in one school, keyed by its dotted path.

    Discovery, not enumeration, and deliberately the same walk
    :mod:`homeroom.explain` and :mod:`homeroom.diff` use: three walks that disagreed
    about what counts as a cell would let this file omit exactly the figures the pages
    show, while presenting itself as the whole school.
    """
    from homeroom.explain import SOURCE_OF_BLOCK, walk_cells

    found: dict[str, dict[str, Any]] = {}
    for block in sorted(SOURCE_OF_BLOCK):
        if block not in school:
            # The source was never supplied to the build, so `artifacts.py` omitted the
            # block rather than emitting a school-shaped set of zeros. Omit it here for
            # the same reason; `coverage.json` records the file as unsupplied, so the
            # absence is stated in the release rather than implied by empty columns.
            continue
        for path, cell in walk_cells(school[block], (block,)):
            found[".".join(path)] = cell
    return found


def measure_paths(entries: list[dict[str, Any]]) -> list[str]:
    """The measure columns, refusing schools that disagree about which they have.

    Every school in one build comes through one pipeline over one set of files, so they
    all carry the same cells. If they do not, something upstream has changed shape, and
    the tempting repair -- emit a blank for the school that is missing a column -- would
    publish "no such measure for this school" when the truth is that this row was built
    differently from its neighbours'. That is the defect this whole project is written
    against, so it raises instead.
    """
    first = _cells_of(entries[0])
    expected = sorted(first)
    for entry in entries[1:]:
        theirs = sorted(_cells_of(entry))
        if theirs != expected:
            missing = sorted(set(expected) - set(theirs))
            extra = sorted(set(theirs) - set(expected))
            raise ExportError(
                f"school {entry['cds_code']} carries a different set of measures from "
                f"{entries[0]['cds_code']}: missing {missing or 'nothing'}, "
                f"extra {extra or 'nothing'}. A blank column here would say the state "
                "published no such measure for this school, which is a different fact."
            )
    return expected


def _state_of(cell: dict[str, Any]) -> str:
    """This cell's dataset state, by way of the state the page renders."""
    rendered = rendered_state(cell)
    state = STATE_OF_RENDERED.get(rendered)
    if state is None:  # pragma: no cover - unreachable while the table is total
        raise ExportError(
            f"no dataset state is declared for rendered cell {rendered!r}"
        )
    return state


def _value_text(cell: dict[str, Any], state: str) -> str:
    """The value cell: the artifact's own number, or empty where none was published.

    ``json.dumps`` rather than ``str`` or a format string, so the CSV prints exactly the
    number ``schools.json`` holds. A re-formatting step here is a second chance to say
    something different from the artifact about a real school.

    There is deliberately no "reported but no value" guard here. :func:`_state_of` runs
    first on every cell and :func:`~homeroom.explain.rendered_state` already refuses
    that artifact by name, so a second check would be an unreachable refusal -- which
    reads as a guard and can never fire.
    """
    if state not in ("reported", "zero"):
        return ""
    return json.dumps(cell["value"])


def build_table(
    schools: dict[str, Any], *, is_fixture: bool
) -> tuple[list[str], list[list[str]]]:
    """``(header, rows)`` for ``schools.csv``."""
    entries = _schools_of(schools)
    paths = measure_paths(entries)

    header = [*IDENTITY_COLUMNS]
    for path in paths:
        header.append(f"{path}{STATE_SUFFIX}")
        header.append(f"{path}{VALUE_SUFFIX}")

    rows: list[list[str]] = []
    for entry in entries:
        cells = _cells_of(entry)
        row: list[str] = []
        for column in SCHOOL_IDENTITY_COLUMNS:
            if column not in entry:
                raise ExportError(
                    f"school {entry['cds_code']} has no `{column}`. Every row states "
                    "which school it is about; a blank identity column would not."
                )
            row.append(_identity_text(entry[column]))
        row.append(_identity_text(is_fixture))
        for path in paths:
            cell = cells[path]
            state = _state_of(cell)
            row.append(state)
            row.append(_value_text(cell, state))
        rows.append(row)
    return header, rows


def _identity_text(value: object) -> str:
    """An identity field as text. ``None`` is written empty; booleans as words."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def table_schema(header: list[str]) -> dict[str, Any]:
    """A Frictionless Table Schema for ``header``, built from the header itself.

    Generated in the same pass as the columns, so a column cannot exist without a
    declaration and a declaration cannot outlive its column.

    ``missingValues: [""]`` is right here and is not right everywhere: an empty value
    cell genuinely is "no number was published". The state columns are the other kind --
    always written, never empty -- so they are ``required`` and carry an ``enum``, and a
    blank in one is an error rather than a null.
    """
    fields: list[dict[str, Any]] = []
    for column in header:
        if column in IDENTITY_DESCRIPTIONS:
            fields.append(
                {
                    "name": column,
                    "type": (
                        "boolean" if column in ("charter", "is_fixture") else "string"
                    ),
                    "description": IDENTITY_DESCRIPTIONS[column],
                    **(
                        {"constraints": {"required": True}}
                        if column == "cds_code"
                        else {}
                    ),
                }
            )
        elif column.endswith(STATE_SUFFIX):
            measure = column[: -len(STATE_SUFFIX)]
            fields.append(
                {
                    "name": column,
                    "type": "string",
                    "description": (
                        f"What CDE published for {measure}: `reported` a number, `zero` "
                        "a published zero stated as such, `suppressed` withheld under "
                        "CDE's small-cell rule, `not_reported` never published."
                    ),
                    "constraints": {"required": True, "enum": list(DATASET_STATES)},
                }
            )
        elif column.endswith(VALUE_SUFFIX):
            measure = column[: -len(VALUE_SUFFIX)]
            fields.append(
                {
                    "name": column,
                    "type": "number",
                    "description": (
                        f"The number CDE published for {measure}. Empty exactly when "
                        f"`{measure}{STATE_SUFFIX}` is `suppressed` or `not_reported`; "
                        "the state column says which."
                    ),
                }
            )
        else:  # pragma: no cover - unreachable while build_table owns the header
            raise ExportError(f"no schema field is declared for column {column!r}")
    return {
        "$schema": "https://datapackage.org/profiles/2.0/tableschema.json",
        "name": "schools",
        "fields": fields,
        "primaryKey": ["cds_code"],
        "missingValues": [""],
    }


def dataset_name(coverage: dict[str, Any], *, is_fixture: bool) -> str:
    """``homeroom-dataset-<date>``, from the sources' access dates.

    The date is the dataset's identity -- when these files were taken from CDE -- and it
    comes from the artifact. A build clock would give two names to one dataset and would
    make a re-run produce a different tarball, which is the property this release exists
    to have.
    """
    if is_fixture:
        # A fixture has no access date, and a made-up one on a file is a false vintage.
        return "homeroom-dataset-fixture"
    sources = coverage.get("sources")
    if not isinstance(sources, dict):
        raise ExportError("coverage.json has no `sources` object")
    dates = sorted(
        str(source["access_date"])
        for source in sources.values()
        if isinstance(source, dict) and isinstance(source.get("access_date"), str)
    )
    if not dates:
        raise ExportError(
            "no source in coverage.json carries an `access_date`, so this dataset "
            "cannot state when it was taken from CDE. A release named by the build "
            "clock would date the run rather than the data."
        )
    return f"homeroom-dataset-{dates[-1]}"


def _require_school_count(schools: dict[str, Any], coverage: dict[str, Any]) -> int:
    """The row count, checked against what the build says it assembled."""
    entries = _schools_of(schools)
    expected = coverage.get("profiles")
    if not isinstance(expected, int) or isinstance(expected, bool):
        raise ExportError(
            "coverage.json does not state `profiles` as an integer, so this release "
            "cannot check that it holds every school the build made."
        )
    if len(entries) != expected:
        raise ExportError(
            f"the artifacts hold {len(entries)} school(s) but the build assembled "
            f"{expected}. A dataset release short of the schools it was built from is "
            "a truncated file presenting itself as a complete one."
        )
    return expected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 with ``\\n`` endings, whatever platform this runs on."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _tar_member_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip everything about the build machine and the build clock from a member."""
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o755 if info.isdir() else 0o644
    return info


def _write_tarball(directory: Path, tarball: Path, name: str) -> None:
    """``directory`` as a deterministic gzipped tar, members sorted and clocks zeroed."""
    members = sorted(
        (path for path in directory.rglob("*")),
        key=lambda path: str(path.relative_to(directory)),
    )
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        archive.add(directory, arcname=name, recursive=False, filter=_tar_member_filter)
        for path in members:
            archive.add(
                path,
                arcname=f"{name}/{path.relative_to(directory)}",
                recursive=False,
                filter=_tar_member_filter,
            )
    # gzip stores its own timestamp; left alone it makes two runs of one dataset
    # different files. `mtime=0` is what makes the digest citable.
    with (
        tarball.open("wb") as handle,
        gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as packed,
    ):
        packed.write(raw.getvalue())


def write_dataset(
    artifacts: Path, out: Path, *, allow_fixture: bool = False
) -> dict[str, Any]:
    """Write the release under ``out`` and return its manifest."""
    schools, coverage = load_artifacts(artifacts)

    is_fixture = coverage.get("is_fixture")
    if not isinstance(is_fixture, bool):
        raise ExportError(
            "coverage.json does not state `is_fixture` as a boolean, so this release "
            "cannot say whether it holds acquired data or fixtures. Refusing rather "
            "than assuming it is real."
        )
    if is_fixture and not allow_fixture:
        raise ExportError(
            "these artifacts are a fixture build. Publishing them as a dataset release "
            "would present sample rows as California's published figures. Pass "
            "--allow-fixture to export them anyway; the release will be named "
            "homeroom-dataset-fixture and every file in it will say `is_fixture: true`."
        )

    header, rows = build_table(schools, is_fixture=is_fixture)
    count = _require_school_count(schools, coverage)
    name = dataset_name(coverage, is_fixture=is_fixture)

    directory = out / name
    if directory.exists():
        shutil.rmtree(directory)
    (directory / "schools").mkdir(parents=True)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    _write_text(directory / "schools.csv", buffer.getvalue())

    _write_text(
        directory / "schools.schema.json",
        json.dumps(table_schema(header), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
    )

    # Verbatim, byte for byte: the release's own account of what it covers has to be
    # the same object the pages were built against, not a re-serialisation of it.
    shutil.copyfile(artifacts / "coverage.json", directory / "coverage.json")

    for entry in _schools_of(schools):
        cds = str(entry["cds_code"])
        record = explain(schools, coverage, cds)
        _write_text(
            directory / "schools" / f"{cds}.json",
            json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )

    files = sorted(
        (path for path in directory.rglob("*") if path.is_file()),
        key=lambda path: str(path.relative_to(directory)),
    )
    manifest: dict[str, Any] = {
        "dataset": name,
        "is_fixture": is_fixture,
        "schools": count,
        "sources": coverage.get("sources", {}),
        "files": [
            {
                "path": str(path.relative_to(directory)),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
    }
    # The manifest does not list itself: a file cannot carry its own digest, and a
    # self-entry that silently held the digest of an earlier version would be worse
    # than an absent one.
    _write_text(
        directory / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )

    _write_tarball(directory, out / f"{name}.tar.gz", name)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom dataset",
        description=(
            "Write the artifacts as a citable dataset release: one CSV row per school "
            "where every measure is a state and a value, a Table Schema, one JSON "
            "record per school, and a manifest of SHA-256 digests."
        ),
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("data/out"),
        help="directory holding schools.json and coverage.json (default: data/out)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("dist/dataset"),
        help="directory to write the release into (default: dist/dataset)",
    )
    parser.add_argument(
        "--allow-fixture",
        action="store_true",
        help="export a fixture build, naming it so and flagging it in every file",
    )
    args = parser.parse_args(argv)

    try:
        manifest = write_dataset(
            args.artifacts, args.out, allow_fixture=args.allow_fixture
        )
    except (ExportError, ExplainError) as error:
        print(f"dataset: {error}", file=sys.stderr)
        return 2

    print(f"{manifest['dataset']}: {manifest['schools']} school(s)")
    print(f"  {args.out / manifest['dataset']}")
    print(f"  {args.out / (str(manifest['dataset']) + '.tar.gz')}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
