from bs4 import BeautifulSoup
import re

def get_top_level_rows(table):
    """
    Helper function to robustly get ONLY the rows
    belonging to the main table, skipping nested tables.
    """
    all_rows_in_dom = table.find_all('tr')
    top_level_rows = []

    for row in all_rows_in_dom:
        if row.find_parent('table') is table:
            top_level_rows.append(row)

    return top_level_rows


def _safe_span(raw):
    """Coerce a rowspan/colspan attribute to an int ≥ 1.

    Adversarial HTML can carry non-numeric span values like `rowspan="foo"`
    or zero / negative values. Normalize these the same way grid_parser does
    so the header-detection helpers don't raise on that input.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


def _build_logical_grid(rows):
    """Expand DOM rows into a colspan/rowspan-aware occupancy grid.

    Returns (grid, origin_cells, max_cols) where
      grid[r][c] = {"nonempty": bool, "origin": (r0, c0), "rs": int, "cs": int}
      origin_cells[(r0, c0)] = DOM Tag of the originating cell
      max_cols = logical width of the table
    """
    occupied = {}
    max_cols = 0
    for r_idx, row in enumerate(rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        col = 0
        for cell in cells:
            while (r_idx, col) in occupied:
                col += 1
            rs = _safe_span(cell.get('rowspan', 1))
            cs = _safe_span(cell.get('colspan', 1))
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(r_idx + dr, col + dc)] = True
            col += cs
        max_cols = max(max_cols, col)

    n = len(rows)
    grid = [
        [{"nonempty": False, "origin": (r, c), "rs": 1, "cs": 1}
         for c in range(max_cols)]
        for r in range(n)
    ]
    origin_cells = {}
    filled_at = {}
    for r_idx, row in enumerate(rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        col = 0
        for cell in cells:
            while col < max_cols and (r_idx, col) in filled_at:
                col += 1
            if col >= max_cols:
                break
            rs = _safe_span(cell.get('rowspan', 1))
            cs = _safe_span(cell.get('colspan', 1))
            txt = cell.get_text(strip=True)
            nonempty = bool(txt)
            origin_cells[(r_idx, col)] = cell
            for dr in range(rs):
                for dc in range(cs):
                    tr, tc = r_idx + dr, col + dc
                    if tr < n and tc < max_cols:
                        grid[tr][tc] = {
                            "nonempty": nonempty,
                            "origin": (r_idx, col),
                            "rs": rs,
                            "cs": cs,
                        }
                        filled_at[(tr, tc)] = True
            col += cs
    return grid, origin_cells, max_cols


def detect_header_block(rows):
    """Infer the header block of a headless table via a universal structural
    rule — no content analysis, no percentage thresholds, no dataset-specific
    heuristics.

    Two structural definitions:

    1. A *clean data row* is a row r where every logical position (r, c) is
       an origin cell (not a rowspan copy from above) with rowspan == 1,
       colspan == 1, and non-empty text. A clean data row has no structural
       feature that could distinguish it from the rows below it — it is
       unambiguously part of the body.

    2. A *stub column* is a column non-empty in every non-divider body row.
       Section dividers (rows with ≤ 1 non-empty logical cell) are excluded
       from the body statistic because they are a separate structural class.

    Rule: the header block is the maximal leading prefix [0..k-1] where k is
    the index of the first clean data row whose col 0 is non-empty, provided
    every non-divider row in that prefix has its empty cells contained in
    stub columns.

    Why this works universally:
      * Dense first-row-header tables (receipts, simple relational): row 0
        is a clean data row, so k = 0 and no promotion occurs. This is
        structurally honest — without spans, empties, or other shape
        differences, row 0 is indistinguishable from row 1+, and the
        pipeline defers to the confidence gate.
      * Multi-row headers with colspan group labels (benefits, FinTabNet
        hierarchical): header rows carry colspan > 1 cells, so they are not
        clean data rows. The first clean data row follows the header block.
      * Financial 10-K tables with an empty row-stub label (FinTabNet
        single-row header): header rows have col 0 empty. Col 0 is a stub
        column (non-empty in every body row), so the empty in row 0 is
        permitted. The first clean data row is the first body row.

    Section-divider rows in the header region (single-cell rows like the
    "2014" year marker in FinTabNet) do NOT themselves qualify as headers,
    but they do not prevent the detection either — they sit inside the
    [0..k-1] range and are left as-is so the downstream thead-wrap naturally
    excludes them via Fix 7's contiguous-<th> chain.

    Returns (k, stub_cols, origin_cells, grid) on success, or None.
    """
    n = len(rows)
    if n < 3:
        return None

    grid, origin_cells, max_cols = _build_logical_grid(rows)
    if max_cols == 0:
        return None

    # Find the first data row. A data row is one whose shape has no
    # structural feature that would mark it as a header:
    #   - col 0 is non-empty (typical row-label)
    #   - at least two non-empty logical cells (not a section divider)
    #   - every logical position at row r is an origin cell at row r
    #     (no rowspan copy from above pulling header content into body)
    #   - every origin cell at row r has rowspan == colspan == 1
    #     (no colspan group or rowspan marker signaling header role)
    #
    # The "every cell non-empty" requirement was dropped intentionally:
    # real body rows in financial tables are often gappy (a cell has a
    # value only for some rows, e.g., an aggregate fair-value column
    # that only fills on vest events). The remaining conditions still
    # separate body rows from header rows — header rows typically carry
    # either an empty col 0 (row-stub-column signature) or a span of
    # some kind.
    first_data_idx = None
    for r in range(n):
        row = grid[r]
        if not row[0]["nonempty"]:
            continue
        nonempty_count = sum(1 for c in row if c["nonempty"])
        if nonempty_count < 2:
            continue
        is_clean = True
        for c in range(max_cols):
            cell = row[c]
            if cell["origin"] != (r, c):
                is_clean = False
                break
            if cell["rs"] != 1 or cell["cs"] != 1:
                is_clean = False
                break
        if is_clean:
            first_data_idx = r
            break

    if first_data_idx is None or first_data_idx == 0:
        return None

    # Header rows = non-divider, non-empty rows in the header region.
    header_row_indices = [
        r for r in range(first_data_idx)
        if sum(1 for c in grid[r] if c["nonempty"]) >= 2
    ]
    if not header_row_indices:
        return None

    # Body rows = non-divider rows from first_data_idx down.
    body_rows = [
        grid[r] for r in range(first_data_idx, n)
        if sum(1 for c in grid[r] if c["nonempty"]) >= 2
    ]
    if not body_rows:
        return None

    # A row-stub column is a col that is empty in *every* header row AND
    # non-empty in a strict majority of non-divider body rows. The
    # conjunction is load-bearing — "empty in every header" alone would
    # mis-label data columns whose top-level group header happens not to
    # cover them; "non-empty in every body row" (the stricter earlier
    # form) would reject tables whose trailing summary row leaves the
    # stub column blank (e.g. a FinTabNet totals row rendered as
    # `— | $1,573,043 | ...`). Strict majority — more non-empty body
    # rows than empty — is deterministic (a count comparison, not a
    # ratio), admits the unlabeled-summary-row pattern, and still
    # refuses to promote a sparsely-filled data column.
    stub_cols = set()
    for c in range(max_cols):
        all_empty_in_header = all(
            not grid[r][c]["nonempty"] for r in header_row_indices
        )
        if not all_empty_in_header:
            continue
        filled = sum(1 for br in body_rows if br[c]["nonempty"])
        empty = len(body_rows) - filled
        if filled > empty:
            stub_cols.add(c)

    # Validity: every column empty in every header row must either be a
    # stub (non-empty in a strict majority of body rows) or a column
    # that is used at all. If such a column fails the stub test, the
    # header region and body region disagree geometrically — there is
    # no consistent story for what that column is, so reject.
    for c in range(max_cols):
        all_empty_in_header = all(
            not grid[r][c]["nonempty"] for r in header_row_indices
        )
        if all_empty_in_header and c not in stub_cols:
            return None

    return first_data_idx, stub_cols, origin_cells, grid


def simple_repair(html: str) -> str:
    """
    Simple targeted repairs for common issues:
    0. Fix mismatched opening/closing tags (<td>...</th> and vice versa)
    1. Move title rows (full-width th) to caption
    2. Fix <td> headers in <tfoot> (for totals)
    3. Move footer legends to tfoot
    4. Convert first data row to proper header row (<th> tags)
    5. Promote summary labels (Total, Subtotal) in <tbody> to <th>
    6. Merge "hanging" description rows (e.g. Dates below items)
    """
    # --- Fix 0: Repair mismatched opening/closing tags ---
    # <td ...>text</th> and <th ...>text</td> cause html.parser to nest
    # subsequent sibling cells inside the unclosed element.
    # Fix by normalising closing tags to match their opener.
    # [^<]* restricts to plain-text content so we never span across tags.
    html = re.sub(r'(<td\b[^>]*>)([^<]*)</th>', r'\1\2</td>', html)
    html = re.sub(r'(<th\b[^>]*>)([^<]*)</td>', r'\1\2</th>', html)

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return html
    
    # --- Fix 9: Inline nested tables ---
    # Replace <table> elements inside cells with their flattened text
    # so the outer grid parser sees clean content instead of nested markup.
    for nested in table.find_all('table'):
        rows = nested.find_all('tr')
        lines = []
        for row in rows:
            cells = row.find_all(['td', 'th'], recursive=False)
            texts = [c.get_text(strip=True) for c in cells]
            if any(texts):
                lines.append(", ".join(t for t in texts if t))
        nested.replace_with("; ".join(lines))

    actual_rows = get_top_level_rows(table)
    if not actual_rows:
        return html

    # --- Fix 1: Move title row to caption ---
    first_meaningful_row = None
    first_meaningful_row_index = 0
    for idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        if cells:
            first_meaningful_row = row
            first_meaningful_row_index = idx
            break
            
    if first_meaningful_row:
        cells = first_meaningful_row.find_all(['td', 'th'], recursive=False)
        # Treat the first row as a title iff it is a single cell whose colspan
        # covers the full width of the remaining rows (width >= 2). This
        # captures 2-col and 3-col tables correctly without over-promoting.
        later_widths = [
            len(r.find_all(['td', 'th'], recursive=False))
            for r in actual_rows[first_meaningful_row_index + 1:]
        ]
        max_later_width = max(later_widths, default=0)
        first_cell_span = int(cells[0].get('colspan', 1))
        if (
            len(cells) == 1
            and max_later_width >= 2
            and first_cell_span >= max_later_width
        ):
            title_text = cells[0].get_text(strip=True)
            caption = table.find('caption')
            if caption:
                caption.string = title_text
            else:
                new_caption = soup.new_tag('caption')
                new_caption.string = title_text
                table.insert(0, new_caption)
            for i in range(first_meaningful_row_index + 1):
                actual_rows[i].decompose()
        actual_rows = get_top_level_rows(table)


    # --- Fix 1b: Decompose mid-table section-title rows ---
    # A <tr> whose sole cell is a <th> with colspan covering the grid
    # width is structurally a section label (e.g. "Personal" / "Work"
    # delimiting A/V blocks in two <tbody>s). If it survives into the
    # grid, the span expansion turns the label into a fabricated column
    # header for the rows below. Decompose these rows so section labels
    # don't pollute the header walk. Fix 1 already handles the first-row
    # instance by moving it to <caption>; this handles mid-table ones.
    if actual_rows:
        row_widths = [
            len(r.find_all(['td', 'th'], recursive=False))
            for r in actual_rows
        ]
        max_width = max(row_widths, default=0)
        if max_width >= 2:
            for row in list(actual_rows):
                cells = row.find_all(['td', 'th'], recursive=False)
                if len(cells) != 1:
                    continue
                cell = cells[0]
                if cell.name != 'th':
                    continue
                colspan = int(cell.get('colspan', 1))
                if colspan >= max_width:
                    row.decompose()
        actual_rows = get_top_level_rows(table)


    # --- Fix 4: Structural header-block promotion ---
    # Universal structural rule (replaces the old row-0-only "all cells
    # non-empty" heuristic). See detect_header_block for the full spec —
    # the rule is deterministic, content-free, and subsumes three cases
    # previously handled by disjoint heuristics:
    #
    #   Dense first-row headers (receipts, simple relational): row 0 is
    #   a clean data row, detection returns None, no promotion.
    #
    #   Multi-row headers with colspan group labels (benefits-style,
    #   FinTabNet hierarchical): span-bearing rows above the first clean
    #   data row form the header block.
    #
    #   Financial 10-K tables with an empty row-stub label (FinTabNet
    #   single-row headers): col 0 is structurally identified as a stub
    #   column (empty in every header, filled in every body), and the
    #   empty col-0 cell in the header row is permitted.
    #
    # Promotes header-region rows (non-divider) to <th> so Fix 7 can wrap
    # them in <thead>. Promotes stub-column body cells to <th scope="row">
    # so dimensional columns are recognized even in single-row-header
    # tables (Fix 8 only covers multi-row <thead>).
    if not table.find('thead') and actual_rows:
        detection = detect_header_block(actual_rows)
        if detection is not None:
            first_data_idx, stub_cols, origin_cells, grid = detection
            # Promote header-region rows to <th> (skip section dividers
            # and empty rows — dividers are structurally distinct and
            # would break the thead contiguous-<th> chain intentionally).
            # Use the *logical* non-empty count (colspan-expanded) so that
            # a single-DOM-cell row with a wide colspan — e.g., a "(Dollars
            # in thousands)" sub-header — is recognized as a multi-cell
            # row rather than mis-classified as a divider.
            for r_idx in range(first_data_idx):
                logical_nonempty = sum(
                    1 for cell in grid[r_idx] if cell["nonempty"]
                )
                if logical_nonempty <= 1:
                    continue
                row = actual_rows[r_idx]
                for cell in row.find_all(['td', 'th'], recursive=False):
                    if cell.name == 'td':
                        cell.name = 'th'
            # Promote stub-column body cells to <th scope="row"> at origin.
            for c in stub_cols:
                for r_idx in range(first_data_idx, len(actual_rows)):
                    if r_idx >= len(grid):
                        break
                    origin = grid[r_idx][c]["origin"]
                    if origin[0] < first_data_idx:
                        continue
                    cell = origin_cells.get(origin)
                    if cell is None:
                        continue
                    if cell.name == 'td':
                        cell.name = 'th'
                        if not cell.get('scope'):
                            cell['scope'] = 'row'
            # Row-group divider promotion. A row with exactly one
            # non-empty logical cell whose column is in stub_cols is a
            # row-group header for the body rows that follow until the
            # next such divider — the FinTabNet year-label pattern
            # ("2014" row between Q1–Q4 blocks). Promoting the cell to
            # <th scope="rowgroup"> lets maze_pathfinder walk up the
            # stub column and include the group label in row_path for
            # subsequent body cells.
            #
            # Iterate from the end of the contiguous promoted-header
            # prefix (what Fix 7 will wrap into <thead>) onward — so
            # dividers inside the header region (e.g., a divider row
            # that breaks the <th>-or-empty chain) are correctly
            # classified as body rowgroup markers, not thead cells.
            #
            # Structurally distinct from the <th scope="row"> promotion
            # above: row-headers are *peer* labels (one per row),
            # rowgroup-headers are *ancestor* labels (span multiple rows).
            thead_end = 0
            for r in range(first_data_idx):
                if sum(1 for c in grid[r] if c["nonempty"]) >= 2:
                    thead_end = r + 1
                else:
                    break
            for r_idx in range(thead_end, len(actual_rows)):
                if r_idx >= len(grid):
                    break
                row = grid[r_idx]
                non_empty_cols = [
                    c for c in range(len(row)) if row[c]["nonempty"]
                ]
                if len(non_empty_cols) != 1:
                    continue
                only_col = non_empty_cols[0]
                if only_col not in stub_cols:
                    continue
                origin = row[only_col]["origin"]
                if origin[0] < thead_end:
                    continue
                cell = origin_cells.get(origin)
                if cell is None:
                    continue
                if cell.name == 'td':
                    cell.name = 'th'
                cell['scope'] = 'rowgroup'

    # --- Fix 7: Wrap header rows in <thead> ---
    # If table lacks <thead>, detect contiguous leading rows that are "header-like"
    # (all <th> cells, or all <th>/empty cells) and wrap them in <thead>.
    # This ensures downstream logic can rely on is_thead to identify column headers.
    if not table.find('thead') and actual_rows:
        header_rows = []
        seen_non_empty = False

        for row in actual_rows:
            cells = row.find_all(['td', 'th'], recursive=False)

            # Ignore leading empty rows; do not treat them as headers
            if not cells and not seen_non_empty:
                continue

            if not cells and seen_non_empty:
                # Empty row after header block means header detection ends
                break

            seen_non_empty = True

            # A row is "header-like" if all cells are <th> or empty
            is_header_like = all(
                cell.name == 'th' or not cell.get_text(strip=True)
                for cell in cells
            )

            if is_header_like:
                header_rows.append(row)
            else:
                # Stop at first non-header row
                break
        
        # Only wrap if we found header rows (and they're not ALL the rows)
        if header_rows and len(header_rows) < len(actual_rows):
            thead = soup.new_tag('thead')
            
            # Insert thead at the beginning of the table
            # (after caption if present)
            caption = table.find('caption')
            if caption:
                caption.insert_after(thead)
            else:
                table.insert(0, thead)
            
            # Move header rows into thead
            for row in header_rows:
                row.extract()
                thead.append(row)
            
            actual_rows = get_top_level_rows(table)


    # --- Fix 8: Promote row headers based on <thead> structure ---
    # If <thead> has multi-row structure (hierarchical column headers), the first
    # column typically contains row identifiers. Promote first-column <td> cells 
    # in <tbody> to <th scope="row">.
    # 
    # We only promote cells that:
    # 1. Are the first cell in their DOM row, AND
    # 2. Either have rowspan > 1 (explicit row group identifier), OR
    # 3. Are not "covered" by a rowspan from a previous row
    thead = table.find('thead')
    if thead:
        thead_rows = thead.find_all('tr', recursive=False)
        header_depth = len(thead_rows)
        
        if header_depth > 1:
            # Multi-row header structure suggests dimensional table
            tbody = table.find('tbody')
            if tbody:
                active_rowspan = 0  # Track if a rowspan from above covers first column

                for row in tbody.find_all('tr', recursive=False):
                    cells = row.find_all(['td', 'th'], recursive=False)

                    if active_rowspan > 0:
                        # First column is covered by rowspan from above.
                        active_rowspan -= 1
                        continue
                    if not cells:
                        continue

                    first = cells[0]
                    # Promote to row-header if not already. Fix 4 may have
                    # pre-promoted this cell via its stub-column path — in
                    # that case we still need to track the rowspan so the
                    # counter stays in sync with the grid, otherwise a cell
                    # at logical col > 0 in a subsequent row would be
                    # mistaken for the first-column cell.
                    if first.name == 'td':
                        first.name = 'th'
                        first['scope'] = 'row'
                    rowspan = _safe_span(first.get('rowspan', 1))
                    if rowspan > 1:
                        active_rowspan = rowspan - 1


    # --- Fix 6: Merge "Hanging" Description Rows ---
    # Detects "wrap continuation" rows: a row with text in only the first cell
    # (rest empty) that follows a fully-populated data row. Historically meant
    # to rejoin labels that wrapped to a new line in some extractor outputs.
    #
    # In practice, this pattern is vastly more often a SECTION DIVIDER row
    # (scientific / financial tables introducing a sub-group) than a genuine
    # wrap continuation. Merging section dividers corrupts adjacent data
    # rows (observed on PubTabNet, HiTab). So we only fire when the row is
    # very likely to be a continuation:
    #   - current sparse row has a wide trailing colspan  → section marker
    #   - next row has a continuation-like shape          → probably wrap
    # For now, the safer default is to NOT merge. The edge case where this
    # merge was useful (single-column wrapped descriptions on narrow tables)
    # hasn't resurfaced across the corpus and red-team fixtures.

    # (merge loop intentionally disabled — see commit log for context)


    # --- Fix 2, 3, 5: Iterate remaining rows ---
    # Re-fetch rows just in case, though pop() should keep list valid
    # (Safe to use existing list references if we were careful, but let's be safe)
    actual_rows = get_top_level_rows(table)
    
    summary_keywords = ['total', 'subtotal', 'sub total', 'amount due', 'amount payable', 'balance', 'tax', 'vat', 'gst']

    for idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        if not cells:
            continue
            
        # --- Fix 2: Fix <tfoot> row headers ---
        if row.find_parent('tfoot') and cells[0].name == 'td':
            if int(cells[0].get('colspan', 1)) > 1:
                cells[0].name = 'th'
                cells[0]['scope'] = 'colgroup'
        
        # --- Fix 3: Move footer legends to tfoot ---
        if not row.find_parent('tfoot'):
            if len(cells) == 1:
                text = cells[0].get_text(strip=True).lower()
                if 'legend' in text or 'footnote' in text:
                    colspan = int(cells[0].get('colspan', 1))
                    if colspan >= 3:
                        tfoot = table.find('tfoot')
                        if not tfoot:
                            tfoot = soup.new_tag('tfoot')
                            table.append(tfoot)
                        row.extract()
                        tfoot.append(row)
                        continue 

        # --- Fix 5: Promote Summary Labels ---
        # Only applies in tbody — 'Total', 'Subtotal', etc. inside <thead>
        # are legitimate column headers (PubTabNet-style financial tables
        # have a 'Total' column under a 'Year Ended' grouping), and marking
        # them scope="row" would hide them from the column-header walk.
        if idx > 0 and not row.find_parent('thead'):
            for cell in cells:
                if cell.name == 'td':
                    txt = cell.get_text(strip=True).lower()
                    if any(txt.startswith(kw) for kw in summary_keywords):
                        cell.name = 'th'
                        cell['scope'] = 'row'

    return str(soup)
