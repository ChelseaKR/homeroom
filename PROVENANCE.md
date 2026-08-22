# Provenance

Every source is a California Department of Education public file, downloaded from CDE's
public data pages in a browser, the way the pages are meant to be used. The pipeline
therefore treats source files as locally acquired inputs rather than fetching them at
build time: record the access date beside each file when acquired, and the pipeline
stamps it into coverage output. CI never touches the network.

| # | Source | What it provides | Acquisition | Status |
|---|---|---|---|---|
| D1 | Public Schools and Districts directory (`pubschls.txt`), https://www.cde.ca.gov/schooldirectory/ (download: text report) | Canonical school list: CDS codes, names, districts, status, type, grades, coordinates, charter/virtual flags | Browser download, ~8.8 MB tab-delimited | Endpoint verified live 2026-08-07 (HEAD 200, text/csv, 8,788,547 bytes); parser built |
| D2 | Census Day Enrollment Data, https://www.cde.ca.gov/ds/ad/filesenrcensus.asp (file structure: https://www.cde.ca.gov/ds/ad/fsenrcensus.asp; the pre-2026 URL filesenr.asp now 404s, renamed upstream, observed 2026-08-07) | Enrollment by school, grade, demographic group | Browser download, annual. Acquire from the browser page and record which school year's file was taken | 2025-26 file acquired 2026-08-07, saved as `cdenroll2526.txt` (32,041,859 bytes, 269,090 data rows); parser built; ReportingCategory names reviewed against the file structure page 2026-08-07; the file's district and statewide `AggregateLevel` rows are read for the context columns on each school page, taking only `Charter=ALL` rows, because each entity is published three times (charter, non-charter, both) and in this file Davis Joint Unified's three district rows read 561 / 7,682 / 8,243 for the same category. Homeroom never sums school rows into a district or state figure |
| D3 | Chronic absenteeism files, https://www.cde.ca.gov/ds/ad/filesabd.asp, linking https://www3.cde.ca.gov/demo-downloads/attendance/chronicabsenteeism25-v2.txt (file structure: https://www.cde.ca.gov/ds/ad/fsabd.asp) | Chronic absenteeism eligible cumulative enrollment, count, and rate by school and group, with CDE small-cell masking | Browser download, annual | **Acquired 2026-08-21.** The 2024-25 file (`chronicabsenteeism25.txt`, 33,781,100 bytes, 341,490 data rows) was downloaded and its header read directly: identity columns are spaced (`Academic Year`, `Charter School`, ...) while the three measure columns are concatenated (`ChronicAbsenteeismEligibleCumulativeEnrollment`, `ChronicAbsenteeismCount`, `ChronicAbsenteeismRate`); `Charter School` and `DASS` are two independent `All`/`Yes`/`No` dimensions, so a genuine district or state figure needs both to read `All`, not the one dimension D2 has. 25 reporting-category codes were observed, none shared with D2's own codes for the same underlying groups (D2's `RE_A` is this file's `RA`); see `src/homeroom/profiles.py` `ABSENTEEISM_CATEGORY_NAMES`. Scanning every row found 104,469 of 341,490 (30.6%) carrying a mask on at least one of the three numeric cells, and masking is always all three together, never a subset. `src/homeroom/absenteeism.py` was written and verified against this file; `docs/ROADMAP.md` M3 records the measured coverage. Wired into `make data` and `make site`'s default invocation (Makefile `--absenteeism`), rendered on every school page (ROADMAP M3) |
| D4 | CA School Dashboard research files, https://www.cde.ca.gov/ta/ac/cm/ | Dashboard indicator data behind the color bands | Browser download, annual | Planned |
| D5 | Teacher Assignment Monitoring Outcome files, https://www.cde.ca.gov/ds/ad/filestamo.asp, linking https://www3.cde.ca.gov/demo-downloads/tamo/tamo2324.txt (file structure: https://www.cde.ca.gov/ds/ad/fstamo.asp). CDE publishes these from the Commission on Teacher Credentialing's CalSAAS system | By school: teaching FTE (full-time-equivalent, not integer counts) held on a clear credential and appropriately assigned, and the other authorization states the state tracks, with CDE small-cell masking where it applies | Browser download, annual. Record which school year's file was taken; it reports on a different cycle than D2 | **Acquired and schema-verified 2026-08-21; not joined to any artifact or page by default.** The 2023-24 file (`tamo2324.txt`, 234,206,408 bytes, 1,528,796 data rows) was downloaded and its header read directly, which found the provisional contract this project carried before acquisition (issue #5) wrong in every particular: real column names are spaced (`Total FTE`, `Clear FTE (count)`, ...) rather than concatenated; there are seven outcomes, not five (`incomplete` and `na` were missing entirely); values are fractional FTE, not integer assignment counts; `Charter School`/`DASS` are the words `All`/`Yes`/`No`, not D2's single-letter `ALL`/`Y`/`N`; the file's grain is one row per (school, charter, DASS, grade span, teacher experience level, teacher credential level, subject area) -- up to 150 rows per school, not one -- of which exactly one row per school (experience = credential = `ALL`, subject = `TA`) is CDE's own whole-school total, verified against all 10,064 schools in the file; and the real header carries CDE's own typo, `Unknown FTE FTE (percent)`. Scanning every numeric cell in the file (1,528,796 rows) found zero instances of `*` or any other unrecognized sentinel: unlike D2 and D3, this file does not appear to mask at all in this vintage, and its file-structure page carries no small-cell suppression rule the way D3's does. `src/homeroom/assignments.py` and `fixtures/tamo.sample.txt` were rewritten to match; `docs/ROADMAP.md` D5a records the measured counts. Publishing a D5 figure on a school page, or wiring `--assignments` into `make data`'s default invocation, is a separate decision this acquisition does not make; `make data` and `make site` are unchanged and no D5 number about a real school is published anywhere |
| D6 | Per-pupil expenditure (SACS/LCFF public files) | School-level spending where published | Browser download, annual | Planned |

Rules:

- CDS code (14-digit county-district-school) is the only join key. Names are display-only.
- CDE masks small cells (published as `*`). A masked cell is `null` in every artifact and
  is counted in coverage output. It is never zero.
- No third-party or commercial data (no ratings sites, no real-estate feeds). If CDE does
  not publish it, Homeroom does not show it.
- A parser may be built ahead of its file, but a number may not. A source whose status
  reads "awaiting acquisition" has an access date of `null` everywhere, publishes nothing,
  and says so in `coverage.json`; the pipeline is tested to keep the code constant and this
  table in agreement, so a build cannot stamp a date nobody recorded.
- Each source keeps its own school year. Sources report on different cycles, and a profile
  carries each year beside its own data rather than one label over data from two calendars.

## Documentation corpus (ADR 0003)

The ask layer quotes CDE's own definitions rather than paraphrasing them. The
pages it quotes are retrieved by `tools/corpus_fetch.py` into `corpus/`, and
`corpus/manifest.json` is their provenance register: URL, retrieval date (UTC),
the page's own "Last Reviewed" date, SHA-256 of the HTML as received and of the
text as committed, and passage count. The same rules apply as to the data files:
a person runs the fetch, CI never does, and a file that no longer matches its
recorded hash is refused by the loader rather than quoted. See `corpus/README.md`.
