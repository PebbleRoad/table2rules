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

## Why RAG Pipelines Need This

The single largest failure mode for tables in RAG isn't extraction — it's **chunking**. A standard pipeline converts tables to markdown or HTML, then a size-based chunker splits by token count. For any table taller than a chunk, the header row ends up in one chunk and data rows land in others. Retrieval on *"what was Q2 2024 revenue?"* returns `Revenue | 155` without the system knowing `155` belongs to Q2, 2024, or even which metric it measures.

Consider a two-level-header financial table:

```html
<table>
  <thead>
    <tr><th></th><th colspan="2">2024</th><th colspan="2">2023</th></tr>
    <tr><th></th><th>Q1</th><th>Q2</th><th>Q1</th><th>Q2</th></tr>
  </thead>
  <tbody>
    <tr><th>Revenue</th><td>130</td><td>155</td><td>118</td><td>125</td></tr>
    <tr><th>Operating Costs</th><td>55</td><td>60</td><td>48</td><td>52</td></tr>
  </tbody>
</table>
```

**Typical markdown extraction** loses the year/quarter hierarchy (the two header rows collapse, and any table-unaware chunker can split the header off from the data):

```
| | Q1 | Q2 | Q1 | Q2 |
| Revenue | 130 | 155 | 118 | 125 |
| Operating Costs | 55 | 60 | 48 | 52 |
```

**table2rules output** is one self-contained fact per line, with the full header ancestry on every line:

```
Revenue | 2024 > Q1: 130
Revenue | 2024 > Q2: 155
Revenue | 2023 > Q1: 118
Revenue | 2023 > Q2: 125
Operating Costs | 2024 > Q1: 55
Operating Costs | 2024 > Q2: 60
Operating Costs | 2023 > Q1: 48
Operating Costs | 2023 > Q2: 52
```

Three properties this gives your RAG pipeline:

1. **Chunk-safety.** Any chunker (character count, token count, semantic, recursive) can split the output at any line boundary and every chunk stays independently meaningful. No row is ever orphaned from its headers.
2. **Retrieval semantics.** A vector embedding of `Revenue | 2024 > Q2: 155` is far closer to the query *"Q2 2024 revenue"* than an embedding of `Revenue | 155` ever will be. The dimension labels are inside the string that gets embedded.
3. **Traceability at answer time.** The LLM sees the full header path on every fact it reads, so when it answers *"why is this 155?"* it can cite the correct column group unambiguously.

This is why we care about producing rules, not just markdown: rules are the representation tables need to survive a RAG pipeline intact. See [Validation](#validation) for how we stress-test this contract against 200 real PubMed Central tables.

### Where this library fits vs. other tools

- **Unstructured.io, markitdown, docling**: extract tables as markdown/HTML. Excellent at extraction, table2rules-incompatible at chunking without additional work.
- **LlamaParse**: paid, similar intent at a higher level (whole-document parsing).
- **pandas / lxml**: give you structured data, not RAG-ingestible facts.
- **table2rules**: narrow scope — HTML table in, self-contained facts out, fail-open on hostile input. Pair it with any of the above in a pipeline: extract with your tool, pass the table HTML through table2rules before chunking.

### What this buys you on today's stack

Three pressures RAG teams are under right now, and what table2rules does about each:

**1) Token bloat on frontier models.** On 200 real PubTabNet tables, the rules output is a median **27% smaller** than the source HTML (p25–p75: 12%–39% savings, measured with OpenAI's `cl100k_base` tokenizer — see [scripts/measure_token_savings.py](scripts/measure_token_savings.py) to reproduce). It's not free, though: on **16% of tables** — dense ones with long header paths — the rules output actually *grows* by up to 59%, because each data cell carries its full row- and col-header path. That's the deliberate tradeoff: where the representation costs extra tokens, it's preserving the context the HTML would otherwise lose at a chunk boundary.

**2) SLMs getting confused by HTML baggage.** Teams increasingly deploy small models (Phi-3, Qwen 2.5 3B, Llama 3.2) where latency and cost matter more than capability headroom. Smaller models have less attention to spend filtering out structural noise — nested tag hierarchy, attribute clutter, whitespace — before they can reason about content. The rules format strips that to a flat sequence of `row-path | col-path: value` statements with no markup. It's the same simplification a human annotator would produce when transcribing a table into bullet points, and it works identically across model sizes.

**3) No chunk configuration.** Teams typically spend meaningful time tuning how long tables are chunked: recursive-character splitter, token splitter, markdown-header-aware splitter, `"don't split in the middle of a table"` heuristics. With table2rules output, every line is a self-contained fact — **any chunker can split anywhere** without orphaning a row from its headers. The chunking question stops being about tables.

---

## Output Format

The default `rules` exporter emits **one self-contained rule per line** — every line carries the full row-header path and full column-header path, so an LLM never loses context across rows:

```
<row-path> | <col-path>: <value>
```

- `>` joins nested header levels (e.g. `Q1 > Sales > Rev`)
- `|` separates the row-header path from the column-header path
- `:` precedes the value

**Examples:**
```
Name: John Smith
January | Revenue: $50,000
North | Q1 Sales > Revenue: $50,000
NA > East | Q1 > Sales > Rev: 100
```

This format:
- Preserves two-dimensional hierarchy without losing span/nesting structure (unlike Markdown or CSV, which cannot represent complex tables)
- Is trivially parseable (delimiters: `>`, `|`, `:`)
- Is **chunk-safe** — every line is self-contained, so RAG splitters can break anywhere without orphaning rows from their headers
- Is backed by the table-understanding literature (TIDE, ICLR 2025; ASTRA, 2025), which found that full-header-path fact lines beat flat/delimited formats for LLM comprehension on hierarchical tables

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
rules = process_tables_to_text(html)           # default: format="rules"
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

# Pick an exporter
table2rules report.html --format rules

# Module form
python3 -m table2rules report.html
```

### Exporters (pluggable output formats)

Output formatting is pluggable. Built-in: `rules` (default, one fact per line).
Third parties can add custom exporters without forking:

```python
from table2rules import Exporter, register_exporter, process_tables_to_text

class JsonlExporter:
    name = "jsonl"

    def export_rules(self, rules):
        import json
        return [
            json.dumps({
                "row": " > ".join(r.row_headers),
                "col": " > ".join(r.col_headers),
                "value": r.outcome.strip(),
            })
            for r in rules
        ]

    def export_flat(self, cell_rows):
        return [" | ".join(r) for r in cell_rows if any(r)]

register_exporter(JsonlExporter())
print(process_tables_to_text(html, format="jsonl"))
```

List available exporters:

```python
from table2rules import available_exporters
available_exporters()   # -> ['rules']
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
│  Phase 4: OUTPUT (_core.py + exporters/)                     │
│  ─────────────────────────────────────────────────────────  │
│  • Generate LogicRule for each data cell                    │
│  • Pluggable exporter turns rules into text lines           │
│  • Default: <row-path> | <col-path>: <value>                │
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
| `exporters/` | Pluggable output exporters (protocol + registry + built-ins) |
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
Product: Widget
Price: $19.99
Stock: 150
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
North | Q1 Sales > Revenue: $50,000
North | Q1 Sales > Units: 500
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
NA > East | Q1 > Sales > Rev: 100
NA > East | Q1 > Sales > Cost: 80
NA > West | Q1 > Sales > Rev: 120
NA > West | Q1 > Sales > Cost: 90
```

---

## Validation

Tested on increasingly complex tables:

| Table Type | Structure | Result |
|------------|-----------|--------|
| Key-Value | 2 cols, th+td pattern | ✅ `Name: John` |
| Invoice | No thead, implicit headers | ✅ `Widget \| Qty: 2` |
| SLA Report | 2-row thead, colspan | ✅ `High \| SLA Met > Yes: 5` |
| Schedule | 3-row thead, body rowspan | ✅ `AI \| Day 1 > AM: Keynote` |
| Financial | 3-level headers, rowgroups | ✅ `NA > East \| Q1 > Sales > Rev: 100` |
| Benefits | Mixed colspan in body | ✅ `Health > Medical \| Level > Junior: $100` |
| **Clinical Trial** | **4-row thead, 3 regions, 9 sites, 12 columns** | ✅ **100 rules extracted correctly** |

### Real-world corpus

The parser is also stress-tested against a real-world external corpus:

- **200 tables from PubTabNet** (tables extracted from PubMed Central
  scientific articles, CDLA-Permissive-1.0) with per-cell oracle
  matching — the oracle is computed from the source's own structural
  annotations, independent of this parser.
- **~2,000 mutation tests** apply 10 real-world HTML noise patterns on
  top of those 200 tables: `<span>` / `<b>` cell wrappers,
  Word-style `<td><b>Header</b></td>`, paginated duplicate header rows,
  mismatched close tags, NBSP padding, `<br>` inside cells, multi-tbody
  splits, and more.
- Contract: emitted rules either match the oracle exactly, or the
  parser falls back to flat / passthrough. **Never fabricates content.**

See [tests/README.md](tests/README.md) for the three-layer test model
(regression · correctness · robustness) and
[tests/realworld/DATA_SOURCES.md](tests/realworld/DATA_SOURCES.md) for
dataset attribution.

### What we have not tested

To set honest expectations:

- **Domains outside scientific papers.** The real-world oracle corpus
  is PubMed Central tables. Financial 10-K filings, sports statistics,
  legal schedules, and newswire tables may have structural idioms this
  test set doesn't exercise. See
  [tests/README.md](tests/README.md#future-dataset-coverage) for planned
  additions.
- **Browser-only tables.** Tables rendered by JavaScript, reconstructed
  from CSS grids, or pasted as Excel clipboard fragments are
  out-of-scope — the input contract is HTML markup.
- **Round-trip ambiguity on cells containing ` > `, ` | `, or `: `.**
  These characters are the rule-format separators, so a cell whose own
  text contains them cannot be distinguished from a split path on the
  consumer side. Data is preserved; cosmetic parsing is ambiguous.

---

## Benchmarking

Tests are organized in three layers — see [tests/README.md](tests/README.md)
for the full model.

**Layer 1 — Regression golds** (hand-authored fixtures, exact text match):
- `tests/smoke/` — minimal sanity checks
- `tests/structured/` — proper headers, hierarchical, real-world enterprise tables
- `tests/adversarial/` — hostile markup, tag mismatches, OCR artifacts, deep nesting
- `tests/headerless/` — receipts, OCR dumps — flat fallback (no parseable headers)
- `tests/regression/` — targeted bug fixes

**Layer 2 — Correctness oracle** (clean real-world tables, structural match):
- `tests/realworld/<dataset>/*.md` + `.oracle.json` — 200 PubTabNet
  tables with independently-computed per-cell oracle triples.

**Layer 3 — Robustness under mutation** (corrupted real-world HTML,
no-fabrication match):
- Same realworld fixtures as Layer 2, mutated on-the-fly.

### Run the test suite

```bash
pip install -e '.[dev]'
pytest
```

Each layer has its own test file:
[test_regression_golds.py](tests/test_regression_golds.py),
[test_correctness_oracle.py](tests/test_correctness_oracle.py),
[test_robustness_mutations.py](tests/test_robustness_mutations.py).

### Maintenance scripts

`scripts/benchmark.py` is a richer harness for diffing and refreshing gold:

```bash
# Run and diff current output vs gold
python3 scripts/benchmark.py --show-diff

# Refresh expected outputs after an intentional format change
python3 scripts/benchmark.py --update-gold

# Pick an exporter (default: rules)
python3 scripts/benchmark.py --format rules
```

`scripts/fuzz.py` generates randomized hostile inputs for the parser.

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
North America > Dr. Smith (Boston) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > Responders: 67%
Europe > Dr. Dubois (Paris) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > p-value: <0.001
Asia-Pacific > Dr. Tanaka (Tokyo) | Treatment Outcomes > Placebo (Control) > Secondary Endpoint > 95% CI: [-2.3, 4.7]
Pooled Analysis (All Sites) | Treatment Outcomes > Drug A (Experimental) > Primary Endpoint > Responders: 68%
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
