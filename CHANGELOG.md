# Changelog

All notable changes to `table2rules` are documented here. Dates are in
`YYYY-MM-DD`. This project follows semantic versioning.

## [Unreleased]

### Fixed

- **Label-only row-group headers are now threaded across columns** (multi-column
  matrix variant). A label-only band groups a *row range*, but 0.6.1 only reached
  it from the value cell's own column and the row-label columns. When a group
  header sits in a leading stub / line-number column while the sub-rows leave
  that column empty and carry their identity in a different column (a numbered
  schedule with `plan × cover` value columns), the band was unreachable — so the
  header was **dropped entirely** rather than threaded. The maze now scans all
  columns for label-only bands (full-width and source `scope="rowgroup"` bands
  keep the column-restricted scan, so unrelated stub dividers don't cross-attach),
  and each group's extent still closes at the next group:

  ```
  10. Travel Delay > Adult under 70 | PLANS > BASIC: 100
  ```

  This also recovers data in three real-world corpus tables (`pubtabnet-180372`,
  `-357665`, `-374857`) whose year / cohort group headers — in a stub column the
  data rows leave empty — were silently dropped in 0.6.1. New fixture
  `matrix/label-only-rowgroup-stub-column`.

## [0.6.1] — 2026-06-14

### Fixed

- **Label-only rows are now threaded as row-group headers.** 0.6.0's row-group
  threading only handled the *full-width band* form (a cell spanning the value
  region / `scope="rowgroup"`). The **label-only-row** form — a body row whose
  value columns are empty while a single leading label cell carries text
  (`9. Trip Cancellation | (empty) | (empty)`), pervasive in `Label | Value`
  financial/insurance schedules — was missed: it was emitted as an orphaned
  `is_label` rule and the values beneath it lost their group identity. Such a
  row is now promoted to a row-group ancestor and threaded into every value line
  under it, until the next label-only row at the same level:

  ```
  10. Travel Delay > If the departure is delayed > 1. Adult insured person | Maximum limit (S$) > Value Plan: 100
  ```

  Detection stays geometric and additive to the existing band path:
  - A row with no value-bearing `<td>` but exactly **one** non-empty label
    source cell is a group header. Consecutive label-only rows nest in order
    (a title followed by a description), and the two forms compose — a
    full-width section band and a label-only group nest consistently.
  - The **single-label-cell** requirement separates a group header from a data
    row whose designated value columns merely happen to be empty: a summary row
    spreading several values across its label cells (`Total | n=4`, or a row
    under a header that over-promoted numeric columns to row labels) keeps the
    `is_label` preservation path, so its cells are never invented into a
    breadcrumb and misattributed onto the rows below.
  - A trailing label-only row with no value rows beneath it stays a label
    (parity with the full-width-note guard) — no empty group is created.

## [0.6.0] — 2026-06-11

### Added

- **Hierarchical row-groups are threaded into every value line, symmetric with
  the multi-level column header path.** Previously rules-mode fully qualified
  the *column* side of each value (`… | A > B > C: value`) but dropped the *row*
  hierarchy — section bands, group headers, and the data-row label were emitted
  as separate, indistinguishable lines, and value lines carried none of that
  row context. A consumer feeding the text to an LLM had to reconstruct "which
  group / which sub-class does this value belong to" by stateful inference
  across lines, which is non-deterministic. Now each value line carries its full
  row path, so one line maps to exactly one record:

  ```
  1. PERSONAL ACCIDENT > Accidental death and permanent disability > 1 > Each adult insured person under 70 | MAXIMUM LIMIT OF BENEFIT (S$) > VALUE PLAN > INDIVIDUAL COVER: 150,000
  ```

  Detection is geometric and honors explicit markup:
  - A value-region-wide body cell (`is_full_width_note` geometry — reaches the
    last column, spans a majority) is a **row-group band**: a full-width section
    band, or a group header / description spanning the value region. It is
    promoted to `scope="rowgroup"` and threaded as a bounded ancestor of the
    rows it groups. **Nested** bands are bounded by colspan — a band's extent
    ends at the next band of equal-or-wider span — so an inner group header does
    not close an outer section band. Source cells already marked
    `scope="rowgroup"` are honored as-is.
  - The maze walks the data cell's **own column** (which a value-region-wide
    band spans) in addition to the row-label columns, so a band is found even
    when the row's label cell is empty — fixing the case where a group's
    unlabeled continuation row previously lost its band entirely.
  - Columns under the leftmost top-level header group (the row-label / stub
    dimension, e.g. a `SECTION` header spanning the rownum and person-class
    columns beside a separate value-header group) are threaded as row labels
    even though they carry header text, so the row identity — not just the
    leading number — appears on each value line.

  Guards keep it faithful: a band is promoted only when its extent contains a
  real data row (so a standalone trailing note is left as a note, never
  stranded), and a full-width body cell that merely repeats a column header (a
  units caption like "(In thousands…)" reprinted between sections) is not
  treated as a band. Existing `scope="rowgroup"` tables (e.g. FinTabNet year
  bands) are unchanged. New fixtures `matrix/rowgroup-nested-bands`,
  `matrix/full-width-note-colspan`, `matrix/section-divider-td-colspan`.

## [0.5.2] — 2026-06-09

### Fixed

- **Full-width descriptive `<td colspan>` cells no longer replicate across every
  value column.** In a plan×cover benefit matrix, a row shaped
  `<td>marker</td><td colspan="7">description…</td>` is a full-width note, not a
  per-column value. The per-position expansion in `_build_rules` was emitting it
  once per spanned column, each stamped with that column's header — so a single
  benefit description ("If the departure of your public transport is delayed…")
  became the value of six unrelated plan×cover cells. A data cell that reaches
  the last column and spans a majority of the grid's columns
  (`spans.is_full_width_note`) is now attributed to its origin column's header at
  every spanned position, and the exporter's origin-aware dedup collapses it to a
  single line. The cell is still emitted at every position, so an overlapping-span
  corruption (a rowspan intruding into the note's row) is still detected by the
  gate and fails open to flat. Legitimate narrow spans (a right-edge `colspan=2`
  amount covering two sub-columns of one group) keep their per-column fan-out.
  New fixture `matrix/full-width-note-colspan`.

- **Body section dividers no longer bleed onto every row as fabricated column
  headers.** A single full-width `<td colspan="N">` divider (e.g. a benefits
  schedule `1. PERSONAL ACCIDENT` row) expands to N non-empty logical positions,
  so the colspan-expanded cell count read it as a full header row —
  `detect_header_block` swept the first divider *and* the body rows between it and
  the first clean data row into the `<thead>`, and they then bled onto every line
  as column headers (observed on a 100-row matrix: a benefit name attached to 474
  of 478 output lines, including unrelated sections). The header now ends at the
  first of a *series* (≥ 2) of full-width single-cell dividers — distinguishing
  body section dividers from a one-off header subtitle like "(Dollars in
  thousands)". Such dividers stay in the body and render once as full-width notes;
  Fix 8 no longer promotes a single full-width cell to `<th scope="row">` (which
  stranded it, since it has no value column to anchor a rule). New fixture
  `matrix/section-divider-td-colspan`.

- All `mypy` errors in `src/table2rules` resolved (`find_all("table")` result
  narrowed to `Tag` before use).

## [0.5.1] — 2026-06-06

### Fixed

- **De-spanned section headers are preserved instead of dropped.** A body row
  whose row-label is present but which carries no independent value — the shape
  a full-width section title takes after an OCR/HTML pipeline drops its
  `colspan` — used to vanish entirely, silently losing the label and leaving
  repeated sub-item rows (`Each child insured person`) context-less.
  `_build_rules` now emits a label-only rule for such rows, preserving the text
  verbatim. The label is kept as-is rather than reconstructed into a section
  breadcrumb, because such a row is structurally indistinguishable from a leaf
  row with a genuinely missing value. Two encodings are covered:
  - **Empty value column** — e.g. a benefits-schedule `1. Accidental death …`
    row, or a balance-sheet `Current assets:` / FinTabNet `Segments:` label.
  - **Value echoes the column header** — e.g. a `24. COVID-19 Coverage
    Extension | Sum Insured` row. The echoed `Sum Insured` value is a
    self-echo that `clean_rules` strips; previously that took the section
    label down with it. The row is now recognised as label-only first, so the
    label survives while the redundant echo is still dropped.

  A `LogicRule.is_label` flag marks these rows; the confidence gate treats them
  as pass-through (excluded from header-attachment and coverage scoring) so a
  table does not degrade to flat output merely for carrying them. New fixture
  `relational/despanned-section-headers` exercises both encodings. Recovers
  previously-dropped labels across the real-world corpus.

### Changed

- **The real-world corpus is now byte-checked in CI.** `test_regression_golds`
  previously skipped `tests/realworld/`, leaving 401 benchmark golds with
  nothing asserting them — two had silently drifted out of sync with the code.
  All real-world golds are now frozen and byte-compared alongside the
  hand-authored fixtures. The correctness/robustness oracles still assert the
  output is *right*; the golds now assert it does not *change* unless a human
  regenerates them, which is what makes a silent-drop regression visible.
  `scripts/benchmark.py` no longer emits stray golds for top-level `*.md`
  (README, scratch files), keeping `--update-gold` in lockstep with the test.

## [0.5.0] — 2026-05-06

### Added

- Two universal structural witnesses extend `simple_repair.detect_header_block`
  so headless tables whose row 0 was previously misclassified as data now
  promote correctly to a header block:
  - **Fuller-than-body.** Row 0 is disqualified as a clean data row when its
    non-empty cell count is strictly greater than the minimum non-empty
    count of the non-divider rows below it AND every column row 0 fills is
    covered by at least one body row. Catches headerless tables with
    implicit-rowspan group-label columns (a leading column repeated at
    group starts and left empty in continuation rows), multi-stub
    indentation pyramids (one of several leading columns filled per row by
    hierarchy level), and alternating coefficient/std-error layouts. The
    body-coverage clause excludes receipts whose row 0 is a wider line
    item over narrower totals — there the body never uses row 0's extra
    columns.
  - **Cell-type inversion.** Row 0 is disqualified when it contains at
    least one corner-stub `<td>` (where the body majority is `<th>`) and a
    strict majority of compared columns have row 0's cell tag inverted
    versus the body majority. Catches header rows authored as
    `[td, th, th]` above body rows `[th, td, td]`. The corner-stub
    requirement is load-bearing: an all-`<th>` row above an all-`<td>`
    body would also "invert" every column, but Fix 7 already wraps that
    case in `<thead>` via the contiguous-`<th>` chain.
- Both witnesses apply only at row 0 — beyond the first row, "fuller than
  the body below" and "cell tags differ from body majority" describe normal
  body geometry, not a header.
- Fixtures
  `tests/fixtures/relational/headerless-{corner-stub-inversion,implicit-rowspan-group,stub-pyramid}.md`
  exercise the three new patterns.

## [0.4.1] — 2026-04-30

### Fixed

- `extract_cell_text` now skips text nodes whose direct parent is a `<style>`
  or `<script>` tag. Wikipedia multi-column list templates inject inline
  `<style>` blocks directly inside `<td>` cells; previously the raw CSS leaked
  into emitted rule values while the quality gate still reported
  `mode=rules, score=1.00` — a silent failure invisible to callers.

## [0.4.0] — 2026-04-29

Header detection reframed as a set of universal structural rules, and
the Layer-2 / Layer-3 real-world corpus doubled to add IBM 10-K
financial tables (FinTabNet). Combined, the rules unlock rules-format
output for **199 of 200 FinTabNet fixtures** (up from 0 with the
previous "all row-0 cells non-empty" heuristic) while leaving
PubTabNet's 170/200 pass count unchanged.

### Structural rule — header-block detection (replaces Fix 4's
row-0-only heuristic)

A new deterministic rule in `simple_repair.detect_header_block` picks
the header block via two geometric definitions:

- **Clean data row.** A row where every logical position is an origin
  cell at this row (no rowspan copy from above) with
  `rowspan == colspan == 1` and non-empty text. The first such row
  (with col 0 non-empty) marks the header/body boundary.
- **Row-stub column.** A column empty in every non-divider header row
  AND non-empty in every non-divider body row. The conjunction is
  load-bearing: neither condition alone distinguishes a stub from a
  missing group-header cell (where a top-level group doesn't span a
  later column) or an always-populated data column.

A leading row is header-compatible iff every empty cell in it lies in
a row-stub column. This subsumes three previously disjoint cases:

- **Dense first-row headers** (receipts, simple relational): row 0 is
  a clean data row with no empties, so the stub-col condition is
  trivially satisfied. Old Fix 4's "row 0 all non-empty + body has
  empties" special-case collapses into the same rule.
- **Multi-row headers with colspan group labels** (FinTabNet
  hierarchical, benefits-style matrix): header rows carry colspan > 1
  cells and are not themselves clean data rows, so the detection
  naturally extends through them to the first plain body row.
- **Financial 10-K tables with empty row-stub labels** (FinTabNet
  single-row headers): col 0 is structurally identified as a stub
  column; the empty col-0 cell in row 0 is now permitted as the
  row-stub-column signature rather than disqualifying.

Body cells in stub columns are promoted to `<th scope="row">`
directly, generalizing Fix 8's rowspan-based dimensional-column
promotion to also cover single-row-header tables.

### Additional invariants

- **Row-group divider propagation (new).** A body row whose single
  non-empty logical cell sits in a stub column is structurally a
  row-group header for the rows that follow. Fix 4 now promotes that
  cell to `<th scope="rowgroup">`, and `maze_pathfinder` walks up the
  stub column to include it in `row_path` — *but only within its
  extent*. Explicit `rowspan > 1` uses the rowspan range; divider
  rows with `rowspan == 1` run until the next rowgroup origin in the
  same column. This captures the FinTabNet year-label pattern
  ("2014" row between Q1–Q4 blocks) without mis-nesting explicit
  rowgroup peers like "North" / "South" with `rowspan="2"` each.

- **Stub-column rule uses strict-majority count (refined).** The
  earlier rule required a stub column to be non-empty in *every*
  non-divider body row. That rejected tables with an unlabeled
  trailing summary row (a FinTabNet pattern where the totals line
  leaves the row-label cell blank: `— | $1,573,043 | ...`). Fix 4
  now accepts a column as a stub when it is non-empty in strictly
  more body rows than it is empty in — still a deterministic integer
  comparison, still refuses to promote sparsely-filled data columns.

- **`first_data_idx` anchor relaxed (refined).** The earlier anchor
  required the first data row to have every cell non-empty. That
  rejected tables whose body rows are inherently gappy (a column
  that only fills on certain events — e.g., an aggregate fair-value
  column that has a value only when shares vest). The anchor now
  requires col 0 non-empty, ≥ 2 non-empty logical cells, and no span
  structure — the remaining conditions still separate body rows from
  header rows, since header rows carry either an empty col 0 or a
  span marker.

- **Column-header detection ignores `<th scope="row">`.** `grid_parser`
  Step 1 previously accepted any `<th>`-or-empty row as the primary
  column-header row, including rows where Fix 5 had promoted a "Total"
  label to `<th scope="row">`. That misidentification caused
  mid-table summary rows to be treated as headers, producing
  fabricated column paths. Now Step 1 requires `<th>` cells without
  `scope="row"`.

- **Fix 8's `active_rowspan` counter tracks pre-promoted `<th>` cells.**
  When Fix 4 has already promoted the first-column cell via the
  stub-column path, Fix 8 still needs to track its rowspan so
  subsequent rows aren't mistaken for first-column content. The
  counter was previously only updated inside Fix 8's promotion branch,
  leaving it stuck at 0 when the cell was already `<th>` — which in
  turn over-promoted data cells at logical col > 0 to row-stub status.

### Corpus

- **FinTabNet oracle corpus (200 fixtures)**: pulled from
  `apoidea/fintabnet-html` via
  [scripts/build_fintabnet_fixtures.py](../scripts/build_fintabnet_fixtures.py).
  With the five structural invariants in place, 199/200 fixtures
  produce rules-format output that oracle-matches. The single remaining
  flat-fallback case uses footnote-marker separator columns — an
  unusual layout pattern where narrow unlabeled columns sit between
  dollar-amount columns to hold footnote references.

- **Regression golds updated**: two matrix fixtures
  (`conflicting-spans-scope`, `scope-rowgroup-colgroup`) had captured
  the pre-existing Fix 8 bug. Updated golds reflect the corrected
  output where a numeric data cell at logical col > 0 in a row whose
  col 0 is covered by an above rowspan is no longer misclassified as
  a row-subheader.

### Quality gate

- **New gate reason `partial_column_coverage`.** Detects when column
  headers cover some rules in a table but not others — the silent
  label-shift failure mode where a multi-level header omits a slot
  for the row-label column, shifting every column label one position
  right and leaving the rightmost data column unlabeled. Tables that
  hit this case now fall back to flat rendering with the reason
  surfaced in `TableReport`, instead of emitting wrong facts at full
  confidence. Contributed by @BeastxD7 in
  [#2](https://github.com/PebbleRoad/table2rules/pull/2).

### Public API additions

- **`TableReport.text`** — the rendered output for *this table only*,
  the same lines that contribute to the concatenated string returned
  alongside the report. Lets callers passing whole-document HTML keep
  per-table provenance without having to split the flat blob
  themselves.
- **`TableReport.caption`** — text of the table's `<caption>` element
  when present, otherwise `None`. Only direct `<caption>` children
  are read; surrounding headings and `id` attributes are intentionally
  ignored — `table_index` remains the only stable positional
  identifier.

## [0.3.0] — 2026-04-23

Three structural invariants tighten when the parser emits rules-format
output, closing a cluster of bugs where non-genuine table types
(enumeration, navigation, form-layout, sectioned A/V) silently produced
fabricated rules. Also broadens the fixture corpus along the Crestan &
Pantel semantic taxonomy and adds 10 financial-table fixtures for
FinTabNet-style idioms.

**Behavior change:** some inputs that previously emitted rules-format
output now correctly degrade to flat mode. If you were consuming the old
rules output on these inputs, expect different string output. See the
invariants below to predict which inputs are affected.

### Structural invariants enforced

Three deterministic, universal rules — no thresholds, no content
inspection, only markup properties:

1. **Row-0 promotion requires structural contrast.** `simple_repair.Fix 4`
   and `grid_parser` step 3 previously converted row 0's `<td>`s to `<th>`
   whenever all cells were non-empty. Now require at least one subsequent
   multi-cell row to have at least one empty cell — a real header
   uniquely labels every column, so structural contrast with sparse data
   rows is the signal. Uniform lists (glossaries, country enumerations,
   checkbox grids) no longer get row 0 fabricated into a header.
2. **Rules mode requires every rule to carry at least one header.** The
   `low_header_attachment` gate check previously fired only at
   `header_ratio < 0.25`. Now fires universally at `header_ratio < 1.0`
   — a rule with zero headers is indistinguishable from flat text.
   Mixed-header tables (bare data rows interleaved with labeled summary
   rows) now route to flat mode instead of producing visually incoherent
   hybrids.
3. **Section-title rows are not header rows.** A `<tr>` whose sole cell
   is a `<th>` with colspan covering the grid width is a section label,
   not a header or data row. `simple_repair.Fix 1` already moved the
   first-row instance to `<caption>`; new `Fix 1b` decomposes mid-table
   instances so span-expanded section labels don't get fabricated into
   column headers for subsequent rows.

### Added

- **Shape heuristics (`numeric_column_headers`, `placeholder_column_headers`)
  now trust source-authored `<thead>`.** Previously, the gate fired on
  any table where rules' column headers were entirely numeric — rejecting
  legitimate financial tables with year columns like
  `<thead><tr><th>2024</th><th>2023</th></tr></thead>`. The checks now
  skip when any grid cell was placed inside a `<thead>` by the source.
  Inferred headers are still subject to the shape checks.
- **Fixture taxonomy under
  [`tests/fixtures/`](tests/fixtures/)** organized by Crestan & Pantel
  (WSDM 2011) semantic class: `relational/`, `matrix/`,
  `attribute-value/`, `listing/`, `form/`, `enumeration/`,
  `navigational/`, `formatting/`, plus `multi-table/` (meta). Filenames
  now capture the parser-stress quirk being exercised
  (`malformed-nesting`, `tfoot-before-tbody`, etc.); no more `evilN-`
  prefixes. 13 new fixtures close coverage gaps on A/V, listing, form,
  enumeration, navigational, and formatting classes.
- **10 FinTabNet-pattern fixtures** under `tests/fixtures/matrix/`
  exercising financial-reporting idioms: parenthesized negatives,
  footnote markers in headers and data, em-dash placeholders, multi-year
  column groups, `Year Ended December 31,` nested headers, `&nbsp;`
  indented row labels, interspersed group totals, `<br>` inside
  headers, mixed currency symbols, 3-level nested headers.
- **Structural invariants section** in [`tests/README.md`](tests/README.md)
  citing Crestan & Pantel and documenting the three rules.

### Changed

- **`low_header_attachment` reason** now fires universally (any rule
  with zero headers) rather than at a 25% threshold. The reason code and
  severity bucket are unchanged; the description text was updated. No
  API break.
- **Fixture layout.** Old folders (`tests/{adversarial,headerless,`
  `regression,smoke,structured}/`) removed; all 44 existing fixtures
  moved under `tests/fixtures/<class>/` via `git mv` (history preserved).

### Test status

1,913 pass, 444 skip (oracle/mutation layers skip fixtures that
legitimately don't emit rules). Zero regressions on the 200 PubTabNet
oracle fixtures — none of the three invariants or the `<thead>` trust
change affected a single PubTabNet table (they all have explicit
`<thead>` and well-formed data rows).

## [0.2.0] — 2026-04-21

Observability, safety caps, and a harder public-API contract. The existing
`process_tables_to_text(html)` call site is unchanged; everything here is
either additive or a narrow breaking change to the data model.

### Added

- **`process_tables_with_stats(html, *, format=..., strict=False) -> (str, RenderReport)`** —
  the string output you already had, plus a per-table `TableReport` carrying
  `render_mode`, the quality-gate verdict, reason codes, and any captured
  error message. Use this when you need to tell "rendered cleanly" apart from
  "silently degraded to flat rows."
- **`RenderReport` / `TableReport`** (frozen dataclasses) exported from the
  package root. `RenderReport.merge([...])` concatenates reports across a
  batch of calls.
- **`REASONS: dict[str, str]`** — stable catalogue of every reason code the
  library can emit, with a human-readable description per key. Adding a new
  reason is a minor-version bump; renaming or removing is breaking.
- **`REASONS_BY_SEVERITY: dict[str, frozenset[str]]`** — three-bucket
  grouping (`"defensive"`, `"confidence"`, `"input"`) for building
  exhaustive switches and auto-populated metrics dashboards without
  hardcoding the lists from the docs. Every code in `REASONS` appears in
  exactly one bucket; enforced by tests.
- **`RENDER_MODE_RULES` / `_FLAT` / `_PASSTHROUGH` / `_SKIPPED`** —
  symbolic constants for the four `render_mode` values. Equal to the raw
  strings, so adopting them is a drop-in change.
- **`render_mode`** typed as `Literal["rules", "flat", "passthrough", "skipped"]`.
  `"skipped"` is new — see "Safety caps" below.
- **`Table2RulesError`** / **`TableTooLargeError`** — public exception types
  in a new `table2rules.errors` module, also exported from the package root.
- **`strict=False` kwarg** on both `process_table` and
  `process_tables_with_stats`. When `True`, parse errors and
  `TableTooLargeError` propagate instead of being swallowed. Useful in
  development; keep the default in production.
- **Safety caps on span expansion.** Per-cell `rowspan` / `colspan` is clamped
  to 1000, and any table whose expanded grid would exceed 1,000,000 cells is
  refused with `TableTooLargeError`. Under `strict=False` that surfaces as a
  `TableReport` with `render_mode="skipped"` and
  `reasons=("input_too_large",)` instead of an OOM. Normal tables never
  approach these bounds; the guard exists for adversarial or malformed HTML
  (typical of PDF/scraper pipelines).
- **`py.typed` marker** — the package now exposes inline type information to
  mypy and pyright users downstream.

### Changed

- **`LogicRule` is now frozen and hashable.** Safe to use as a dict key or in
  a set; immutable after construction. This is a soft breaking change for
  anyone who was mutating rule attributes after the fact (nobody should have
  been, but worth flagging).
- **`LogicRule.row_headers` / `col_headers`** are now `Tuple[str, ...]`
  instead of `List[str]`. Reading behaviour (iteration, indexing, `in`) is
  identical; `.append()` and assignment no longer work. If you were
  constructing `LogicRule` directly, pass tuples.
- `LogicRule.to_string()` (the descriptive form on the dataclass itself, not
  the default `rules` exporter) uses `→` between row- and col-header paths.
  The `rules` exporter output is unchanged — still `"<row> | <col>: <val>"`.

### Removed

- **`LogicRule.conditions`** — the compatibility list that duplicated
  `row_headers + col_headers`. The field has been marked for removal since
  well before 0.2.0 and no code in the library read it for routing. If you
  relied on it, use `rule.row_headers + rule.col_headers`.

### Fixed

- **Invalid span values no longer abort the whole table.** `rowspan="foo"`,
  `colspan="-1"`, and `colspan="0"` previously raised inside the parser and
  sent the table down the flat-cell fallback path. With clamping, these are
  coerced to `1` and the table now parses into proper rules. Two adversarial
  fixtures (`evil20-invalid-span-values`, `evil26-kitchen-sink-hostile`) saw
  their gold files updated to reflect the improved output.

### Migration notes

```python
# Before (0.1.x)
from table2rules import process_tables_to_text
text = process_tables_to_text(html)

# After (0.2.0) — the above still works, but for production you want:
from table2rules import process_tables_with_stats, TableTooLargeError

text, report = process_tables_with_stats(html)
for t in report.tables:
    if t.render_mode != "rules":
        logger.warning("table %d degraded to %s: %s",
                       t.table_index, t.render_mode, t.reasons)

# If you were constructing LogicRule by hand, drop `conditions` and pass
# tuples for the header fields:
rule = LogicRule(
    outcome="100",
    position=(0, 0),
    row_headers=("Revenue",),    # was List[str]
    col_headers=("2024", "Q1"),  # was List[str]
)
```

## [0.1.0] — 2026-03-19

Initial public release. HTML tables in, one self-contained rule per line out,
fail-open on hostile markup, pluggable exporters, tested against 200
PubTabNet tables with oracle + mutation layers.
