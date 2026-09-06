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

A source that was not supplied to the build is stated as absent rather than
emitted as a field of zeros. Teacher assignment outcomes (D5) and chronic
absenteeism (D3) are both optional input; without either, ``coverage.json``
records the source as unsupplied and no school carries the corresponding block at
all, so nothing in the artifact implies Homeroom looked and found nothing.

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

from homeroom.absenteeism import TOTAL_CATEGORY as ABSENTEEISM_TOTAL_CATEGORY
from homeroom.assignments import OUTCOME_NAMES, OUTCOMES
from homeroom.enrollment import GRADE_COLUMNS, TOTAL_CATEGORY
from homeroom.measures import Measure, MeasureStatus, coverage
from homeroom.profiles import (
    ABSENTEEISM_CATEGORY_NAMES,
    ABSENTEEISM_SUBGROUP_CODES,
    ABSENTEEISM_SUBGROUP_FAMILIES,
    CATEGORY_NAMES,
    SUBGROUP_CODES,
    SUBGROUP_FAMILIES,
    ProfileAssembly,
    SchoolProfile,
    assemble_profiles,
    assignment_measure,
    assignment_total,
)

DIRECTORY_ACCESS_DATE = "2026-08-07"
"""When D1 (pubschls.txt) was acquired. Mirrors PROVENANCE.md; tested for sync."""

ENROLLMENT_ACCESS_DATE = "2026-08-07"
"""When D2 (cdenroll2526.txt) was acquired. Mirrors PROVENANCE.md; tested for sync."""

ASSIGNMENTS_ACCESS_DATE: str | None = "2026-08-21"
"""When the D5 file (``tamo2324.txt``) was downloaded and its schema verified
against the real 2023-24 file. Mirrors PROVENANCE.md; tested for sync.

Acquired is not the same fact as published, and for thirteen days it was the only
fact this date recorded: the file had been read and :mod:`homeroom.assignments`
rewritten to match it (issue #5), while whether any D5 figure should reach a
build's default invocation or a page was an open question (issue #59). The owner
answered it on 2026-09-05 (ADR 0005), so ``make data``, ``make site`` and
``make publish`` are all given the file now. The two facts stay separate anyway:
this constant says when the file was downloaded, and a build that is not given it
stamps nothing and publishes nothing."""

ABSENTEEISM_ACCESS_DATE: str | None = "2026-08-21"
"""When D3 (``chronicabsenteeism25.txt``, the 2024-25 file) was acquired. Mirrors
PROVENANCE.md; tested for sync. D3 is wired into `make data` and `make site`'s
default invocation (Makefile): this is the first masked-heavy measure this
project publishes end to end (M3, docs/ROADMAP.md). This docstring read "unlike
D5" until 2026-09-05, when ADR 0005 wired D5 in alongside it."""


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


def _assignments_json(profile: SchoolProfile) -> dict[str, object]:
    """One school's published assignment outcomes, counts and shares side by side.

    Both are copied. A share is never divided out of the counts, so a school whose
    percent column is masked shows a masked share even where a count is visible.
    """
    row = profile.teacher_assignments
    if row is None:
        return {
            "academic_year": None,
            "total_assignments": measure_json(Measure.not_reported()),
            "outcomes": {
                outcome: {
                    "count": measure_json(Measure.not_reported()),
                    "percent": measure_json(Measure.not_reported()),
                }
                for outcome in OUTCOMES
            },
        }
    return {
        "academic_year": row.academic_year,
        "total_assignments": measure_json(row.total),
        "outcomes": {
            outcome: {
                "count": measure_json(row.counts[outcome]),
                "percent": measure_json(row.percents[outcome]),
            }
            for outcome in OUTCOMES
        },
    }


def _absenteeism_json(profile: SchoolProfile) -> dict[str, object]:
    """This school's published chronic-absenteeism rates, total and by subgroup.

    Each is a copied ``ChronicAbsenteeismRate`` cell, never a count divided by an
    enrollment figure this project holds separately.
    """
    return {
        "total": measure_json(profile.chronic_absenteeism_rate),
        "subgroups": {
            family: {
                code: measure_json(profile.chronic_absenteeism_subgroups[code])
                for code in codes
            }
            for family, codes in ABSENTEEISM_SUBGROUP_FAMILIES.items()
        },
    }


def _school_json(
    profile: SchoolProfile, *, with_assignments: bool, with_absenteeism: bool
) -> dict[str, object]:
    school = profile.school
    payload: dict[str, object] = {
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
    if with_assignments:
        payload["teacher_assignments"] = _assignments_json(profile)
    if with_absenteeism:
        payload["chronic_absenteeism"] = _absenteeism_json(profile)
    return payload


def _schools_payload(assembly: ProfileAssembly) -> dict[str, object]:
    named = (TOTAL_CATEGORY, *SUBGROUP_CODES)
    with_assignments = assembly.assignments_academic_year is not None
    with_absenteeism = assembly.absenteeism_academic_year is not None
    payload: dict[str, object] = {
        "academic_year": assembly.academic_year,
        "reporting_categories": {code: CATEGORY_NAMES[code] for code in named},
        "schools": [
            _school_json(
                profile,
                with_assignments=with_assignments,
                with_absenteeism=with_absenteeism,
            )
            for profile in assembly.profiles
        ],
    }
    if with_assignments:
        payload["teacher_assignment_academic_year"] = assembly.assignments_academic_year
        payload["teacher_assignment_outcomes"] = dict(OUTCOME_NAMES)
    if with_absenteeism:
        payload["chronic_absenteeism_academic_year"] = (
            assembly.absenteeism_academic_year
        )
        named_absenteeism = (ABSENTEEISM_TOTAL_CATEGORY, *ABSENTEEISM_SUBGROUP_CODES)
        payload["chronic_absenteeism_categories"] = {
            code: ABSENTEEISM_CATEGORY_NAMES[code] for code in named_absenteeism
        }
    return payload


def _assignment_coverage(assembly: ProfileAssembly) -> dict[str, object]:
    profiles = assembly.profiles
    return {
        "total_assignments": coverage(assignment_total(p) for p in profiles),
        "outcomes": {
            outcome: {
                "count": coverage(
                    assignment_measure(p, outcome, percent=False) for p in profiles
                ),
                "percent": coverage(
                    assignment_measure(p, outcome, percent=True) for p in profiles
                ),
            }
            for outcome in OUTCOMES
        },
    }


def _absenteeism_coverage(assembly: ProfileAssembly) -> dict[str, object]:
    profiles = assembly.profiles
    return {
        "total": coverage(p.chronic_absenteeism_rate for p in profiles),
        "subgroups": {
            code: coverage(p.chronic_absenteeism_subgroups[code] for p in profiles)
            for code in ABSENTEEISM_SUBGROUP_CODES
        },
    }


def _coverage_payload(
    assembly: ProfileAssembly,
    *,
    directory_name: str,
    enrollment_name: str,
    assignments_name: str | None,
    absenteeism_name: str | None,
    is_fixture: bool,
) -> dict[str, object]:
    profiles = assembly.profiles
    assignments_supplied = assembly.assignments_academic_year is not None
    absenteeism_supplied = assembly.absenteeism_academic_year is not None
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
            "D3_chronic_absenteeism": {
                "supplied": absenteeism_supplied,
                "file": absenteeism_name,
                "access_date": None if is_fixture else ABSENTEEISM_ACCESS_DATE,
                "academic_year": assembly.absenteeism_academic_year,
            },
            "D5_teacher_assignments": {
                "supplied": assignments_supplied,
                "file": assignments_name,
                "access_date": None if is_fixture else ASSIGNMENTS_ACCESS_DATE,
                "academic_year": assembly.assignments_academic_year,
            },
        },
        "profiles": len(profiles),
        "join_gaps": {
            "school_totals_without_directory_match": assembly.unjoined_school_totals,
            "active_schools_without_enrollment_rows": assembly.schools_without_enrollment,
            "assignment_rows_without_directory_match": assembly.unjoined_assignment_rows,
            "active_schools_without_assignment_rows": assembly.schools_without_assignments,
            "absenteeism_rows_without_directory_match": assembly.unjoined_absenteeism_rows,
            "active_schools_without_absenteeism_rows": assembly.schools_without_absenteeism,
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
            "teacher_assignments": (
                _assignment_coverage(assembly) if assignments_supplied else None
            ),
            "chronic_absenteeism": (
                _absenteeism_coverage(assembly) if absenteeism_supplied else None
            ),
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
    assignments: Path | None = None,
    absenteeism: Path | None = None,
) -> ArtifactBuild:
    assembly = assemble_profiles(
        directory, enrollment, assignments, absenteeism_path=absenteeism
    )
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
            assignments_name=assignments.name if assignments is not None else None,
            absenteeism_name=absenteeism.name if absenteeism is not None else None,
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
        "--assignments",
        type=Path,
        default=None,
        help="path to the D5 teacher assignment monitoring file (optional)",
    )
    parser.add_argument(
        "--absenteeism",
        type=Path,
        default=None,
        help="path to the D3 chronic absenteeism file (optional)",
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
        assignments=args.assignments,
        absenteeism=args.absenteeism,
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
    if assembly.assignments_academic_year is None:
        print("teacher assignments: no D5 file supplied, nothing published")
    else:
        clear_counts = coverage(
            assignment_measure(profile, "clear", percent=False)
            for profile in assembly.profiles
        )
        print(
            f"teacher assignments: {assembly.assignments_academic_year}, "
            "clear-assignment counts "
            + ", ".join(f"{status}={count}" for status, count in clear_counts.items())
            + f"; {assembly.schools_without_assignments} active schools without rows"
        )
    if assembly.absenteeism_academic_year is None:
        print("chronic absenteeism: no D3 file supplied, nothing published")
    else:
        rate_counts = coverage(
            profile.chronic_absenteeism_rate for profile in assembly.profiles
        )
        print(
            f"chronic absenteeism: {assembly.absenteeism_academic_year}, "
            "total-rate coverage "
            + ", ".join(f"{status}={count}" for status, count in rate_counts.items())
            + f"; {assembly.schools_without_absenteeism} active schools without rows"
        )
    print(f"wrote {build.schools_path} and {build.coverage_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
