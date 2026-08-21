# Suppression showcase: null-never-zero, from a real file to a real page

Committed per `docs/ROADMAP.md` M3's acceptance criteria: "a committed artifact
demonstrating null-never-zero rendering... coverage stats published beside the
data." This is not a test; it is the same claim the test suite enforces, made
inspectable by someone who does not read Python. Every figure below is copied
from `chronicabsenteeism25.txt` (the 2024-25 Chronic Absenteeism file, acquired
2026-08-21; PROVENANCE.md D3), read with `errors="replace"` the way
`src/homeroom/absenteeism.py` reads it, on 2026-08-21. Nothing here is invented,
rounded, or estimated.

## The rule

CDE's chronic absenteeism file states three possible facts about one school and
one student group: a number it measured and published, a number it measured and
withheld because the group is small enough to risk identifying a student (`*`),
or nothing published at all (the row does not exist). Homeroom's whole honesty
argument is that a page must keep these apart, all the way from the source file
to the pixels, and a fourth fact -- the state published a genuine zero, and that
is different again from either kind of absence -- must survive alongside them.

## Four real rows, one real school

Birch Lane Elementary, Davis Joint Unified (CDS `57726786056246`), the same
school `docs/ROADMAP.md` M4 renders end to end. Four of its rows in the acquired
file, verbatim:

| Reporting Category | `ChronicAbsenteeismEligibleCumulativeEnrollment` | `ChronicAbsenteeismCount` | `ChronicAbsenteeismRate` |
|---|---|---|---|
| `RA` (Asian) | `96` | `12` | `12.5` |
| `RF` (Filipino) | `*` | `*` | `*` |
| `SF` (Foster youth) | *(no row for this school and category exists in the file)* | | |
| `TA`, a different school (Table Mountain, Butte County Office of Education, CDS `04100410430066`) | `26` | `0` | `0.0` |

Table Mountain stands in for the fourth case because Birch Lane's own `TA` rate
(16.9%) is a published non-zero; a genuine published zero needed a second real
school, found by scanning the acquired file for a `TA` row reading exactly `0.0`,
not by editing Birch Lane's own numbers.

## What each one becomes, end to end

### Reported: Asian, 12.5%

`homeroom.measures.parse_cell` reads `"12.5"`, matches `PUBLISHED_NUMBER`, and
returns `Measure.reported(12.5)`.

`schools.json` (`homeroom.artifacts.measure_json`):

```json
{"status": "reported", "value": 12.5}
```

The rendered cell (`homeroom.render._measure_cell`):

```html
<td class="m c-school m-number"><span class="num">12.5%</span></td>
```

### Withheld: Filipino, `*`

`parse_cell` reads `"*"`, matches `SUPPRESSION_MARK`, and returns
`Measure.suppressed()`. `Measure.number()` raises `SuppressedValueError` if
anything ever tries to read a value out of it -- there is no numeric path for
this state to leak through.

`schools.json`:

```json
{"status": "suppressed"}
```

No `"value"` key exists. A consumer of this JSON cannot recover a number that
was never written, which is the artifact-level form of the same rule.

The rendered cell:

```html
<td class="m c-school m-withheld"><span class="state">withheld to protect privacy</span></td>
```

No digit appears anywhere in that markup. `tests/test_pages.py` asserts this for
every `m-withheld` cell on every built page, and
`tests/test_absenteeism.py::test_masked_row_masks_all_three_cells_never_zero`
pins it at the parser.

### Not reported: Foster youth

The category never appears for this CDS in the file at all. Profile assembly
(`homeroom.profiles._profile`) never invented a row for it: the dictionary
lookup falls through and the profile carries `Measure.not_reported()`.

`schools.json`:

```json
{"status": "not_reported"}
```

Byte-identical shape to the withheld case -- no `"value"` key either -- but a
different `"status"`, because "the state measured this and would not tell us"
and "the state never measured this" are different facts, not the same absence
twice.

The rendered cell:

```html
<td class="m c-school m-nothing"><span class="state">no figure published</span></td>
```

### Reported zero: Table Mountain, 0.0%

`parse_cell` reads `"0.0"`, matches `PUBLISHED_NUMBER`, and returns
`Measure.reported(0.0)`. `Measure.is_zero` is `True` and `Measure.status` is
`REPORTED` -- the same status as the 12.5% case above, which is exactly why the
page must say "reported as zero" in words rather than trusting a reader to
notice the digit `0` is not a dash.

`schools.json`:

```json
{"status": "reported", "value": 0}
```

The rendered cell:

```html
<td class="m c-school m-zero"><span class="num">0.0%</span> <span class="state">reported as zero</span></td>
```

## The scale this matters at

Measured by running `homeroom.artifacts` against the acquired D1, D2 and D3
files together (`make data`, 2026-08-21), across all 10,534 active schools:

| Chronic absenteeism, total rate (`TA`) | Count |
|---|---|
| Published (reported, including genuine zeros) | 9,718 |
| Withheld (`*`, small-cell suppression) | 83 |
| Not published (no row for this school) | 733 |

Some subgroup categories are withheld far more often than the total rate, because
a small subgroup crosses CDE's small-cell threshold long before the whole school
does. Among the 9,801 schools that publish any row for a given category:

| Category | Published | Withheld | Withheld, of schools with any row |
|---|---|---|---|
| `RI` (American Indian or Alaska Native) | 451 | 9,350 | 95.4% |
| `RP` (Pacific Islander) | 528 | 9,273 | 94.6% |
| `RF` (Filipino) | 2,908 | 6,893 | 70.3% |
| `RD` (race or ethnicity not reported) | 1,995 | 7,806 | 79.7% |
| `RB` (African American) | 4,864 | 4,937 | 50.4% |
| `TA` (all students) | 9,718 | 83 | 0.8% |

The full breakdown for every category, subgroup and join gap is in
`coverage.json`'s `measures.chronic_absenteeism` block, regenerated by
`make data` and never hand-edited.

For a family reading a real page, this is the argument in its strongest form:
the smaller the group, the more likely CDE withheld its figure, and the more it
matters that "withheld" never quietly becomes a zero on the page -- because for
several of these groups, a zero would be the *majority* rendering of a real
school's real (but unpublished) chronic absenteeism rate for that group, not an
edge case.

## Where this is enforced, if you do want to read the tests

- `src/homeroom/measures.py` -- the type that makes a masked value unreadable.
- `src/homeroom/absenteeism.py` -- the D3 parser, verified against the acquired
  file (module docstring).
- `src/homeroom/profiles.py` -- `_absenteeism_rows` / `_profile`, the join that
  never invents a row.
- `src/homeroom/artifacts.py` -- `measure_json`, `_absenteeism_coverage`.
- `src/homeroom/render.py` -- `_measure_cell`, `_absenteeism_section`.
- `tests/test_absenteeism.py`, `tests/test_profiles.py`, `tests/test_artifacts.py`,
  `tests/test_pages.py` -- each layer's own drift and null-never-zero tests.
