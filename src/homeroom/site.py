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
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

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
    canonical_url,
    page_name,
    render_school,
    site_coverage,
    social_card_name,
)

#: Where the preview cards live. Inside the package rather than beside it, so an
#: installed wheel carries them the same way a checkout does. They are the only
#: bytes this project publishes that no build step produces: rasterising text
#: needs a font renderer and ``dependencies = []`` is a property this package
#: keeps, so ``tools/make_social_card.py`` draws them out-of-band from the same
#: ``i18n.py`` table the pages are rendered from, and the result is committed.
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


class MissingAssetError(FileNotFoundError):
    """A page's ``og:image`` would name a file this build cannot publish.

    Raised rather than warned, and rather than skipped, because the two quiet
    outcomes are both worse. Emitting the tag anyway publishes a card pointing
    at a 404, which renders worse than the ``summary`` card this site carried
    before there was an image. Dropping the tag instead would leave a hosted
    build silently without a card and nothing to notice it, which is exactly the
    failure the deployment checks in this repository exist to refuse.
    """


def _publish_social_cards(out_dir: Path) -> list[Path]:
    """Copy one preview card per locale into the build.

    Only ever called for a build that was given an origin: without one no page
    carries social markup at all, and a build that names no address must stay
    byte-identical to a build made before any of this existed.
    """
    written: list[Path] = []
    for locale in LOCALES:
        name = social_card_name(locale)
        source = ASSETS_DIR / name
        if not source.is_file():
            raise MissingAssetError(
                f"{source} is missing, but every {locale} page in a hosted build "
                f"names it as its og:image. Redraw the cards with "
                f"`uv run --with pillow python tools/make_social_card.py`."
            )
        destination = out_dir / name
        shutil.copyfile(source, destination)
        written.append(destination)
    return written


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


class SiteUrlError(ValueError):
    """``--site-url`` was given something that is not an https origin."""


def normalise_site_url(site_url: str) -> str:
    """The origin, without its trailing slash, or a hard error.

    A canonical link and a sitemap both publish absolute addresses, so a
    mistyped origin does not fail loudly; it publishes a page that points a
    crawler somewhere else. The only accepted shape is an ``https`` scheme, a
    host, and no path, query or fragment. ``http`` is refused because the site
    is served over TLS and a canonical naming the plaintext address invites a
    crawler to prefer it.
    """
    parsed = urlsplit(site_url)
    if parsed.scheme != "https":
        raise SiteUrlError(f"site url must be https, got {site_url!r}")
    if not parsed.netloc:
        raise SiteUrlError(f"site url names no host: {site_url!r}")
    if parsed.path.strip("/") or parsed.query or parsed.fragment:
        raise SiteUrlError(
            f"site url must be a bare origin with no path, query or fragment, "
            f"got {site_url!r}"
        )
    return f"https://{parsed.netloc}"


def robots_txt(site_url: str) -> str:
    """What a crawler is told at ``/robots.txt``.

    Nothing here is disallowed. The ask pages are the one part of the site kept
    out of an index, and they carry ``<meta name="robots" content="noindex">``
    to say so; a ``Disallow`` on top of that would stop a crawler fetching the
    page and so stop it ever reading the noindex, which is the opposite of what
    it is for.
    """
    return f"User-agent: *\nAllow: /\n\nSitemap: {site_url}/sitemap.xml\n"


def sitemap_xml(site_url: str, paths: list[str]) -> str:
    """The indexable pages, as a sitemap.

    ``paths`` are published file names, already in build order, so the file is
    deterministic for the same reason every page is. The ask pages are not here:
    they are ``noindex``, and listing a page in a sitemap while telling a crawler
    not to index it asks for two different things at once.
    """
    locs = "\n".join(
        f"  <url><loc>{escape(canonical_url(site_url, path))}</loc></url>"
        for path in paths
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{locs}\n"
        "</urlset>\n"
    )


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
    site_url: str | None = None,
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

    ``site_url`` is the origin the output will be served from. Given, every
    indexable page gains a canonical address and its social tags, and the build
    also writes ``robots.txt``, ``sitemap.xml`` and one preview card per locale.
    Left out, no page names an address, no crawler file is written, no card is
    copied, and the output is byte-identical to a build before any of this: a
    page cannot honestly claim a canonical address on a build that has not been
    told where it will be served.

    The cards are copied under the same condition that emits the tag naming
    them, in the same function, so a hosted build cannot publish an ``og:image``
    pointing at a file it did not also publish.
    """
    if site_url is not None:
        site_url = normalise_site_url(site_url)
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
    indexable: list[str] = []
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
                    site_url=site_url,
                ),
                encoding="utf-8",
            )
            pages.append(path)
            indexable.append(page_name(cds, locale))
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
            render_landing(schools, is_fixture=is_fixture, site_url=site_url),
            encoding="utf-8",
        )
        pages.append(index)
        indexable.insert(0, "index.html")
    if site_url is not None:
        pages.extend(_publish_social_cards(out_dir))
        robots = out_dir / "robots.txt"
        robots.write_text(robots_txt(site_url), encoding="utf-8")
        pages.append(robots)
        sitemap = out_dir / "sitemap.xml"
        sitemap.write_text(sitemap_xml(site_url, indexable), encoding="utf-8")
        pages.append(sitemap)
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
    parser.add_argument(
        "--site-url",
        default=None,
        metavar="ORIGIN",
        help=(
            "https origin this build will be served from, with no path. Given, "
            "every indexable page carries a canonical address and its social "
            "tags, and robots.txt and sitemap.xml are written. Omit for none"
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
        site_url=args.site_url,
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
