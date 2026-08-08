# Provenance

Every source is a California Department of Education public file, downloaded from CDE's
public data pages in a browser, the way the pages are meant to be used. The pipeline
therefore treats source files as locally acquired inputs rather than fetching them at
build time: record the access date beside each file when acquired, and the pipeline
stamps it into coverage output. CI never touches the network.

| # | Source | What it provides | Acquisition | Status |
|---|---|---|---|---|
| D1 | Public Schools and Districts directory (`pubschls.txt`), https://www.cde.ca.gov/schooldirectory/ (download: text report) | Canonical school list: CDS codes, names, districts, status, type, grades, coordinates, charter/virtual flags | Browser download, ~8.8 MB tab-delimited | Endpoint verified live 2026-08-07 (HEAD 200, text/csv, 8,788,547 bytes); parser built |
| D2 | Census Day Enrollment Data, https://www.cde.ca.gov/ds/ad/filesenrcensus.asp (file structure: https://www.cde.ca.gov/ds/ad/fsenrcensus.asp; the pre-2026 URL filesenr.asp now 404s, renamed upstream, observed 2026-08-07) | Enrollment by school, grade, demographic group | Browser download, annual. Acquire from the browser page and record which school year's file was taken | 2025-26 file acquired 2026-08-07, saved as `cdenroll2526.txt` (32,041,859 bytes, 269,090 data rows); parser built; ReportingCategory names reviewed against the file structure page 2026-08-07 |
| D3 | Chronic absenteeism files, https://www.cde.ca.gov/ds/ad/filesabd.asp (verify URL at acquisition; CDE renamed sibling pages in 2026) | Chronic absenteeism rate by school and group, with CDE small-cell masking | Browser download, annual | Planned |
| D4 | CA School Dashboard research files, https://www.cde.ca.gov/ta/ac/cm/ | Dashboard indicator data behind the color bands | Browser download, annual | Planned |
| D5 | Teacher Assignment Monitoring Outcome files, https://www.cde.ca.gov/ds/ad/filestamo.asp (verify the URL and the file structure page it links at acquisition; CDE renamed sibling pages in 2026, as the D2 row records). CDE publishes these from the Commission on Teacher Credentialing's CalSAAS system | By school: teaching assignments held on a clear credential and appropriately assigned, and the other authorization states the state tracks, with CDE small-cell masking | Browser download, annual. Record which school year's file was taken; it reports on a different cycle than D2 | **Parser built, awaiting acquisition.** No D5 file has been acquired and no D5 number about a real school has been published. The parser was written against `fixtures/tamo.sample.txt`, a synthetic fixture built from what these files are documented to report and from the conventions of CDE's sibling downloadable files verified at D2 (aggregate-level rows, split county/district/school codes, `*` masking). The column names in `src/homeroom/assignments.py` were not read off CDE's file structure page and are provisional: check them there at acquisition. Getting them wrong stops the build rather than mis-reads the file |
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
