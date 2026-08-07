# Provenance

Every source is a California Department of Education public file. CDE's site challenges
non-browser HTTP clients (Radware-style bot manager, observed 2026-08-07), so acquisition
is a documented browser step, not an automated fetch. Record the access date beside each
file when acquired; the pipeline stamps it into coverage output.

| # | Source | What it provides | Acquisition | Status |
|---|---|---|---|---|
| D1 | Public Schools and Districts directory (`pubschls.txt`), https://www.cde.ca.gov/schooldirectory/ (download: text report) | Canonical school list: CDS codes, names, districts, status, type, grades, coordinates, charter/virtual flags | Browser download, ~8.8 MB tab-delimited | Endpoint verified live 2026-08-07 (HEAD 200, text/csv, 8,788,547 bytes); parser built |
| D2 | Census Day enrollment files, https://www.cde.ca.gov/ds/ad/filesenr.asp | Enrollment by school, grade, demographic group | Browser download, annual. Note 2026-08-07: direct www3.cde.ca.gov/demo-downloads URLs return 303 to an HTML page for non-browser clients; acquire from the browser page and record which school year's file was taken | Awaiting first acquisition |
| D3 | Chronic absenteeism files, https://www.cde.ca.gov/ds/ad/filesabd.asp | Chronic absenteeism rate by school and group, with CDE small-cell masking | Browser download, annual | Planned |
| D4 | CA School Dashboard research files, https://www.cde.ca.gov/ta/ac/cm/ | Dashboard indicator data behind the color bands | Browser download, annual | Planned |
| D5 | Teacher Assignment Monitoring (CalSAAS) outcomes | Clear/appropriately-assigned teaching share by school | Browser download, annual | Planned |
| D6 | Per-pupil expenditure (SACS/LCFF public files) | School-level spending where published | Browser download, annual | Planned |

Rules:

- CDS code (14-digit county-district-school) is the only join key. Names are display-only.
- CDE masks small cells (published as `*`). A masked cell is `null` in every artifact and
  is counted in coverage output. It is never zero.
- No third-party or commercial data (no ratings sites, no real-estate feeds). If CDE does
  not publish it, Homeroom does not show it.
