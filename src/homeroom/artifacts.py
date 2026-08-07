"""Emit deterministic JSON artifacts: the profiles, and coverage beside them.

Two files land in the output directory:

``schools.json``
    One entry per active school, Measures serialized as ``{"status": ...}`` with a
    ``"value"`` key only when the state actually published a number. A suppressed
    or not-reported measure has no value at all, so no consumer can read it as
    zero. The reviewed category display names ride along.

``coverage.json``
    Coverage as a first-class output: per-measure reported/suppressed/not-reported
    counts, the join gaps in both directions, the source files with their
    PROVENANCE.md access dates, and an ``is_fixture`` flag so fixture output can
    never impersonate acquired data.

Determinism is a requirement, not a nicety: re-running on the same inputs must be
byte-identical (sorted keys, CDS-ordered schools, no wall clock anywhere). The
access dates are reviewed constants mirrored from PROVENANCE.md and tested for
sync; a fixture build stamps ``null`` instead, because fixtures were never
acquired from CDE.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from homeroom.enrollment import GRADE_COLUMNS, TOTAL_CATEGORY
from homeroom.measures import Measure, MeasureStatus, coverage
from homeroom.profiles import (
    CATEGORY_NAMES,
    SUBGROUP_CODES,
    SUBGROUP_FAMILIES,
    ProfileAssembly,
    SchoolProfile,
    assemble_profiles,
)

DIRECTORY_ACCESS_DATE = "2026-08-07"
"""When D1 (pubschls.txt) was acquired. Mirrors PROVENANCE.md; tested for sync."""

ENROLLMENT_ACCESS_DATE = "2026-08-07"
"""When D2 (cdenroll2526.txt) was acquired. Mirrors PROVENANCE.md; tested for sync."""


@dataclass(frozen=True)
class ArtifactBuild:
    assembly: ProfileAssembly
    schools_path: Path
    coverage_path: Path


def measure_json(measure: Measure) -> dict[str, object]:
    """``{"status": ...}`` plus ``"value"`` only for a published number.

    Integral counts serialize as integers; the absence of ``"value"`` is the
    artifact-level form of null-never-zero.
    """
    payload: dict[str, object] = {"status": measure.status.value}
    if measure.status is MeasureStatus.REPORTED:
        value = measure.number()
        payload["value"] = int(value) if value.is_integer() else value
    return payload


def _school_json(profile: SchoolProfile) -> dict[str, object]:
    school = profile.school
    return {
        "cds_code": school.cds_code,
        "name": school.name,
        "district": school.district,
        "county": school.county,
        "city": school.city,
        "charter": school.charter,
        "virtual_code": school.virtual_code,
        "grades_served": school.grades_served,
        "total_enrollment": measure_json(profile.total_enrollment),
        "grades": {
            grade: measure_json(measure) for grade, measure in profile.grades.items()
        },
        "subgroups": {
            family: {code: measure_json(profile.subgroups[code]) for code in codes}
            for family, codes in SUBGROUP_FAMILIES.items()
        },
    }


def _schools_payload(assembly: ProfileAssembly) -> dict[str, object]:
    named = (TOTAL_CATEGORY, *SUBGROUP_CODES)
    return {
        "academic_year": assembly.academic_year,
        "reporting_categories": {code: CATEGORY_NAMES[code] for code in named},
        "schools": [_school_json(profile) for profile in assembly.profiles],
    }


def _coverage_payload(
    assembly: ProfileAssembly,
    *,
    directory_name: str,
    enrollment_name: str,
    is_fixture: bool,
) -> dict[str, object]:
    profiles = assembly.profiles
    return {
        "is_fixture": is_fixture,
        "sources": {
            "D1_directory": {
                "file": directory_name,
                "access_date": None if is_fixture else DIRECTORY_ACCESS_DATE,
            },
            "D2_enrollment": {
                "file": enrollment_name,
                "access_date": None if is_fixture else ENROLLMENT_ACCESS_DATE,
                "academic_year": assembly.academic_year,
            },
        },
        "profiles": len(profiles),
        "join_gaps": {
            "school_totals_without_directory_match": assembly.unjoined_school_totals,
            "active_schools_without_enrollment_rows": assembly.schools_without_enrollment,
        },
        "measures": {
            "total_enrollment": coverage(p.total_enrollment for p in profiles),
            "grades": {
                grade: coverage(p.grades[grade] for p in profiles)
                for grade in GRADE_COLUMNS
            },
            "subgroups": {
                code: coverage(p.subgroups[code] for p in profiles)
                for code in SUBGROUP_CODES
            },
        },
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def build_artifacts(
    *,
    directory: Path,
    enrollment: Path,
    out_dir: Path,
    is_fixture: bool,
) -> ArtifactBuild:
    assembly = assemble_profiles(directory, enrollment)
    out_dir.mkdir(parents=True, exist_ok=True)
    schools_path = out_dir / "schools.json"
    coverage_path = out_dir / "coverage.json"
    _write(schools_path, _schools_payload(assembly))
    _write(
        coverage_path,
        _coverage_payload(
            assembly,
            directory_name=directory.name,
            enrollment_name=enrollment.name,
            is_fixture=is_fixture,
        ),
    )
    return ArtifactBuild(
        assembly=assembly, schools_path=schools_path, coverage_path=coverage_path
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-artifacts",
        description="Build deterministic school-profile artifacts from source files.",
    )
    parser.add_argument(
        "--directory", type=Path, required=True, help="path to the D1 directory file"
    )
    parser.add_argument(
        "--enrollment", type=Path, required=True, help="path to the D2 enrollment file"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="output directory for JSON artifacts"
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="mark output as built from committed fixtures, not acquired files",
    )
    args = parser.parse_args(argv)
    build = build_artifacts(
        directory=args.directory,
        enrollment=args.enrollment,
        out_dir=args.out,
        is_fixture=args.fixture,
    )
    assembly = build.assembly
    subgroup_counts = coverage(
        measure
        for profile in assembly.profiles
        for measure in profile.subgroups.values()
    )
    print(f"profiles: {len(assembly.profiles)} ({assembly.academic_year})")
    print(
        "subgroup measures: "
        + ", ".join(f"{status}={count}" for status, count in subgroup_counts.items())
    )
    print(
        f"join gaps: {assembly.unjoined_school_totals} school totals without a "
        f"directory match, {assembly.schools_without_enrollment} active schools "
        "without enrollment rows"
    )
    print(f"wrote {build.schools_path} and {build.coverage_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
