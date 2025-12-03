# Table2Rules - Maze Pathfinder Approach

## The Breakthrough

**Tables are mazes. Each cell finds its headers by pathfinding.**

Instead of trying to understand table "types" or infer structure globally, each data cell independently navigates to find its context. This parser is built on a "Pragmatic + Pure" model: it first *repairs* broken HTML, then runs a *pure* logical algorithm.

## Output Format

Rules express table data in a natural, parseable format that preserves dimensional grouping:

```
Entity Headers → Attribute Headers: Value
```

Headers within each dimension are separated by `|`, making it easy to parse while remaining human-readable.

**Example:**
```
Severity Level | Very Severe → Number of requests: 0
Severity Level | Very Severe → SLA Met | Yes: 0
Program | Project | Program Atlas | Aquila → Phase Gates | Discovery | Plan: Jan
```

This format:
- ✅ Preserves two-dimensional table structure (entity vs attribute)
- ✅ Is trivially parseable (clear delimiters: `|`, `→`, `:`)
- ✅ Uses semantic names (actual headers, not generic attr0/attr1)
- ✅ Works for LLM embeddings and schema extraction

## How It Works: The Pipeline

This is not just a simple script, but a robust 6-stage pipeline.

### 1\. Entry Point (`table2rules.py`)

  * Uses BeautifulSoup to find all *top-level* tables.
  * It **does not use regex**, which avoids the "greedy" bug with nested tables.
  * Passes each top-level table string to the `process_table` function.

### 2\. The "Pragmatic" Layer (`simple_repair.py`)

This script's job is to fix "semantically incorrect" HTML *before* the pure parser sees it. It makes the HTML "honest."

  * **Fixes Footers:** Converts `<td>` with `colspan` in a `<tfoot>` (like "Total Revenue") to a `<th>`.
  * **Fixes Captions:** Moves full-width header rows to a proper `<caption>` tag.
  * **Filters Legends:** Moves metadata-like rows (e.g., "Note:", "Legend:") to the `tfoot`.
  * **Robust Row-Finding:** Safely finds all top-level rows, even in the presence of nested tables.

### 3\. The "Smart" Core (`grid_parser.py`)

This is the heart of the parser. It builds the 2D logical grid with "mathematical" precision.

  * **Learns Structure:** For tables with `<thead>`, it defaults to 1 row-header column (the safest assumption). For headless tables, it uses heuristics to detect header structure.
  * **Builds Logical Grid:** Expands all `rowspan` and `colspan` cells into their true grid positions, marking copies with `is_span_copy`.
  * **Fixes `<tbody>`:** As it builds the grid, it uses its `logical_col` position and the `num_row_headers` count to *correctly* promote `<td>` cells (like "Revenue [$M]") to `<th>` tags, *without* touching data cells (like "80").
  * **Tags Context:** It tags every cell with `is_thead` and `is_footer` for the pathfinder.

### 4\. The "Pure" Core (`maze_pathfinder.py`)

With a perfect logical grid, the pathfinding is simple and 100% accurate. Each data cell (`<td>`) runs three searches:

  * **Walk LEFT:** Collects all `<th>` cells to its left on the same row (entity/subject headers).
  * **Walk UP (from data column):** Collects all `<th>` cells above the data cell, with one critical rule: **it *only* accepts headers where `is_thead == True`**. This prevents "header pollution" from `<th>` tags inside the `<tbody>`.
  * **Walk UP (from row header columns):** Walks up from each row header's column to find their column headers (like "Program", "Project"), ensuring full context.

The pathfinder returns row headers and column headers **separately**, preserving the two-dimensional structure.

### 5\. Post-Processing (`cleanup.py`)

  * **Deduplicates:** Removes duplicate headers created by overlapping spans in both row and column dimensions.
  * **Filters Metadata:** Uses the `is_footer` flag to intelligently filter rules from metadata footers (like "Note:...") while *keeping* rules from data footers (like "Total Revenue").

### 6\. Output Generation (`models.py`)

The `LogicRule` dataclass stores:
- `row_headers` - Entity/subject dimension
- `col_headers` - Attribute/measurement dimension  
- `outcome` - The data value

The `to_string()` method formats these as: `row_headers → col_headers: outcome`

## Why This Works

### Robust (Pure + Pragmatic)

This parser is robust because it doesn't trust the HTML. A "pragmatic" repair script first cleans the broken semantics, allowing a "pure" logical parser to run flawlessly.

### Universal

The same algorithm handles:

  * Multi-level `colspan`/`rowspan` headers (`<thead>`).
  * Multi-column `rowspan` headers (`<tbody>`).
  * Data footers (`<tfoot>`) with `colspan`.
  * Multi-`<tbody>` structures.
  * Headless tables with implicit headers.
  * Key-value tables (2 columns, th+td pattern).

### Mathematically Correct

The core "Maze Pathfinder" logic isn't guessing. It's following the logical grid structure that `grid_parser` builds.

## Files

  * `table2rules.py` - Main entry point; finds top-level tables.
  * `simple_repair.py` - The "pragmatic" pre-parser that fixes broken HTML.
  * `grid_parser.py` - The "smart" core; builds the logical 2D grid.
  * `maze_pathfinder.py` - The "pure" core; runs "Walk LEFT" and "Walk UP", returns separated dimensions.
  * `cleanup.py` - Post-processing and filtering.
  * `models.py` - Output structure (`LogicRule`) with arrow-separated format.

## Example

### Input

```html
<table>
  <thead>
    <tr>
      <th rowspan="2">Severity Level</th>
      <th rowspan="2">Number of requests</th>
      <th colspan="2">SLA Met</th>
    </tr>
    <tr>
      <th>Yes</th>
      <th>No</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Very Severe</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
    </tr>
    <tr>
      <td>Severe</td>
      <td>0</td>
      <td>0</td>
      <td>0</td>
    </tr>
  </tbody>
</table>
```

### Output Rules

```
Severity Level | Very Severe → Number of requests: 0
Severity Level | Very Severe → SLA Met | Yes: 0
Severity Level | Very Severe → SLA Met | No: 0
Severity Level | Severe → Number of requests: 0
Severity Level | Severe → SLA Met | Yes: 0
Severity Level | Severe → SLA Met | No: 0
```

### Parsing the Output

```python
def parse_rule(line):
    # Split into parts
    headers_part, value = line.split(': ')
    entity_part, attribute_part = headers_part.split(' → ')
    
    # Parse each dimension
    entity = [h.strip() for h in entity_part.split('|')]
    attribute = [h.strip() for h in attribute_part.split('|')]
    
    return entity, attribute, value

# Example
line = "Severity Level | Very Severe → SLA Met | Yes: 0"
entity, attribute, value = parse_rule(line)
# entity = ['Severity Level', 'Very Severe']
# attribute = ['SLA Met', 'Yes']
# value = '0'
```

## The Key Insights

1.  **Each cell is independent** - No global table analysis needed.
2.  **Walk LEFT for entity context** - Find all `<th>` to the left (who/what).
3.  **Walk UP for attribute context** - Find `<th>` above (what about them).
4.  **Walk UP from row headers too** - Row header columns need their column headers.
5.  **Separate the dimensions** - Return row and column headers separately to preserve table structure.
6.  **A "pure" parser needs a "pragmatic" repair script** - The core logic must be protected from bad HTML.
7.  **Default to 1 row header for `<thead>` tables** - The safest assumption for structured tables.
8.  **Never parse HTML with regex** - Using BeautifulSoup to find *only* top-level tables is the key to avoiding nested-table bugs.
9.  **Use clear delimiters** - `|` for headers within a dimension, `→` between dimensions, `:` before the value.

## Success Metrics

Tested and validated on a suite of "evil" tables:

  * ✅ **Monster Table:** (Financial report with `colspan`/`rowspan` in `<thead>`, `<tbody>`, and `<tfoot>`).
  * ✅ **Multi-`<tbody>` Table:** (Compliance report with `rowspan` and single-row headers).
  * ✅ **Evil Nested Table:** (Correctly parsed the *outer* table and "mushed" the inner table's content into a single cell).
  * ✅ **Irregular `<tbody>` Header:** (Correctly *ignored* `<th>` dividers in the `<tbody>` thanks to the `is_thead` check).
  * ✅ **Hierarchical Headers:** (Multi-level column headers like "Phase Gates → Discovery → Plan").
  * ✅ **SLA Tables:** (Column headers that span without being row headers).

## What We Learned

Previous attempts were overengineered or too simple. The maze metaphor combined with dimensional separation is the key:

> "You're a data cell dropped in a maze. **Walk left to find your entity context.** **Walk up to find your attribute context.** **Separate them with an arrow.**"

That's it. That's the whole algorithm.