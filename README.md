# Table2Rules - Maze Pathfinder Approach

## The Breakthrough

**Tables are mazes. Each cell finds its headers by pathfinding.**

Instead of trying to understand table "types" or infer structure globally, each data cell independently navigates to find its context. This parser is built on a "Pragmatic + Pure" model: it first *repairs* broken HTML, then runs a *pure* logical algorithm.

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

  * **Learns Structure:** It first inspects the `<thead>` to count the number of row-header columns (`num_row_headers`).
  * **Builds Logical Grid:** Expands all `rowspan` and `colspan` cells into their true grid positions, marking copies with `is_span_copy`.
  * **Fixes `<tbody>`:** As it builds the grid, it uses its `logical_col` position and the `num_row_headers` count to *correctly* promote `<td>` cells (like "Revenue [$M]") to `<th>` tags, *without* touching data cells (like "80").
  * **Tags Context:** It tags every cell with `is_thead` and `is_footer` for the pathfinder.

### 4\. The "Pure" Core (`maze_pathfinder.py`)

With a perfect logical grid, the pathfinding is simple and 100% accurate. Each data cell (`<td>`) runs two searches:

  * **Walk LEFT:** Collects all `<th>` cells to its left on the same row.
  * **Walk UP:** Collects all `<th>` cells above it, with one critical rule: **it *only* accepts headers where `is_thead == True`**. This prevents "header pollution" from `<th>` tags inside the `<tbody>`.

### 5\. Post-Processing (`cleanup.py`)

  * **Deduplicates:** Removes duplicate headers created by overlapping spans.
  * **Filters Metadata:** Uses the `is_footer` flag to intelligently filter rules from metadata footers (like "Note:...") while *keeping* rules from data footers (like "Total Revenue").

## Why This Works

### Robust (Pure + Pragmatic)

This parser is robust because it doesn't trust the HTML. A "pragmatic" repair script first cleans the broken semantics, allowing a "pure" logical parser to run flawlessly.

### Universal

The same algorithm handles:

  * Multi-level `colspan`/`rowspan` headers (`<thead>`).
  * Multi-column `rowspan` headers (`<tbody>`).
  * Data footers (`<tfoot>`) with `colspan`.
  * Multi-`<tbody>` structures.

### Mathematically Correct

The core "Maze Pathfinder" logic isn't guessing. It's following the logical grid structure that `grid_parser` builds.

## Files

  * `table2rules.py` - Main entry point; finds top-level tables.
  * `simple_repair.py` - The "pragmatic" pre-parser that fixes broken HTML.
  * `grid_parser.py` - The "smart" core; builds the logical 2D grid.
  * `maze_pathfinder.py` - The "pure" core; runs "Walk LEFT" and "Walk UP".
  * `cleanup.py` - Post-processing and filtering.
  * `models.py` - Output structure (`LogicRule`).

## Example

### Input

```html
<table>
  <tr>
    <th>Region</th>
    <th>Product</th>
    <th>Q1</th>
  </tr>
  <tr>
    <th rowspan="2">Americas</th>
    <th>Alpha</th>
    <td>3.2</td>
  </tr>
  <tr>
    <th>Beta</th>
    <td>2.1</td>
  </tr>
</table>
```

### Cell at (1, 2) containing "3.2":

1.  Walk LEFT → finds "Alpha", "Americas"
2.  Walk UP → finds "Q1" (it's in the `<thead>`)
3.  Output: `Americas Alpha Q1: 3.2`

## The Key Insights

1.  **Each cell is independent** - No global table analysis needed.
2.  **Walk LEFT for row context** - Find all `<th>` to the left.
3.  **Walk UP *only in the `<thead>`*** - Find `<th>` above *only if* `is_thead == True`.
4.  **A "pure" parser needs a "pragmatic" repair script.** The core logic must be protected from bad HTML.
5.  **Learn from the `<thead>` to fix the `<tbody>`.** The *only* reliable way to fix `<tbody>` headers is to learn the header-column-count from the `<thead>`.
6.  **The parser must be "structure-aware."** The `grid_parser` is the only place to fix `<tbody>` `<td>` tags, as it's the only script that knows a cell's true `logical_col`.
7.  **Never parse HTML with regex.** Using BeautifulSoup to find *only* top-level tables is the key to avoiding nested-table bugs.

## Success Metrics

Tested and validated on a suite of "evil" tables:

  * ✅ **Monster Table:** (Financial report with `colspan`/`rowspan` in `<thead>`, `<tbody>`, and `<tfoot>`).
  * ✅ **Multi-`<tbody>` Table:** (Compliance report with `rowspan` and single-row headers).
  * ✅ **Evil Nested Table:** (Correctly parsed the *outer* table and "mushed" the inner table's content into a single cell).
  * ✅ **Irregular `<tbody>` Header:** (Correctly *ignored* `<th>` dividers in the `<tbody>` thanks to the `is_thead` check).

## What We Learned

Previous attempts were overengineered or too simple. The maze metaphor is the key:

> "You're a data cell dropped in a maze. **Walk left to find who you are.** **Walk up *to the header row* to find what you measure.**"

That's it. That's the whole algorithm.