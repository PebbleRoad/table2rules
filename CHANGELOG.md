# Changelog

All notable changes to `table2rules` are documented here. Dates are in
`YYYY-MM-DD`. This project follows semantic versioning.

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
