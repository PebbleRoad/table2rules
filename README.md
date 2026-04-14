# Table2Rules — Maze Pathfinder Approach

## The DNA of Table Parsing

**Tables are mazes. Each cell finds its headers by pathfinding.**

This isn't pattern-matching or table-type detection. It's a universal algorithm based on how HTML tables actually work:

1. **Cells occupy grid positions** (with rowspan/colspan expanding them)
2. **Headers relate to data cells** via spatial relationships (left = row context, above = column context)
3. **Semantic markers** (`<th>`, `<thead>`, `scope`) signal intent

The algorithm **discovers structure** — it doesn't memorize patterns.

### Why This Approach

Table2Rules is built as a structural transformer, not a table-type classifier. It converts HTML tables into a logical grid, resolves header relationships by spatial pathfinding, and emits deterministic rules for downstream systems. When markup is ambiguous or hostile, it fails open and preserves raw HTML instead of inventing structure. This makes outputs more trustworthy for enterprise pipelines and LLM workflows where correctness and traceability matter more than aggressive guessing.

---

## Output Format

Rules express table data in a natural, parseable format:

```
Row Headers → Column Headers: Value
```

**Examples:**
```
January → Revenue: $50,000
North America | Dr. Smith (Boston) → Treatment Outcomes | Drug A | Primary Endpoint | Responders: 67%
Name: John Smith
```

This format:
- ✅ Preserves two-dimensional structure (entity vs attribute)
- ✅ Is trivially parseable (delimiters: `|`, `→`, `:`)
- ✅ Uses semantic names (actual headers, not generic labels)
- ✅ Works for LLM embeddings and schema extraction

---

## Installation

```bash
pip install table2rules
```

Or install from source:

```bash
pip install -e .
```

## Usage

### Python API

```python
from table2rules import process_tables_to_text

html = open("page.html").read()
rules = process_tables_to_text(html)
print(rules)
```

### CLI

```bash
# File in, stdout out
table2rules report.html

# File in, file out
table2rules report.html -o rules.txt

# Pipe
cat report.html | table2rules

# Module form
python3 -m table2rules report.html
```

---

## Architecture

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
│  Phase 4: OUTPUT (_core.py)                                  │
│  ─────────────────────────────────────────────────────────  │
│  • Generate LogicRule for each data cell                    │
│  • Group by row for serialization                           │
│  • Format: Row Headers → Column Headers: Value              │
└─────────────────────────────────────────────────────────────┘
```

---

## The Repair Layer (simple_repair.py)

Real-world HTML is messy. The repair layer fixes common authoring mistakes **before** the pure parser runs.

| Fix | What It Does | Why |
|-----|--------------|-----|
| **Fix Tags** | Normalizes `<td>...</th>` mismatches to `<td>...</td>` | Prevents cell nesting from broken closers |
| **Title → Caption** | Moves full-width first rows to `<caption>` | Prevents title pollution in headers |
| **Wrap `<thead>`** | Wraps leading all-`<th>` rows in `<thead>` | Enables thead/tbody distinction |
| **Promote Row Headers** | Converts first-column `<td>` with rowspan to `<th scope="row">` | Marks row identifiers semantically |
| **Promote Summaries** | Converts "Total", "Subtotal", "Sub Total" cells to `<th>` | Preserves summary row semantics |
| **Move Legends** | Moves footnote/legend rows to `<tfoot>` | Separates metadata from data |

**Key principle:** These are generic rules that apply to **classes** of tables, not specific tables.

---

## The Grid Parser (grid_parser.py)

Transforms HTML's tree structure into a true 2D grid.

**Span Expansion:**
```
Original:                    Expanded Grid:
┌──────────┬─────┐          ┌─────┬─────┬─────┐
│ A        │  B  │          │  A  │  B  │  B  │
│ (rs=2)   │(cs=2)          ├─────┼─────┼─────┤
├──────────┼──┬──┤          │  A  │  C  │  D  │
│          │C │D │          └─────┴─────┴─────┘
└──────────┴──┴──┘
```

**Cell Metadata:**
- `is_thead` — Is this cell in the `<thead>`?
- `is_footer` — Is this cell in the `<tfoot>`?
- `header_depth` — How many rows in the header?
- `is_span_copy` — Is this a copy from rowspan/colspan?
- `origin` — For span copies, points to the original cell

---

## The Maze Pathfinder (maze_pathfinder.py)

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

**Filtering Rules:**
- Skip `<thead>` cells in row header context (they're column headers)
- Skip cells with `scope="col"` or `scope="colgroup"` in row context
- Deduplicate span copies using origin tracking

---

## Files

All core modules live in `src/table2rules/`.

| File | Purpose |
|------|---------|
| `_core.py` | Pipeline orchestration; `process_tables_to_text()` entry point |
| `simple_repair.py` | HTML repair and normalization |
| `grid_parser.py` | Builds 2D logical grid from HTML |
| `maze_pathfinder.py` | Pathfinding algorithm for each cell |
| `quality_gate.py` | Confidence scoring; fail-open gate |
| `cleanup.py` | Post-processing deduplication and filtering |
| `models.py` | `LogicRule` dataclass |
| `__main__.py` | CLI entry point |

---

## Examples

### Key-Value Table
```html
<table>
  <tr><th>Name</th><td>John Smith</td></tr>
  <tr><th>Department</th><td>Engineering</td></tr>
</table>
```
```
Name: John Smith
Department: Engineering
```

### Simple Data Table
```html
<table>
  <thead>
    <tr><th>Product</th><th>Price</th><th>Stock</th></tr>
  </thead>
  <tbody>
    <tr><td>Widget</td><td>$19.99</td><td>150</td></tr>
  </tbody>
</table>
```
```
Product: Widget | Price: $19.99 | Stock: 150
```

### Multi-Level Headers
```html
<table>
  <thead>
    <tr><th rowspan="2">Region</th><th colspan="2">Q1 Sales</th></tr>
    <tr><th>Revenue</th><th>Units</th></tr>
  </thead>
  <tbody>
    <tr><th>North</th><td>$50,000</td><td>500</td></tr>
  </tbody>
</table>
```
```
North → Q1 Sales | Revenue: $50,000
North → Q1 Sales | Units: 500
```

### Complex Hierarchical Table
```html
<table>
  <thead>
    <tr>
      <th rowspan="3">Region</th>
      <th rowspan="3">Unit</th>
      <th colspan="2">Q1</th>
    </tr>
    <tr><th colspan="2">Sales</th></tr>
    <tr><th>Rev</th><th>Cost</th></tr>
  </thead>
  <tbody>
    <tr>
      <th rowspan="2">NA</th>
      <th>East</th>
      <td>100</td><td>80</td>
    </tr>
    <tr><th>West</th><td>120</td><td>90</td></tr>
  </tbody>
</table>
```
```
NA | East → Q1 | Sales | Rev: 100
NA | East → Q1 | Sales | Cost: 80
NA | West → Q1 | Sales | Rev: 120
NA | West → Q1 | Sales | Cost: 90
```

---

## Validation

Tested on increasingly complex tables:

| Table Type | Structure | Result |
|------------|-----------|--------|
| Key-Value | 2 cols, th+td pattern | ✅ `Name: John` |
| Invoice | No thead, implicit headers | ✅ `Item: Widget \| Qty: 2` |
| SLA Report | 2-row thead, colspan | ✅ `High → SLA Met \| Yes: 5` |
| Schedule | 3-row thead, body rowspan | ✅ `AI → Day 1 \| AM: Keynote` |
| Financial | 3-level headers, rowgroups | ✅ `NA \| East → Q1 \| Sales \| Rev: 100` |
| Benefits | Mixed colspan in body | ✅ `Health \| Medical → Level \| Junior: $100` |
| **Clinical Trial** | **4-row thead, 3 regions, 9 sites, 12 columns** | ✅ **100 rules extracted correctly** |

---

## Benchmarking

Use the benchmark runner to compare all test tables against committed expected outputs.

Test corpus is organized by intent:

- `tests/smoke/` — minimal sanity checks
- `tests/structured/` — proper headers, hierarchical, real-world enterprise tables
- `tests/adversarial/` — hostile markup, tag mismatches, OCR artifacts, deep nesting
- `tests/headerless/` — receipts, OCR dumps — flat fallback (no parseable headers)
- `tests/regression/` — targeted bug fixes

```bash
python3 tests/benchmark_tables.py --allow-missing-gold
```

Create or refresh expected outputs:

```bash
python3 tests/benchmark_tables.py --update-gold
```

Compare with unified diffs:

```bash
python3 tests/benchmark_tables.py --show-diff
```

## Safety Contract

This module is designed to be fail-open on hostile table markup:

- Parse and transform well-formed tables deterministically.
- Apply bounded generic repair for common breakage (mismatched tags, missing `<thead>`, summary rows).
- If invariants/confidence fail, passthrough the original table HTML instead of emitting low-confidence rules.

## Limitations

- Output format is deterministic but not guaranteed to match every downstream schema; separators and grouping are optimized for parseability.
- The repair stage is bounded and generic; it does not attempt arbitrary HTML surgery.
- Extremely malformed or ambiguous tables may be passed through as raw HTML by design (fail-open safety).
- Semantic interpretation is intentionally conservative: the system transforms structure, it does not infer business meaning beyond table topology and header scopes.
- Benchmark coverage improves confidence but cannot prove correctness for all possible HTML table encodings.

**Clinical Trial Output (sample):**
```
North America | Dr. Smith (Boston) → Treatment Outcomes | Drug A (Experimental) | Primary Endpoint | Responders: 67%
Europe | Dr. Dubois (Paris) → Treatment Outcomes | Drug A (Experimental) | Primary Endpoint | p-value: <0.001
Asia-Pacific | Dr. Tanaka (Tokyo) → Treatment Outcomes | Placebo (Control) | Secondary Endpoint | 95% CI: [-2.3, 4.7]
Pooled Analysis (All Sites) → Treatment Outcomes | Drug A (Experimental) | Primary Endpoint | Responders: 68%
```

---

## Why This Works

### It's Not Hardcoded

Every fix addresses a **class** of tables:

| Rule | Applies To |
|------|------------|
| First-column `<td>` with rowspan → `<th>` | All tables with row identifiers |
| Skip thead cells in row context | HTML specification |
| Don't merge rows with colspan | All hierarchical headers |

### It's Mathematically Sound

The pathfinder doesn't guess. It follows grid coordinates:
- LEFT = row context (same row, earlier columns)
- UP = column context (same column, earlier rows)

### It Degrades Gracefully

When a table can't be parsed (too small, malformed), the pipeline returns the original HTML. No data is lost.

---

## The Key Insight

> **"You're a data cell dropped in a maze. Walk left to find your row headers. Walk up to find your column headers. That's it."**

No table classification. No pattern matching. No machine learning.

Just the DNA of how tables work.
