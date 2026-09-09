"""``homeroom diff``: what changed between two publishes, by school and by cell state.

``make publish`` rewrites 23,310 files, and reviewing that as a git diff of markup is
not review. The event this project must never ship unnoticed is a **state flip on a
real school's page** -- a figure that was published and is now withheld, or the
reverse -- and a diff of HTML buries it among reflowed tags. This compares the
``data/out`` artifacts instead, where the states are the data.

Four things it refuses to do, each one a way a diff of this kind normally misleads.

**"Value changed to nothing" is not a change of value.** A cell going from a number
to withheld, or to not-reported, is its own kind of event with its own count. Every
transition between the four rendered states -- number, zero, withheld, nothing -- is
named (:data:`TRANSITIONS`), and a numeric move is only ever reported between two
cells that both actually carry a number.

**A source nobody supplied is one event, not thousands.** If a build ran without
``--assignments``, every teacher-assignment cell is absent from that side. Reported
cell by cell that is 21,069 schools' worth of "withheld -> nothing", which reads as
CDE having withdrawn a whole dataset. It is not: nobody opened the file. Those blocks
produce a single ``source_supplied`` or ``source_unsupplied`` event and the per-cell
noise is suppressed, with the count of suppressed cells stated so the suppression is
visible rather than silent.

**A school that appears or disappears is stated, never inferred.** A CDS on one side
and not the other yields exactly one ``school_added`` or ``school_removed`` event.
Nothing is diffed cell-wise against a school that is not there, because every cell
would read as a change and none of them would be one.

**A fixture run and an acquired run are not comparable.** ``coverage.json`` says
which each side is, and comparing them is refused rather than diffed: the result
would be a very large and entirely meaningless report, published as a list of changes
to real schools.

Usage::

    python -m homeroom.diff --old data/out.previous --new data/out
    python -m homeroom.diff --old ... --new ... --format markdown

Output is JSON (sorted keys) or Markdown, both deterministic: identical artifacts
produce an empty diff and exit 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from homeroom.explain import (
    SOURCE_OF_BLOCK,
    ExplainError,
    load_artifacts,
    registered_blocks,
    rendered_state,
    walk_cells,
)

__all__ = [
    "TRANSITIONS",
    "DiffError",
    "diff",
    "main",
    "render_markdown",
]


class DiffError(ValueError):
    """The two artifact sets cannot be compared."""


#: Every transition between the four rendered states, named. The names are the point:
#: a report that lumped `withheld -> number` in with `number -> number` as "changed"
#: would hide the only event this tool exists to surface.
TRANSITIONS: dict[tuple[str, str], str] = {
    ("number", "withheld"): "published_to_withheld",
    ("zero", "withheld"): "published_to_withheld",
    ("number", "nothing"): "published_to_nothing",
    ("zero", "nothing"): "published_to_nothing",
    ("withheld", "number"): "withheld_to_published",
    ("withheld", "zero"): "withheld_to_published",
    ("withheld", "nothing"): "withheld_to_nothing",
    ("nothing", "number"): "nothing_to_published",
    ("nothing", "zero"): "nothing_to_published",
    ("nothing", "withheld"): "nothing_to_withheld",
    ("number", "zero"): "number_to_zero",
    ("zero", "number"): "zero_to_number",
    ("number", "number"): "number_changed",
}


def _cells(school: dict[str, Any], block: str) -> dict[str, dict[str, Any]]:
    """Every cell in one block of one school, keyed by dotted path."""
    return {
        ".".join(path): cell for path, cell in walk_cells(school.get(block), (block,))
    }


def _by_cds(artifacts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = artifacts.get("schools")
    if not isinstance(entries, list):
        raise DiffError("schools.json has no `schools` list")
    by_cds: dict[str, dict[str, Any]] = {}
    for entry in entries:
        cds = entry.get("cds_code")
        if not isinstance(cds, str):
            raise DiffError(
                "a school entry has no `cds_code`; refusing to diff by position"
            )
        if cds in by_cds:
            raise DiffError(
                f"CDS code {cds} appears twice; refusing to guess which is meant"
            )
        by_cds[cds] = entry
    return by_cds


def _fixture_flag(coverage: dict[str, Any], side: str) -> bool:
    value = coverage.get("is_fixture")
    if not isinstance(value, bool):
        raise DiffError(
            f"the {side} coverage.json does not state `is_fixture` as a boolean, so this "
            "diff cannot say what it is comparing. Refusing rather than assuming."
        )
    return value


def _school_events(
    old_by_cds: dict[str, dict[str, Any]], new_by_cds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """A CDS on one side only, stated rather than inferred.

    Diffing such a school's cells against a school that is not there would report
    every cell as a change, and none of them would be one.
    """
    events: list[dict[str, Any]] = []
    for cds in sorted(set(old_by_cds) - set(new_by_cds)):
        events.append(
            {
                "event": "school_removed",
                "cds_code": cds,
                "name": old_by_cds[cds].get("name"),
            }
        )
    for cds in sorted(set(new_by_cds) - set(old_by_cds)):
        events.append(
            {
                "event": "school_added",
                "cds_code": cds,
                "name": new_by_cds[cds].get("name"),
            }
        )
    return events


def _blocks_across(
    old_by_cds: dict[str, dict[str, Any]], new_by_cds: dict[str, dict[str, Any]]
) -> tuple[str, ...]:
    """Every measure block either side carries, discovered from the artifacts.

    Issue #109. Reading ``SOURCE_OF_BLOCK`` here meant a block present in both
    builds but absent from that dict produced **zero events**: no
    ``source_supplied``, no per-cell transitions, no count in the summary. A
    figure could flip from published to withheld for every school in California
    and ``make diff`` would print nothing and exit 0.

    :func:`homeroom.explain.registered_blocks` refuses an unregistered block, so
    the failure is now a named error on both sides rather than a silent omission
    from one report.
    """
    blocks: set[str] = set()
    for by_cds in (old_by_cds, new_by_cds):
        for school in by_cds.values():
            blocks.update(registered_blocks(school))
    return tuple(sorted(blocks))


def _source_events(
    old_by_cds: dict[str, dict[str, Any]], new_by_cds: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], set[str]]:
    """A source supplied to one build and not the other: one event, not thousands.

    Returns the events and the blocks whose per-cell events are suppressed. The
    number suppressed rides along in the event, so the suppression is a stated fact
    rather than a silent one.
    """
    events: list[dict[str, Any]] = []
    suppressed: set[str] = set()
    for block in _blocks_across(old_by_cds, new_by_cds):
        in_old = any(block in school for school in old_by_cds.values())
        in_new = any(block in school for school in new_by_cds.values())
        if in_old == in_new:
            continue
        suppressed.add(block)
        side = new_by_cds if in_new else old_by_cds
        events.append(
            {
                "event": "source_supplied" if in_new else "source_unsupplied",
                "measure_block": block,
                "source": SOURCE_OF_BLOCK[block],
                "cell_events_suppressed": sum(
                    len(_cells(s, block)) for s in side.values()
                ),
                "why": (
                    "this build did not open the file, so the cells are absent rather "
                    "than changed; reporting them individually would read as CDE "
                    "withdrawing a dataset"
                ),
            }
        )
    return events, suppressed


def _cell_event(
    cds: str, measure: str, before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any] | None:
    """One cell's event, or ``None`` if nothing about it changed."""
    was, now = rendered_state(before), rendered_state(after)
    if was == now:
        if was not in ("number", "zero"):
            return None
        if float(before["value"]) == float(after["value"]):
            return None
    event: dict[str, Any] = {
        "event": TRANSITIONS[(was, now)],
        "cds_code": cds,
        "measure": measure,
        "from_state": was,
        "to_state": now,
    }
    # A number is carried only from a side that actually published one. `from` and
    # `to` are absent otherwise, for the same reason `explain` omits `value`: a null
    # here becomes a zero one line downstream.
    if was in ("number", "zero"):
        event["from"] = before["value"]
    if now in ("number", "zero"):
        event["to"] = after["value"]
    return event


def _block_events(
    cds: str, old_school: dict[str, Any], new_school: dict[str, Any], block: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    old_cells = _cells(old_school, block)
    new_cells = _cells(new_school, block)
    for measure in sorted(set(old_cells) | set(new_cells)):
        before, after = old_cells.get(measure), new_cells.get(measure)
        if before is None or after is None:
            # One side has a cell the other lacks while the whole block is present on
            # both. That is a shape change inside a school -- a real event, and not a
            # value that changed.
            events.append(
                {
                    "event": "cell_added" if before is None else "cell_removed",
                    "cds_code": cds,
                    "measure": measure,
                }
            )
            continue
        event = _cell_event(cds, measure, before, after)
        if event is not None:
            events.append(event)
    return events


def diff(
    old: tuple[dict[str, Any], dict[str, Any]],
    new: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    """What changed between two artifact sets, as a deterministic record."""
    old_schools, old_coverage = old
    new_schools, new_coverage = new

    old_fixture = _fixture_flag(old_coverage, "old")
    new_fixture = _fixture_flag(new_coverage, "new")
    if old_fixture != new_fixture:
        raise DiffError(
            "one side is a fixture build and the other is not. Comparing them would "
            "produce a very large report about real schools that describes nothing "
            "that happened to them."
        )

    old_by_cds = _by_cds(old_schools)
    new_by_cds = _by_cds(new_schools)

    events = _school_events(old_by_cds, new_by_cds)
    source_events, suppressed = _source_events(old_by_cds, new_by_cds)
    events += source_events

    blocks = _blocks_across(old_by_cds, new_by_cds)
    for cds in sorted(set(old_by_cds) & set(new_by_cds)):
        for block in blocks:
            if block not in suppressed:
                events += _block_events(cds, old_by_cds[cds], new_by_cds[cds], block)

    counts: dict[str, int] = {}
    for event in events:
        counts[event["event"]] = counts.get(event["event"], 0) + 1

    return {
        "is_fixture": new_fixture,
        "schools": {"old": len(old_by_cds), "new": len(new_by_cds)},
        "sources": {
            "old": old_coverage.get("sources"),
            "new": new_coverage.get("sources"),
        },
        "counts": dict(sorted(counts.items())),
        "events": events,
    }


def render_markdown(record: dict[str, Any]) -> str:
    """The same record as prose. Empty means empty, and says so."""
    lines = ["# Publish diff", ""]
    if record["is_fixture"]:
        lines += [
            "**Both sides are fixture builds.** Nothing here is about a real school.",
            "",
        ]
    if not record["events"]:
        lines += [
            "Nothing changed. The two artifact sets describe the same schools in the",
            "same states.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        f"{len(record['events'])} event(s).",
        "",
        "| Event | Count |",
        "| --- | ---: |",
    ]
    for name, count in record["counts"].items():
        lines.append(f"| `{name}` | {count} |")
    lines += [
        "",
        "## Every event",
        "",
        "| Event | School | Measure | From | To |",
        "| --- | --- | --- | --- | --- |",
    ]
    for event in record["events"]:
        # A state with no number prints the state's own word, never a dash and never
        # a blank that could read as zero.
        frm = event.get("from", event.get("from_state", "—"))
        to = event.get("to", event.get("to_state", "—"))
        lines.append(
            f"| `{event['event']}` | {event.get('cds_code', '')} | "
            f"{event.get('measure', event.get('measure_block', ''))} | {frm} | {to} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom diff",
        description=(
            "What changed between two publishes, by school and by cell state. A cell "
            "that went from a number to withheld is its own event, never a value that "
            "changed to nothing."
        ),
    )
    parser.add_argument("--old", type=Path, required=True, help="the previous data/out")
    parser.add_argument("--new", type=Path, required=True, help="the new data/out")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="json", help="output format"
    )
    args = parser.parse_args(argv)

    try:
        record = diff(load_artifacts(args.old), load_artifacts(args.new))
    except (DiffError, ExplainError) as error:
        print(f"diff: {error}", file=sys.stderr)
        return 2

    if args.format == "markdown":
        print(render_markdown(record), end="")
    else:
        print(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
