# Architecture

Internal reference for the pipeline. Read this if you're debugging a parse
issue, contributing, or curious how the maze-pathfinder approach is
actually implemented. If you just want to use the library, the
[README](../README.md) and [integration guide](integrating.md) are enough.

## Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                        HTML Table                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: REPAIR (simple_repair.py)                         │
│  ─────────────────────────────────────────────────────────  │
│  • Promote first-column <td> with rowspan to <th>           │
│  • Move title rows to <caption>                             │
│  • Wrap all-<th> rows in <thead>                            │
│  • Promote summary labels (Total, Subtotal)                 │
│  • Move legends/footnotes to <tfoot>                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: GRID EXPANSION (grid_parser.py)                   │
│  ─────────────────────────────────────────────────────────  │
│  • Expand rowspan/colspan into true grid positions          │
│  • Enforce span caps (1000 per cell, 1M total)              │
│  • Mark span copies with origin references                  │
│  • Tag cells: is_thead, is_footer, header_depth             │
│  • Detect key-value tables                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: PATHFINDING (maze_pathfinder.py)                  │
│  ─────────────────────────────────────────────────────────  │
│  For each data cell:                                        │
│  1. Walk LEFT  → collect row headers                        │
│  2. Walk UP    → collect column headers                     │
│  3. Walk UP from row header columns → find header context   │
│  • Deduplicate spans, filter by scope                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: QUALITY GATE + OUTPUT (_core.py + exporters/)     │
│  ─────────────────────────────────────────────────────────  │
│  • Generate LogicRule for each data cell                    │
│  • assess_confidence → gate verdict + reason codes          │
│  • Pluggable exporter turns rules into text lines           │
│  • Default: <row-path> | <col-path>: <value>                │
└─────────────────────────────────────────────────────────────┘
```

## The repair layer (`simple_repair.py`)

Real-world HTML is messy. The repair layer fixes common authoring mistakes
**before** the pure parser runs.

| Fix | What it does | Why |
|-----|--------------|-----|
| Fix tags | Normalizes `<td>...</th>` mismatches to `<td>...</td>` | Prevents cell nesting from broken closers |
| Title → caption | Moves full-width first rows to `<caption>` | Prevents title pollution in headers |
| Wrap `<thead>` | Wraps leading all-`<th>` rows in `<thead>` | Enables thead/tbody distinction |
| Promote row headers | Converts first-column `<td>` with rowspan to `<th scope="row">` | Marks row identifiers semantically |
| Promote summaries | Converts "Total", "Subtotal", "Sub Total" cells to `<th>` | Preserves summary row semantics |
| Move legends | Moves footnote/legend rows to `<tfoot>` | Separates metadata from data |

**Key principle:** these are generic rules that apply to *classes* of
tables, not specific tables.

## The grid parser (`grid_parser.py`)

Transforms HTML's tree structure into a true 2D grid.

**Span expansion:**

```
Original:                    Expanded Grid:
┌──────────┬─────┐          ┌─────┬─────┬─────┐
│ A        │  B  │          │  A  │  B  │  B  │
│ (rs=2)   │(cs=2)          ├─────┼─────┼─────┤
├──────────┼──┬──┤          │  A  │  C  │  D  │
│          │C │D │          └─────┴─────┴─────┘
└──────────┴──┴──┘
```

**Safety caps:**

- Per-cell `rowspan` / `colspan` clamped to 1000
- Expanded grid refused if it would exceed 1,000,000 total cells
  (`TableTooLargeError`)

**Cell metadata attached to each position:**

- `is_thead` — Is this cell in the `<thead>`?
- `is_footer` — Is this cell in the `<tfoot>`?
- `header_depth` — How many rows deep is the header?
- `is_span_copy` — Is this a copy from rowspan/colspan?
- `origin` — For span copies, points to the original cell

## The maze pathfinder (`maze_pathfinder.py`)

Each data cell independently navigates to find its headers.

**Algorithm:**

```
For cell at (row, col):

1. WALK LEFT on same row
   → Collect all <th> cells to the left
   → These are ROW HEADERS (entity context)

2. WALK UP from data column
   → Collect all <th> cells above
   → These are COLUMN HEADERS (attribute context)

3. WALK UP from each row header column
   → Find column headers for the row headers themselves
   → This adds hierarchical context (e.g., "Region" for "North America")
```

**Filtering rules:**

- Skip `<thead>` cells in row header context (they're column headers)
- Skip cells with `scope="col"` or `scope="colgroup"` in row context
- Deduplicate span copies using origin tracking

## Why this approach works

- **It's not hardcoded.** Every repair rule addresses a *class* of tables
  (first-column rowspan, summary labels, all-`<th>` rows), not specific
  shapes.
- **It's mathematically sound.** The pathfinder doesn't guess — it follows
  grid coordinates. LEFT = row context; UP = column context. No machine
  learning, no pattern classification.
- **It degrades gracefully.** When a table can't be parsed cleanly, the
  gate rejects the output and the pipeline falls back to flat rows or raw
  HTML passthrough instead of emitting low-confidence rules. See the
  [integration guide](integrating.md#render-modes-what-each-one-means) for
  operational semantics.

## File map

All core modules live in `src/table2rules/`.

| File | Purpose |
|------|---------|
| `_core.py` | Pipeline orchestration; `process_tables_to_text()` and `process_tables_with_stats()` entry points |
| `simple_repair.py` | HTML repair and normalization |
| `grid_parser.py` | Builds 2D logical grid from HTML; enforces span / grid-size caps |
| `maze_pathfinder.py` | Pathfinding algorithm for each cell |
| `quality_gate.py` | Confidence scoring; fail-open gate |
| `cleanup.py` | Post-processing deduplication and filtering |
| `models.py` | `LogicRule` dataclass (frozen, hashable) |
| `report.py` | `RenderReport` / `TableReport` — per-table observability |
| `errors.py` | Public exception types (`Table2RulesError`, `TableTooLargeError`) |
| `exporters/` | Pluggable output exporters (protocol + registry + built-ins) |
| `__main__.py` | CLI entry point |
