"""Parse CDE's public school directory (`pubschls.txt`), the spine of everything.

Every other dataset joins against this file by CDS code, the 14-digit
county-district-school identifier. The parser reads the header row and addresses
columns by name, so a column added or reordered upstream cannot silently shift
fields; a column this module depends on going missing is a hard failure, not a
guess. Source: PROVENANCE.md D1.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = (
    "CDSCode",
    "StatusType",
    "County",
    "District",
    "School",
    "City",
    "Charter",
    "Virtual",
    "GSserved",
)
"""Columns this project reads today. Absence of any is upstream drift and fails the build."""

ACTIVE_STATUS = "Active"


@dataclass(frozen=True)
class School:
    cds_code: str
    name: str
    district: str
    county: str
    city: str
    status: str
    charter: bool
    virtual_code: str
    grades_served: str

    @property
    def active(self) -> bool:
        return self.status == ACTIVE_STATUS


class DirectoryDriftError(ValueError):
    """The upstream file no longer matches the layout this parser was verified against."""


def _clean(value: str | None) -> str:
    text = (value or "").strip()
    # CDE uses "No Data" as an explicit placeholder in several columns.
    return "" if text == "No Data" else text


def parse_directory(path: Path) -> Iterator[School]:
    """Yield each school row. Rows without a school name are district/county offices
    present in the same file; they are yielded too (status and name make them
    distinguishable) because pretending the file holds only schools would be a lie
    about the source."""
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise DirectoryDriftError(
                f"{path.name} is missing required columns {missing}; "
                "the upstream layout changed and must be re-verified before parsing"
            )
        for row in reader:
            cds = _clean(row.get("CDSCode"))
            if not cds:
                continue
            if len(cds) != 14 or not cds.isdigit():
                raise DirectoryDriftError(
                    f"{path.name}: CDS code {cds!r} is not 14 digits; refusing to join on it"
                )
            yield School(
                cds_code=cds,
                name=_clean(row.get("School")),
                district=_clean(row.get("District")),
                county=_clean(row.get("County")),
                city=_clean(row.get("City")),
                status=_clean(row.get("StatusType")),
                charter=_clean(row.get("Charter")) == "Y",
                virtual_code=_clean(row.get("Virtual")),
                grades_served=_clean(row.get("GSserved")),
            )


def active_schools(path: Path) -> list[School]:
    """Active entries that are actual schools (a school name is present)."""
    return [s for s in parse_directory(path) if s.active and s.name]
