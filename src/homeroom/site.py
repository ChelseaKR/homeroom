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

from homeroom.artifacts import (
    ABSENTEEISM_ACCESS_DATE,
    DIRECTORY_ACCESS_DATE,
    ENROLLMENT_ACCESS_DATE,
)
from homeroom.askpage import ask_page_name, render_ask_page
from homeroom.context import (
    AbsenteeismContextDriftError,
    ContextDriftError,
    load_absenteeism_context,
    load_context,
)
from homeroom.i18n import LOCALES
from homeroom.landing import render_landing
from homeroom.profiles import ProfileAssembly, SchoolProfile, assemble_profiles
from homeroom.render import (
    ABSENTEEISM_URL,
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
    absenteeism: Path | None = None,
    absenteeism_academic_year: str | None = None,
) -> tuple[SourceRef, ...]:
    """The files this build read, with the dates PROVENANCE.md records.

    A fixture build stamps no date, because nobody downloaded a fixture. The same
    rule governs ``coverage.json``; the two are tested to agree. ``absenteeism`` is
    optional, the same way the D3 source is everywhere else in this module: a
    build with no D3 file names only D1 and D2.
    """
    refs = [
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
    ]
    if absenteeism is not None:
        refs.append(
            SourceRef(
                key="d3",
                file_name=absenteeism.name,
                url=ABSENTEEISM_URL,
                access_date=None if is_fixture else ABSENTEEISM_ACCESS_DATE,
                academic_year=absenteeism_academic_year,
            )
        )
    return tuple(refs)


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
    absenteeism: Path | None = None,
    ask_endpoint: str | None = None,
    landing: bool = False,
) -> SiteBuild:
    """Render every selected school in every locale. Returns what was written.

    ``absenteeism`` (D3) is optional, mirroring how every other optional source in
    this project works: left out, every page's chronic-absenteeism section is
    replaced by the "not yet published" copy, rather than an empty table.

    ``ask_endpoint`` (ADR 0003) is the URL of a running ask service. Given, each
    school page gains one link to an ask page written under ``ask/``; left out,
    no ask page exists and the school pages are byte-identical to a build before
    ADR 0003. Deployment is a separate decision, so the default is out.

    ``landing`` writes ``index.html``, the one bilingual front door listing the
    schools this build published. A hosted site needs a root; a build without it
    is byte-identical to one before there was a landing page, which is what the
    fixture gates compare against.
    """
    assembly = assemble_profiles(directory, enrollment, absenteeism_path=absenteeism)
    cover = site_coverage(assembly)
    context = load_context(enrollment)
    if context.academic_year != assembly.academic_year:
        raise ContextDriftError(
            f"context covers {context.academic_year} but the profiles cover "
            f"{assembly.academic_year}; a page must not read one year's school "
            f"figures against another year's district and statewide figures"
        )
    absenteeism_context = (
        load_absenteeism_context(absenteeism) if absenteeism is not None else None
    )
    if (
        absenteeism_context is not None
        and absenteeism_context.academic_year != assembly.absenteeism_academic_year
    ):
        raise AbsenteeismContextDriftError(
            f"absenteeism context covers {absenteeism_context.academic_year} but "
            f"the profiles cover {assembly.absenteeism_academic_year}; a page must "
            "not read one year's school figures against another year's district "
            "and statewide figures"
        )
    refs = sources(
        directory=directory,
        enrollment=enrollment,
        academic_year=assembly.academic_year,
        is_fixture=is_fixture,
        absenteeism=absenteeism,
        absenteeism_academic_year=assembly.absenteeism_academic_year,
    )
    schools = _selected(assembly, cds_codes)
    out_dir.mkdir(parents=True, exist_ok=True)
    if ask_endpoint:
        (out_dir / "ask").mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    for profile in schools:
        for locale in LOCALES:
            cds = profile.school.cds_code
            path = out_dir / page_name(cds, locale)
            path.write_text(
                render_school(
                    profile,
                    locale=locale,
                    cover=cover,
                    sources=refs,
                    is_fixture=is_fixture,
                    context=context,
                    absenteeism_context=absenteeism_context,
                    ask_href=ask_page_name(cds, locale) if ask_endpoint else None,
                ),
                encoding="utf-8",
            )
            pages.append(path)
            if ask_endpoint:
                ask_path = out_dir / ask_page_name(cds, locale)
                ask_path.write_text(
                    render_ask_page(
                        profile,
                        locale=locale,
                        endpoint=ask_endpoint,
                        is_fixture=is_fixture,
                    ),
                    encoding="utf-8",
                )
                pages.append(ask_path)
    if landing:
        index = out_dir / "index.html"
        index.write_text(
            render_landing(schools, is_fixture=is_fixture), encoding="utf-8"
        )
        pages.append(index)
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
        "--absenteeism",
        type=Path,
        default=None,
        help="path to the D3 chronic absenteeism file (optional)",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="mark output as built from committed fixtures, not acquired files",
    )
    parser.add_argument(
        "--ask-endpoint",
        default=None,
        metavar="URL",
        help=(
            "URL of a running ask service (ADR 0003); adds one link per school "
            "page and writes the ask pages under ask/. Omit for none"
        ),
    )
    parser.add_argument(
        "--landing",
        action="store_true",
        help=(
            "also write index.html, the bilingual front door listing the schools "
            "this build published. Needed by a hosted site; omit for none"
        ),
    )
    args = parser.parse_args(argv)
    build = build_site(
        directory=args.directory,
        enrollment=args.enrollment,
        out_dir=args.out,
        is_fixture=args.fixture,
        cds_codes=tuple(args.cds),
        absenteeism=args.absenteeism,
        ask_endpoint=args.ask_endpoint,
        landing=args.landing,
    )
    counts = build.coverage.total_enrollment
    print(
        f"pages: {len(build.pages)} "
        f"({len(build.schools)} schools x {len(LOCALES)} locales"
        + (", plus an ask page for each" if args.ask_endpoint else "")
        + f") in {args.out}"
    )
    print(f"academic year: {build.assembly.academic_year}")
    print(
        "total-enrollment coverage across "
        f"{build.coverage.schools} active schools: "
        + ", ".join(f"{status}={count}" for status, count in counts.items())
    )
    print("teacher assignments: no D5 file is read here, so no page carries one")
    if build.coverage.absenteeism_supplied:
        abd_counts = build.coverage.absenteeism_total
        print(
            "chronic absenteeism coverage across "
            f"{build.coverage.schools} active schools: "
            + ", ".join(f"{status}={count}" for status, count in abd_counts.items())
        )
    else:
        print("chronic absenteeism: no D3 file given, no page carries one")
    for page in build.pages[:4]:
        print(f"wrote {page}")
    if len(build.pages) > 4:
        print(f"...and {len(build.pages) - 4} more")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
