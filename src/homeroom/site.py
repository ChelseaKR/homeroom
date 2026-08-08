"""Build the static bilingual pages: one file per school per language.

The page build is deliberately narrower than the artifact build. It takes the
directory and the enrollment file and nothing else, so there is no argument by
which a teacher assignment figure could reach a page: D5 has not been acquired,
and the strongest form of "no D5 number is published about a real school" is a
build that cannot be handed the file (PROVENANCE.md D5, docs/ROADMAP.md D5a). The
pages say so in words, in both languages, rather than leaving a silent gap.

Two modes, mirroring ``make data`` and ``make data-offline``:

* acquired files, with ``--cds`` naming the schools to render, and PROVENANCE.md
  access dates stamped into each page's sources section;
* ``--fixture``, which renders every school in the committed fixtures, stamps no
  access date anywhere, and puts a banner at the top of each page saying the data
  is not real. That is what the accessibility and HTML-conformance gates run
  against, so they run with no acquired file present and no network.

Output is deterministic: schools in CDS order, locales in a fixed order, no wall
clock. CI builds twice and compares hashes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from homeroom.artifacts import DIRECTORY_ACCESS_DATE, ENROLLMENT_ACCESS_DATE
from homeroom.i18n import LOCALES
from homeroom.profiles import ProfileAssembly, SchoolProfile, assemble_profiles
from homeroom.render import (
    DIRECTORY_URL,
    ENROLLMENT_URL,
    SiteCoverage,
    SourceRef,
    page_name,
    render_school,
    site_coverage,
)


class UnknownSchoolError(ValueError):
    """A CDS code was asked for that no active school in the build carries."""


@dataclass(frozen=True)
class SiteBuild:
    assembly: ProfileAssembly
    coverage: SiteCoverage
    schools: list[SchoolProfile]
    pages: list[Path]


def sources(
    *,
    directory: Path,
    enrollment: Path,
    academic_year: str,
    is_fixture: bool,
) -> tuple[SourceRef, ...]:
    """The files this build read, with the dates PROVENANCE.md records.

    A fixture build stamps no date, because nobody downloaded a fixture. The same
    rule governs ``coverage.json``; the two are tested to agree.
    """
    return (
        SourceRef(
            key="d2",
            file_name=enrollment.name,
            url=ENROLLMENT_URL,
            access_date=None if is_fixture else ENROLLMENT_ACCESS_DATE,
            academic_year=academic_year,
        ),
        SourceRef(
            key="d1",
            file_name=directory.name,
            url=DIRECTORY_URL,
            access_date=None if is_fixture else DIRECTORY_ACCESS_DATE,
        ),
    )


def _selected(
    assembly: ProfileAssembly, cds_codes: tuple[str, ...]
) -> list[SchoolProfile]:
    """The schools to render, in CDS order. An unknown code is a hard error.

    Rendering nothing for a code somebody asked for would look like a school with
    no data, which is a claim about a real school this build is not entitled to
    make.
    """
    if not cds_codes:
        return list(assembly.profiles)
    by_code = {profile.school.cds_code: profile for profile in assembly.profiles}
    missing = sorted(code for code in cds_codes if code not in by_code)
    if missing:
        raise UnknownSchoolError(
            f"no active school in this build carries CDS code(s) {missing}; "
            "refusing to render a page for a school the directory does not list"
        )
    return [by_code[code] for code in sorted(set(cds_codes))]


def build_site(
    *,
    directory: Path,
    enrollment: Path,
    out_dir: Path,
    is_fixture: bool,
    cds_codes: tuple[str, ...] = (),
) -> SiteBuild:
    """Render every selected school in every locale. Returns what was written."""
    assembly = assemble_profiles(directory, enrollment)
    cover = site_coverage(assembly)
    refs = sources(
        directory=directory,
        enrollment=enrollment,
        academic_year=assembly.academic_year,
        is_fixture=is_fixture,
    )
    schools = _selected(assembly, cds_codes)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    for profile in schools:
        for locale in LOCALES:
            path = out_dir / page_name(profile.school.cds_code, locale)
            path.write_text(
                render_school(
                    profile,
                    locale=locale,
                    cover=cover,
                    sources=refs,
                    is_fixture=is_fixture,
                ),
                encoding="utf-8",
            )
            pages.append(path)
    return SiteBuild(assembly=assembly, coverage=cover, schools=schools, pages=pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-site",
        description="Render bilingual school pages from acquired CDE files.",
    )
    parser.add_argument(
        "--directory", type=Path, required=True, help="path to the D1 directory file"
    )
    parser.add_argument(
        "--enrollment", type=Path, required=True, help="path to the D2 enrollment file"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="output directory for the pages"
    )
    parser.add_argument(
        "--cds",
        action="append",
        default=[],
        metavar="CODE",
        help="14-digit CDS code to render; repeatable. Omit to render every school",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="mark output as built from committed fixtures, not acquired files",
    )
    args = parser.parse_args(argv)
    build = build_site(
        directory=args.directory,
        enrollment=args.enrollment,
        out_dir=args.out,
        is_fixture=args.fixture,
        cds_codes=tuple(args.cds),
    )
    counts = build.coverage.total_enrollment
    print(
        f"pages: {len(build.pages)} "
        f"({len(build.schools)} schools x {len(LOCALES)} locales) "
        f"in {args.out}"
    )
    print(f"academic year: {build.assembly.academic_year}")
    print(
        "total-enrollment coverage across "
        f"{build.coverage.schools} active schools: "
        + ", ".join(f"{status}={count}" for status, count in counts.items())
    )
    print("teacher assignments: no D5 file is read here, so no page carries one")
    for page in build.pages[:4]:
        print(f"wrote {page}")
    if len(build.pages) > 4:
        print(f"...and {len(build.pages) - 4} more")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
