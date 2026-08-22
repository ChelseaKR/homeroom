"""One school's published records, in the shape the model reads and the verifier checks.

The ask layer's whole claim to honesty is that the model sees nothing but what
the school's page already shows, and that every sentence it writes is checked
against exactly that. This module is that "exactly that": an
:class:`EvidenceRecord` per measure the page renders, carrying the school's own
cell beside the district and statewide cells the page puts next to it, each in
one of the same three states, with the source file, academic year, unit, and
coverage tally the page prints.

Cells are addressable. A record is ``<cds>|<measure>|<year>`` and a cell is that
plus ``|school``, ``|district`` or ``|state``. Those are the only identifiers a
claim may cite for a figure, and a cite that does not resolve to one of this
school's cells is not a citation.

The bundle on disk is one small file per school (``schools/<cds>.json``) plus an
``index.json``, written by :func:`build_bundle` from the same acquired files and
the same assembly, context, and coverage code the page build uses, so a figure
here is a figure the page shows and nothing else. Deterministic: sorted keys,
fixed record order, no wall clock.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from homeroom.ask.catalog import CATALOG, ENROLLMENT, MeasureSpec
from homeroom.context import (
    AbsenteeismAggregate,
    AggregateFigures,
    load_absenteeism_context,
    load_context,
)
from homeroom.measures import Measure, MeasureStatus
from homeroom.profiles import SchoolProfile, assemble_profiles
from homeroom.render import SiteCoverage, site_coverage
from homeroom.site import sources as site_sources

SCOPES: tuple[str, ...] = ("school", "district", "state")


@dataclass(frozen=True)
class Cell:
    status: str
    value: float | None = None

    @property
    def reported(self) -> bool:
        return self.status == MeasureStatus.REPORTED.value

    @classmethod
    def of(cls, measure: Measure) -> Cell:
        if measure.status is MeasureStatus.REPORTED:
            return cls(status=measure.status.value, value=measure.number())
        return cls(status=measure.status.value)


@dataclass(frozen=True)
class SourceInfo:
    key: str
    file_name: str
    url: str
    access_date: str | None
    academic_year: str | None


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    measure: str
    year: str
    source: str
    school: Cell
    district: Cell
    state: Cell
    coverage: dict[str, int]

    @property
    def spec(self) -> MeasureSpec:
        return CATALOG[self.measure]

    def cell(self, scope: str) -> Cell:
        if scope == "school":
            return self.school
        if scope == "district":
            return self.district
        if scope == "state":
            return self.state
        raise KeyError(scope)

    def cell_id(self, scope: str) -> str:
        if scope not in SCOPES:
            raise KeyError(scope)
        return f"{self.id}|{scope}"


@dataclass(frozen=True)
class SchoolEvidence:
    cds: str
    name: str
    district: str
    county: str
    city: str
    charter: bool
    grades_served: str
    is_fixture: bool
    schools_in_build: int
    sources: dict[str, SourceInfo]
    records: dict[str, EvidenceRecord]

    def cell(self, cell_id: str) -> tuple[EvidenceRecord, str, Cell] | None:
        """Resolve a cited cell id, or ``None`` if it is not one of this school's."""
        parts = cell_id.split("|")
        if len(parts) != 4:
            return None
        cds, measure, year, scope = parts
        record = self.records.get(measure)
        if (
            record is None
            or cds != self.cds
            or year != record.year
            or scope not in SCOPES
        ):
            return None
        return record, scope, record.cell(scope)

    def to_json(self) -> dict[str, object]:
        return {
            "cds": self.cds,
            "name": self.name,
            "district": self.district,
            "county": self.county,
            "city": self.city,
            "charter": self.charter,
            "grades_served": self.grades_served,
            "is_fixture": self.is_fixture,
            "schools_in_build": self.schools_in_build,
            "sources": {k: asdict(v) for k, v in sorted(self.sources.items())},
            "records": [asdict(r) for r in self.records.values()],
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> SchoolEvidence:
        sources_raw = data["sources"]
        records_raw = data["records"]
        if not isinstance(sources_raw, dict) or not isinstance(records_raw, list):
            raise ValueError(f"evidence for {data.get('cds')} is not shaped as written")
        records: dict[str, EvidenceRecord] = {}
        for raw in records_raw:
            record = EvidenceRecord(
                id=str(raw["id"]),
                measure=str(raw["measure"]),
                year=str(raw["year"]),
                source=str(raw["source"]),
                school=Cell(**raw["school"]),
                district=Cell(**raw["district"]),
                state=Cell(**raw["state"]),
                coverage={k: int(v) for k, v in raw["coverage"].items()},
            )
            if record.measure not in CATALOG:
                raise ValueError(
                    f"evidence for {data['cds']} names measure {record.measure!r}, "
                    "which the catalog does not carry; the bundle was built by a "
                    "different version of the code"
                )
            records[record.measure] = record
        return cls(
            cds=str(data["cds"]),
            name=str(data["name"]),
            district=str(data["district"]),
            county=str(data["county"]),
            city=str(data["city"]),
            charter=bool(data["charter"]),
            grades_served=str(data["grades_served"]),
            is_fixture=bool(data["is_fixture"]),
            schools_in_build=int(str(data["schools_in_build"])),
            sources={k: SourceInfo(**v) for k, v in sources_raw.items()},
            records=records,
        )


def _records(
    profile: SchoolProfile,
    cover: SiteCoverage,
    district: AggregateFigures,
    state: AggregateFigures,
    absenteeism_district: AbsenteeismAggregate | None,
    absenteeism_state: AbsenteeismAggregate | None,
) -> Iterator[EvidenceRecord]:
    """Every catalog measure for one school, in catalog order, copied not computed."""
    cds = profile.school.cds_code
    for spec in CATALOG.values():
        if spec.family == ENROLLMENT:
            year = profile.academic_year
            if spec.key == "enrollment.total":
                own, dist, st = profile.total_enrollment, district.total, state.total
                counts = cover.total_enrollment
            elif spec.key.startswith("enrollment.grade."):
                own = profile.grades[spec.code]
                dist, st = district.grade(spec.code), state.grade(spec.code)
                counts = cover.grades[spec.code]
            else:
                own = profile.subgroups[spec.code]
                dist, st = district.subgroup(spec.code), state.subgroup(spec.code)
                counts = cover.subgroups[spec.code]
            source = "d2"
        else:
            if (
                not cover.absenteeism_supplied
                or cover.absenteeism_academic_year is None
            ):
                continue
            year = cover.absenteeism_academic_year
            own = (
                profile.chronic_absenteeism_rate
                if spec.key == "absenteeism.total"
                else profile.chronic_absenteeism_subgroups[spec.code]
            )
            dist = (
                absenteeism_district.category(spec.code)
                if absenteeism_district is not None
                else Measure.not_reported()
            )
            st = (
                absenteeism_state.category(spec.code)
                if absenteeism_state is not None
                else Measure.not_reported()
            )
            counts = (
                cover.absenteeism_total
                if spec.key == "absenteeism.total"
                else cover.absenteeism_subgroups[spec.code]
            )
            source = "d3"
        yield EvidenceRecord(
            id=f"{cds}|{spec.key}|{year}",
            measure=spec.key,
            year=year,
            source=source,
            school=Cell.of(own),
            district=Cell.of(dist),
            state=Cell.of(st),
            coverage=dict(counts),
        )


def build_bundle(
    *,
    directory: Path,
    enrollment: Path,
    out_dir: Path,
    is_fixture: bool,
    absenteeism: Path | None = None,
) -> int:
    """Write ``index.json`` and one ``schools/<cds>.json`` per active school.

    Uses the page build's own assembly, coverage, and context loaders, so the
    bundle cannot carry a figure the page does not. Returns the school count.
    """
    assembly = assemble_profiles(directory, enrollment, absenteeism_path=absenteeism)
    cover = site_coverage(assembly)
    context = load_context(enrollment)
    abs_context = (
        load_absenteeism_context(absenteeism) if absenteeism is not None else None
    )
    refs = site_sources(
        directory=directory,
        enrollment=enrollment,
        academic_year=assembly.academic_year,
        is_fixture=is_fixture,
        absenteeism=absenteeism,
        absenteeism_academic_year=assembly.absenteeism_academic_year,
    )
    sources = {
        ref.key: SourceInfo(
            key=ref.key,
            file_name=ref.file_name,
            url=ref.url,
            access_date=ref.access_date,
            academic_year=ref.academic_year,
        )
        for ref in refs
    }
    schools_dir = out_dir / "schools"
    schools_dir.mkdir(parents=True, exist_ok=True)
    for profile in assembly.profiles:
        cds = profile.school.cds_code
        evidence = SchoolEvidence(
            cds=cds,
            name=profile.school.name,
            district=profile.school.district,
            county=profile.school.county,
            city=profile.school.city,
            charter=profile.school.charter,
            grades_served=profile.school.grades_served,
            is_fixture=is_fixture,
            schools_in_build=cover.schools,
            sources=sources,
            records={
                r.measure: r
                for r in _records(
                    profile,
                    cover,
                    context.for_district(cds),
                    context.state,
                    abs_context.for_district(cds) if abs_context else None,
                    abs_context.state if abs_context else None,
                )
            },
        )
        (schools_dir / f"{cds}.json").write_text(
            json.dumps(evidence.to_json(), sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
    index = {
        "is_fixture": is_fixture,
        "schools": cover.schools,
        "academic_year": assembly.academic_year,
        "absenteeism_academic_year": assembly.absenteeism_academic_year,
        "sources": {k: asdict(v) for k, v in sorted(sources.items())},
        "measures": list(CATALOG),
    }
    (out_dir / "index.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return cover.schools


def load_school(root: Path, cds: str) -> SchoolEvidence | None:
    """The evidence for one school, or ``None`` if the build does not carry it.

    The CDS code is validated before it touches a path: fourteen digits or it
    is not a code this project has ever seen, and it never becomes a filename.
    """
    if len(cds) != 14 or not cds.isdigit():
        return None
    path = root / "schools" / f"{cds}.json"
    if not path.is_file():
        return None
    return SchoolEvidence.from_json(json.loads(path.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-ask-bundle",
        description="Write the per-school evidence bundle the ask service reads.",
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--enrollment", type=Path, required=True)
    parser.add_argument("--absenteeism", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args(argv)
    count = build_bundle(
        directory=args.directory,
        enrollment=args.enrollment,
        out_dir=args.out,
        is_fixture=args.fixture,
        absenteeism=args.absenteeism,
    )
    print(f"evidence bundle: {count} schools in {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
