# 0006. Search titles that name the place, and absolute hreflang

Status: Accepted (owner decision, 2026-11-17)
Date: 2026-11-17
Deciders: Chelsea Kelly-Reif
Relates to: ADR 0002 (refuse to rank schools), which binds this decision and is
not amended. ADR 0001 is not amended either: the pages stay static and rendered
by the same stdlib renderer.

## Context

A search review on 2026-11-17 (Search Console, URL Inspection and GA4, read
only) found Google indexing Homeroom: 242 impressions in the week of 2026-10-19,
1,789 in the week of 2026-11-09, across 846 pages. Two things in the page head
were working against those impressions:

- **The school title did not say where the school is or what the page holds.**
  "Shafter High, 2025-26 school year · Homeroom". Many California schools share
  a name ("Lincoln Elementary"), and the queries that reach these pages ask for
  enrollment ("lincoln high school enrollment 2026"). The description read
  "Enrollment for Shafter High in Kern High", which looks like a school inside a
  school.
- **The hreflang links were relative** (`href="15635291535087.es.html"`).
  Google ignores hreflang without a fully qualified URL, so it could not pair
  the English and Spanish pages, and 460 impressions in the review window went
  to Spanish school pages. There was no `x-default`.

## Decision

1. A school page's title is `{school}, {city} CA: {year} enrollment` and its
   description names the city and county, the year, what the page carries and
   where it came from, ending "No score, no ranking." Spanish follows the same
   shape. The owner chose this pattern (D5, option A) over a longer one that
   mobile results cut off.
2. A directory row with no city keeps the earlier title, and one with no city or
   no county keeps the earlier description. CDE writes "No Data" in some
   columns; none of the 10,534 active schools lacks a city today, but a title
   with a hole in it is worse than the old one. This is why the change adds two
   keys rather than rewording two.
3. A hosted build (`--site-url` given) writes absolute hreflang addresses on
   every school, county and district page, plus `hreflang="x-default"` naming
   the English page. A build given no origin keeps the sibling file names and
   writes no `x-default`, because such a build claims no address.

## Consequences

- Two interface keys per locale: 230 keys per locale.
- Nothing about what a page shows changes. The title and description describe
  the page; they do not compare it to another school, and
  `tests/test_search_head.py` holds them to that.
- The served pages change only when `site/` is re-published. `pages.yml` builds
  nothing, and the next full `make publish` is the one that waits on the hosting
  move (#82, `deploy/site/CUTOVER.md`).

## Alternatives considered

- "Shafter High (Shafter, CA): enrollment and students, 2025-26": longer, and
  cut off on mobile for long school names (D5, option B).
- Keeping the old title (D5, option C).
- Name-based URL slugs: rejected, because changing every URL while Google is
  part-way through discovering the site would reset what it has indexed.
