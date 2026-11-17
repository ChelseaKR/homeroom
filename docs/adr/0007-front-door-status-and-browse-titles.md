# 0007. The front door says what is published, and browse pages get search titles

Status: Accepted (owner decision, 2026-11-17)
Date: 2026-11-17
Deciders: Chelsea Kelly-Reif
Relates to: ADR 0002 (refuse to rank schools), which binds this decision and is
not amended. ADR 0006 made the same kind of change to the school pages.

## Context

The search review of 2026-11-17 found three pieces of copy working against the
site:

- **The front door's status line was out of date.** It said "Homeroom is in
  development. The schools published so far are the ones reached through the
  counties below..." Every active school has been published since 2026-09-05.
  The page's title was just "Homeroom".
- **District pages were thin in search.** The title was "Sacramento City
  Unified · Homeroom" and the description repeated the site tagline. District
  pages already brought 2 of the site's 11 search clicks.
- **County pages** were titled "Alameda County · Homeroom", which does not say
  what the page lists.

## Decision

1. The front door's title is "Homeroom: California public school enrollment, in
   English and Spanish". The page is bilingual under `lang="en"`, so it carries
   the one English title.
2. The status line says Homeroom publishes every active California public
   school, then gives the count the build actually rendered. The count is never
   typed in. A `--cds` build of fewer schools keeps the earlier "published so
   far" wording (`landing_status_partial`), because "every" would then be false.
   That count is the one number the front door carries, and
   `test_the_landing_page_publishes_no_figure` allows only that sentence.
3. County title: "{county} County schools by district". District title:
   "{district} ({county} County): public schools". District description: "Each
   public school in {district}, {county} County, with its {year} enrollment and
   chronic absenteeism from California Department of Education files." The year
   is the year the district's schools' figures are for.
4. The district page's list heading, "Schools published so far" / "Escuelas
   publicadas hasta ahora", becomes "Public schools" / "Escuelas públicas": every
   active school is published, so the list is not "so far" (owner decision,
   2026-11-17). It is a reworded key, not a new one.
5. The Spanish says the same things in the catalog's own terms. It was drafted at
   the owner's request and she approved all of it on 2026-11-17.

## Consequences

- Five interface keys per locale: 235 keys per locale, on top of ADR 0006's two.
- Nothing ranks, scores or compares a school; `tests/test_landing_titles.py`
  holds the new copy to that.
- The served pages change at the next `make publish`, which waits on #82.
