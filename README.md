# Table2Rules — Maze Pathfinder Approach

[![PyPI](https://img.shields.io/pypi/v/table2rules.svg)](https://pypi.org/project/table2rules/)
[![Python versions](https://img.shields.io/pypi/pyversions/table2rules.svg)](https://pypi.org/project/table2rules/)
[![License: MIT](https://img.shields.io/pypi/l/table2rules.svg)](LICENSE)
[![CI](https://github.com/pebbleroad/table2rules/actions/workflows/test.yml/badge.svg)](https://github.com/pebbleroad/table2rules/actions/workflows/test.yml)

## The DNA of Table Parsing

**Tables are mazes. Each cell finds its headers by pathfinding.**

This isn't pattern-matching or table-type detection. It's a universal algorithm based on how HTML tables actually work:

1. **Cells occupy grid positions** (with rowspan/colspan expanding them)
2. **Headers relate to data cells** via spatial relationships (left = row context, above = column context)
3. **Semantic markers** (`<th>`, `<thead>`, `scope`) signal intent

The algorithm **discovers structure** — it doesn't memorize patterns. When markup is ambiguous or hostile, it fails open and preserves raw HTML instead of inventing structure. This makes outputs more trustworthy for enterprise pipelines and LLM workflows where correctness and traceability matter more than aggressive guessing.

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

This is why we produce rules, not just markdown: rules are the representation tables need to survive a RAG pipeline intact.

### Where this library fits vs. other tools

- **Unstructured.io, markitdown, docling**: extract tables as markdown/HTML. Excellent at extraction, table2rules-incompatible at chunking without additional work.
- **LlamaParse**: paid, similar intent at a higher level (whole-document parsing).
- **pandas / lxml**: give you structured data, not RAG-ingestible facts.
- **table2rules**: narrow scope — HTML table in, self-contained facts out, fail-open on hostile input. Pair it with any of the above in a pipeline: extract with your tool, pass the table HTML through table2rules before chunking.

### What this buys you on today's stack

Three pressures RAG teams are under right now, and what table2rules does about each:

**1) Token bloat on frontier models.** On 200 real PubTabNet tables, the rules output is a median **27% smaller** than the source HTML (p25–p75: 12%–39% savings, measured with OpenAI's `cl100k_base` tokenizer — see [scripts/measure_token_savings.py](scripts/measure_token_savings.py) to reproduce). It's not free, though: on **16% of tables** — dense ones with long header paths — the rules output actually *grows* by up to 59%, because each data cell carries its full row- and col-header path. That's the deliberate tradeoff: where the representation costs extra tokens, it's preserving the context the HTML would otherwise lose at a chunk boundary.

**2) SLMs getting confused by HTML baggage.** Teams increasingly deploy small models (Phi-3, Qwen 2.5 3B, Llama 3.2) where latency and cost matter more than capability headroom. Smaller models have less attention to spend filtering out structural noise — nested tag hierarchy, attribute clutter, whitespace — before they can reason about content. The rules format strips that to a flat sequence of `row-path | col-path: value` statements with no markup.

**3) No chunk configuration.** Teams typically spend meaningful time tuning how long tables are chunked: recursive-character splitter, token splitter, markdown-header-aware splitter, `"don't split in the middle of a table"` heuristics. With table2rules output, every line is a self-contained fact — **any chunker can split anywhere** without orphaning a row from its headers. The chunking question stops being about tables.

### Language coverage

**table2rules operates on table geometry, not cell text.** Header detection, span resolution, row-group propagation, and every other parsing decision is a deterministic property of the markup — cell type, span values, empty-vs-non-empty, row/column fill patterns. The one content-level question the pipeline asks is *"does this cell contain any letter?"* via Unicode `str.isalpha()`, used to distinguish descriptor columns from numeric ones. Every writing system answers identically: Latin, Cyrillic, CJK, Arabic, Devanagari, Thai, Hebrew. No language-specific lexicons, no keyword lists, no English bias — a financial table in 合計 / итого / المجموع parses by the same rules as one in English.

---

## Output Format

The default `rules` exporter emits **one self-contained rule per line** — every line carries the full row-header path and full column-header path:

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

See [docs/examples.md](docs/examples.md) for a gallery of inputs and
outputs, from key-value tables to four-level-header clinical trial data.

---

## Installation

```bash
pip install table2rules
```

Or from source:

```bash
pip install -e .
```

See [CHANGELOG.md](CHANGELOG.md) for release notes and migration guidance.

---

## Usage

### Python API — the minimal call

```python
from table2rules import process_tables_to_text

html = open("page.html").read()
rules = process_tables_to_text(html)           # default: format="rules"
print(rules)
```

### Python API — with observability

When you need to know *which* tables rendered cleanly and which fell back,
use the stats form. It returns the same text plus a structured
`RenderReport` with one `TableReport` per top-level table:

```python
from table2rules import process_tables_with_stats

text, report = process_tables_with_stats(html)

for t in report.tables:
    if t.render_mode != "rules":
        print(f"table {t.table_index}: {t.render_mode} — {t.reasons}")
```

`render_mode` is one of `"rules"`, `"flat"`, `"passthrough"`, or
`"skipped"`. The full playbook — what each mode means operationally, how to
group the 16 reason codes by severity, `gate_score` thresholds, batch
aggregation, `strict` mode, thread safety, and a conservative policy
template — is in **[docs/integrating.md](docs/integrating.md)**. Read that
before wiring this into anything production.

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

### Custom exporters

Output formatting is pluggable. Built-in: `rules` (default, one fact per
line). Third parties can add custom exporters by registering an object with
`export_rules` / `export_flat` methods — see
[docs/integrating.md](docs/integrating.md) for the full exporter protocol
and a JSONL example.

### Public API and stability

The public API is exactly the names listed in `table2rules.__all__` (and re-exported at the package root). Anything else — submodules like `table2rules.grid_parser`, internal helpers, undocumented attributes — is implementation detail and may change in any release without notice. SemVer compatibility guarantees apply only to the documented public surface.

---

## Safety contract

- Parse and transform well-formed tables deterministically.
- Apply bounded generic repair for common breakage (mismatched tags, missing `<thead>`, malformed spans).
- If invariants / confidence fail, degrade to header-free flat rows, then to passthrough of the original HTML — never fabricate content.
- Clamp per-cell `rowspan` / `colspan` to 1000 and refuse tables whose expanded grid would exceed 1,000,000 cells. Adversarial span values surface as a `TableReport` with `render_mode="skipped"` rather than an OOM.
- Surface the per-table verdict via `process_tables_with_stats` so callers can route flagged tables through their own policy instead of discovering lossy output downstream.

## Limitations

- Output format is deterministic but not guaranteed to match every downstream schema; separators and grouping are optimized for parseability.
- The repair stage is bounded and generic; it does not attempt arbitrary HTML surgery.
- Extremely malformed or ambiguous tables may be passed through as raw HTML by design (fail-open safety).
- Semantic interpretation is intentionally conservative: the system transforms structure, it does not infer business meaning beyond table topology and header scopes.
- Benchmark coverage improves confidence but cannot prove correctness for all possible HTML table encodings.

---

## Validation at a glance

Tested against 200 real PubTabNet tables with per-cell oracle matching,
plus ~2,000 mutation tests applying 10 HTML-noise patterns on top. The
parser either matches the oracle exactly or degrades to flat / passthrough
— it never fabricates content. Full test model, corpus details, and
reproduction instructions are in [docs/validation.md](docs/validation.md).

---

## Documentation map

- **[docs/integrating.md](docs/integrating.md)** — wiring `table2rules`
  into a production pipeline: render modes, reason severity, gate scoring,
  logging, strict mode, policy templates.
- **[docs/architecture.md](docs/architecture.md)** — internals of the
  repair → grid → pathfinder → output pipeline.
- **[docs/examples.md](docs/examples.md)** — gallery of HTML inputs and
  their rules-format outputs.
- **[docs/validation.md](docs/validation.md)** — test corpora, coverage
  gaps, and how to run the suite locally.
- **[CHANGELOG.md](CHANGELOG.md)** — release notes and migration guidance.
