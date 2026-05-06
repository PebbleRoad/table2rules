import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .spans import assert_grid_size, clamped_span


def get_top_level_rows(table):
    """
    Helper function to robustly get ONLY the rows
    belonging to the main table, skipping nested tables.
    """
    all_rows_in_dom = table.find_all("tr")
    top_level_rows = []

    for row in all_rows_in_dom:
        if row.find_parent("table") is table:
            top_level_rows.append(row)

    return top_level_rows


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
        cells = row.find_all(["td", "th"], recursive=False)
        col = 0
        for cell in cells:
            while (r_idx, col) in occupied:
                col += 1
            rs = clamped_span(cell.get("rowspan", 1))
            cs = clamped_span(cell.get("colspan", 1))
            assert_grid_size(len(rows), col + cs)
            for dr in range(min(rs, len(rows) - r_idx)):
                for dc in range(cs):
                    occupied[(r_idx + dr, col + dc)] = True
            col += cs
        max_cols = max(max_cols, col)

    n = len(rows)
    grid = [
        [{"nonempty": False, "origin": (r, c), "rs": 1, "cs": 1} for c in range(max_cols)]
        for r in range(n)
    ]
    origin_cells = {}
    filled_at = {}
    for r_idx, row in enumerate(rows):
        cells = row.find_all(["td", "th"], recursive=False)
        col = 0
        for cell in cells:
            while col < max_cols and (r_idx, col) in filled_at:
                col += 1
            if col >= max_cols:
                break
            rs = clamped_span(cell.get("rowspan", 1))
            cs = clamped_span(cell.get("colspan", 1))
            txt = cell.get_text(strip=True)
            nonempty = bool(txt)
            origin_cells[(r_idx, col)] = cell
            for dr in range(min(rs, n - r_idx)):
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

    Two further structural witnesses extend "clean data row" to disqualify
    rows that look header-shaped relative to the body:

    * **Fuller-than-body**: row r's non-empty cell count is strictly greater
      than the minimum non-empty count of the non-divider rows below it,
      AND every column where row r is non-empty has at least one body
      row that fills the same column. A row that fills more columns
      than at least one body row is naming columns the body sometimes
      leaves empty — the structural signature of a column-header row
      above an implicit-rowspan group-label column, a multi-stub
      indentation pyramid, or an alternating coefficient/std-error
      layout. Comparing to the minimum (rather than median or mean)
      is intentional: the structural distinction is "exists a body
      row with fewer non-empty cells than row r," and strictly more
      central statistics misfire on tables where a slim majority of body
      rows match row r's fullness. The body-coverage clause excludes
      receipts whose row 0 is a 4-cell line item followed by 2-cell
      totals — there cols 2 and 3 are filled only in row 0, the body
      never uses them, and promoting row 0 to header would erase the
      line-item data. Uniform-dense tables stay out because their min
      equals row r's count.

    * **Cell-type inversion**: row r contains at least one corner-stub
      ``<td>`` — a column where row r is ``<td>`` while the body majority
      is ``<th>`` — and a strict majority of compared columns invert.
      The corner-stub clause is load-bearing: an all-``<th>`` row above
      an all-``<td>`` body inverts every column too, but that's the
      *normal* header pattern (and Fix 7 already wraps it in ``<thead>``
      via the contiguous-``<th>`` chain). Inversion is only the right
      witness when row r has a stray ``<td>`` corner cell that the body
      makes a ``<th scope="row">`` (e.g., header row ``[td, th, th]``
      above body rows ``[th, td, td]``). Universal: cell tags are
      markup, not content.

    Both extended witnesses apply only at r == 0 — the literal first
    row. Beyond row 0, "fuller than the body below" describes regular
    data rows (regression group labels, alternating coefficient/std-err
    pairs) and "first row with col 0 non-empty" is already the existing
    stub-column header pattern handled by the rest of the function.

    Returns (k, stub_cols, origin_cells, grid) on success, or None.
    """
    n = len(rows)
    if n < 3:
        return None

    grid, origin_cells, max_cols = _build_logical_grid(rows)
    if max_cols == 0:
        return None

    # Pre-compute per-row non-empty counts (logical, colspan-expanded).
    nonempty_counts = [sum(1 for c in row if c["nonempty"]) for row in grid]

    def _body_min_nonempty(after_r: int) -> int:
        """Minimum non-empty count among non-divider rows strictly after
        ``after_r``. Returns -1 when no qualifying body row exists
        (caller treats that as "no body to compare against" and skips
        the witness).
        """
        counts = [
            nonempty_counts[r2] for r2 in range(after_r + 1, n) if nonempty_counts[r2] >= 2
        ]
        if not counts:
            return -1
        return min(counts)

    def _row_cols_covered_by_body(r: int) -> bool:
        """True iff every column where row r is non-empty has at least one
        non-divider body row below that fills the same column. Excludes
        receipts whose row 0 fills columns the body never uses (line
        item over totals)."""
        for c in range(max_cols):
            if not grid[r][c]["nonempty"]:
                continue
            covered = False
            for r2 in range(r + 1, n):
                if nonempty_counts[r2] < 2:
                    continue
                if grid[r2][c]["nonempty"]:
                    covered = True
                    break
            if not covered:
                return False
        return True

    def _is_inverted_relative_to_body(r: int) -> bool:
        """True iff row r contains a corner-stub ``<td>`` and inverts the
        body majority at a strict majority of compared columns. Only
        origin cells with non-empty text on both sides participate.

        The corner-stub clause requires ≥1 column where row r is ``<td>``
        but body majority is ``<th>``. Without it, an all-``<th>`` row
        above an all-``<td>`` body would also "invert" every column — but
        that's the normal header pattern, already handled by Fix 7's
        contiguous-``<th>`` thead wrap.
        """
        has_corner_stub = False
        inverted = 0
        checked = 0
        for c in range(max_cols):
            row_cell = grid[r][c]
            if row_cell["origin"] != (r, c) or not row_cell["nonempty"]:
                continue
            row_origin = origin_cells.get((r, c))
            if row_origin is None or row_origin.name not in ("td", "th"):
                continue
            row_tag = row_origin.name

            td_count = 0
            th_count = 0
            for r2 in range(r + 1, n):
                body_cell = grid[r2][c]
                if body_cell["origin"] != (r2, c) or not body_cell["nonempty"]:
                    continue
                body_origin = origin_cells.get((r2, c))
                if body_origin is None:
                    continue
                if body_origin.name == "td":
                    td_count += 1
                elif body_origin.name == "th":
                    th_count += 1
            if td_count + th_count == 0:
                continue
            body_majority = "td" if td_count >= th_count else "th"
            checked += 1
            if body_majority != row_tag:
                inverted += 1
                if row_tag == "td" and body_majority == "th":
                    has_corner_stub = True
        return has_corner_stub and checked > 0 and inverted * 2 > checked

    # Find the first data row. A data row is one whose shape has no
    # structural feature that would mark it as a header:
    #   - col 0 is non-empty (typical row-label)
    #   - at least two non-empty logical cells (not a section divider)
    #   - every logical position at row r is an origin cell at row r
    #     (no rowspan copy from above pulling header content into body)
    #   - every origin cell at row r has rowspan == colspan == 1
    #     (no colspan group or rowspan marker signaling header role)
    # Plus, only at r == 0 (the literal first row):
    #   - row 0 is not strictly fuller than at least one body row below
    #     while every column it fills is covered by some body row
    #     (the fuller-than-body witness — see docstring)
    #   - row 0's cell tags are not inverted relative to body majority,
    #     with at least one corner-stub ``<td>`` versus body ``<th>``
    #     (the cell-type-inversion witness — see docstring)
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
        nonempty_count = nonempty_counts[r]
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
        if is_clean and r == 0:
            body_min = _body_min_nonempty(r)
            if (
                body_min >= 0
                and nonempty_count > body_min
                and _row_cols_covered_by_body(r)
            ):
                is_clean = False
            if is_clean and _is_inverted_relative_to_body(r):
                is_clean = False
        if is_clean:
            first_data_idx = r
            break

    if first_data_idx is None or first_data_idx == 0:
        return None

    # Header rows = non-divider, non-empty rows in the header region.
    header_row_indices = [
        r for r in range(first_data_idx) if sum(1 for c in grid[r] if c["nonempty"]) >= 2
    ]
    if not header_row_indices:
        return None

    # Body rows = non-divider rows from first_data_idx down.
    body_rows = [
        grid[r] for r in range(first_data_idx, n) if sum(1 for c in grid[r] if c["nonempty"]) >= 2
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
        all_empty_in_header = all(not grid[r][c]["nonempty"] for r in header_row_indices)
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
        all_empty_in_header = all(not grid[r][c]["nonempty"] for r in header_row_indices)
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
    6. Merge "hanging" description rows (e.g. Dates below items)
    """
    # --- Fix 0: Repair mismatched opening/closing tags ---
    # <td ...>text</th> and <th ...>text</td> cause html.parser to nest
    # subsequent sibling cells inside the unclosed element.
    # Fix by normalising closing tags to match their opener.
    # [^<]* restricts to plain-text content so we never span across tags.
    html = re.sub(r"(<td\b[^>]*>)([^<]*)</th>", r"\1\2</td>", html)
    html = re.sub(r"(<th\b[^>]*>)([^<]*)</td>", r"\1\2</th>", html)

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not isinstance(table, Tag):
        return html

    # --- Fix 9: Inline nested tables ---
    # Replace <table> elements inside cells with their flattened text
    # so the outer grid parser sees clean content instead of nested markup.
    for nested in table.find_all("table"):
        if not isinstance(nested, Tag):
            continue
        rows = nested.find_all("tr")
        lines = []
        for row in rows:
            if not isinstance(row, Tag):
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            texts = [c.get_text(strip=True) for c in cells]
            if any(texts):
                lines.append(", ".join(t for t in texts if t))
        nested.replace_with(NavigableString("; ".join(lines)))

    actual_rows = get_top_level_rows(table)
    if not actual_rows:
        return html

    # --- Fix 1: Move title row to caption ---
    first_meaningful_row = None
    first_meaningful_row_index = 0
    for idx, row in enumerate(actual_rows):
        cells = row.find_all(["td", "th"], recursive=False)
        if cells:
            first_meaningful_row = row
            first_meaningful_row_index = idx
            break

    if first_meaningful_row:
        cells = first_meaningful_row.find_all(["td", "th"], recursive=False)
        # Treat the first row as a title iff it is a single cell whose colspan
        # covers the full width of the remaining rows (width >= 2). This
        # captures 2-col and 3-col tables correctly without over-promoting.
        later_widths = [
            len(r.find_all(["td", "th"], recursive=False))
            for r in actual_rows[first_meaningful_row_index + 1 :]
        ]
        max_later_width = max(later_widths, default=0)
        first_cell_span = clamped_span(cells[0].get("colspan", 1))
        # If two or more rows in the table share this "single full-width
        # <th>" shape, they are a section-divider series (e.g. <tbody>
        # groups labelled "Personal" / "Work"), not a title. Treating the
        # first as a caption while the others survive into Fix 1b would
        # delete the matched siblings and leave the document with one
        # arbitrarily-promoted label and the rest erased.
        sibling_full_width_count = 0
        for r in actual_rows:
            r_cells = r.find_all(["td", "th"], recursive=False)
            if len(r_cells) != 1:
                continue
            only = r_cells[0]
            if only.name != "th":
                continue
            if clamped_span(only.get("colspan", 1)) >= max_later_width and max_later_width >= 2:
                sibling_full_width_count += 1
        is_section_divider_series = sibling_full_width_count >= 2
        if (
            len(cells) == 1
            and max_later_width >= 2
            and first_cell_span >= max_later_width
            and not is_section_divider_series
        ):
            title_text = cells[0].get_text(strip=True)
            caption = table.find("caption")
            if isinstance(caption, Tag):
                caption.string = title_text
            else:
                new_caption = soup.new_tag("caption")
                new_caption.string = title_text
                table.insert(0, new_caption)
            for i in range(first_meaningful_row_index + 1):
                actual_rows[i].decompose()
        actual_rows = get_top_level_rows(table)

    # --- Fix 1b: Mark section-divider rows as scope="rowgroup" ---
    # A <tr> whose sole cell is a <th> with colspan covering the grid
    # width is structurally a row-group label (e.g. "Personal" / "Work"
    # delimiting attribute-value blocks across two <tbody>s, or
    # "Operating Expenses" / "Non-Operating Items" partitioning a P&L
    # statement). The maze pathfinder already understands
    # <th scope="rowgroup"> as an ancestor label whose extent runs from
    # its origin row to the next rowgroup divider in the same column —
    # we just need to mark the cell honestly instead of deleting it.
    #
    # Two structural side-effects of the divider survive into downstream:
    #   1. The col-header walk (maze_pathfinder.find_headers_for_cell)
    #      already skips cells (and span copies) whose origin scope is
    #      "rowgroup", so the colspan-expanded divider can never be
    #      mistaken for a fabricated column header for the rows below.
    #   2. The row-header walk picks the divider up as a row-group
    #      ancestor — but only if col 0 of the body rows is itself a
    #      row-header column. A divider series is a structural witness
    #      that col 0 names individual rows within each group; promote
    #      <td> col-0 cells in non-divider, non-thead rows to
    #      <th scope="row"> so the maze can walk up from there.
    #
    # The earlier behaviour (row.decompose()) silently destroyed the
    # group label. Outputs scored gate_ok with no signal that context
    # had been lost — see issue #1.
    rowgroup_divider_rows: list = []
    if actual_rows:
        row_widths = [len(r.find_all(["td", "th"], recursive=False)) for r in actual_rows]
        max_width = max(row_widths, default=0)
        if max_width >= 2:
            for row in list(actual_rows):
                cells = row.find_all(["td", "th"], recursive=False)
                if len(cells) != 1:
                    continue
                cell = cells[0]
                if cell.name != "th":
                    continue
                colspan = clamped_span(cell.get("colspan", 1))
                if colspan >= max_width:
                    cell["scope"] = "rowgroup"
                    rowgroup_divider_rows.append(row)
        actual_rows = get_top_level_rows(table)

    # If any rowgroup dividers were marked, col 0 of the surrounding
    # rows is the row-label column by structural implication (the
    # divider partitions row identities, which must live in some
    # column; the canonical placement is col 0). Promote <td> col-0
    # cells outside <thead> and outside divider rows to
    # <th scope="row"> so the row-header walk picks up both the row
    # label and its rowgroup ancestor.
    if rowgroup_divider_rows:
        divider_set = {id(r) for r in rowgroup_divider_rows}
        for row in actual_rows:
            if id(row) in divider_set:
                continue
            if row.find_parent("thead") is not None:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            first = cells[0]
            if first.name == "td" and first.get_text(strip=True):
                first.name = "th"
                if not first.get("scope"):
                    first["scope"] = "row"

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
    if not table.find("thead") and actual_rows:
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
                logical_nonempty = sum(1 for cell in grid[r_idx] if cell["nonempty"])
                if logical_nonempty <= 1:
                    continue
                row = actual_rows[r_idx]
                for cell in row.find_all(["td", "th"], recursive=False):
                    if cell.name == "td":
                        cell.name = "th"
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
                    if cell.name == "td":
                        cell.name = "th"
                        if not cell.get("scope"):
                            cell["scope"] = "row"
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
                non_empty_cols = [c for c in range(len(row)) if row[c]["nonempty"]]
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
                if cell.name == "td":
                    cell.name = "th"
                cell["scope"] = "rowgroup"

    # --- Fix 7: Wrap header rows in <thead> ---
    # If table lacks <thead>, detect contiguous leading rows that are "header-like"
    # (all <th> cells, or all <th>/empty cells) and wrap them in <thead>.
    # This ensures downstream logic can rely on is_thead to identify column headers.
    if not table.find("thead") and actual_rows:
        header_rows = []
        seen_non_empty = False

        for row in actual_rows:
            cells = row.find_all(["td", "th"], recursive=False)

            # Ignore leading empty rows; do not treat them as headers
            if not cells and not seen_non_empty:
                continue

            if not cells and seen_non_empty:
                # Empty row after header block means header detection ends
                break

            seen_non_empty = True

            # A row carrying a <th scope="rowgroup"> is a body section
            # divider (Fix 1b marker), not a thead row. Stop the leading
            # header chain here so the divider stays in <tbody>; pulling
            # it into <thead> would mis-classify it as a column header.
            is_rowgroup_divider = any(
                cell.name == "th" and cell.get("scope") == "rowgroup" for cell in cells
            )
            if is_rowgroup_divider:
                break

            # A row is "header-like" if all cells are <th> or empty
            is_header_like = all(
                cell.name == "th" or not cell.get_text(strip=True) for cell in cells
            )

            if is_header_like:
                header_rows.append(row)
            else:
                # Stop at first non-header row
                break

        # Only wrap if we found header rows (and they're not ALL the rows)
        if header_rows and len(header_rows) < len(actual_rows):
            new_thead = soup.new_tag("thead")

            # Insert thead at the beginning of the table
            # (after caption if present)
            caption = table.find("caption")
            if isinstance(caption, Tag):
                caption.insert_after(new_thead)
            else:
                table.insert(0, new_thead)

            # Move header rows into thead
            for row in header_rows:
                row.extract()
                new_thead.append(row)

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
    thead = table.find("thead")
    if isinstance(thead, Tag):
        thead_rows = thead.find_all("tr", recursive=False)
        header_depth = len(thead_rows)

        if header_depth > 1:
            # Multi-row header structure suggests dimensional table
            tbody = table.find("tbody")
            if isinstance(tbody, Tag):
                active_rowspan = 0  # Track if a rowspan from above covers first column

                for row in tbody.find_all("tr", recursive=False):
                    if not isinstance(row, Tag):
                        continue
                    cells = row.find_all(["td", "th"], recursive=False)

                    if active_rowspan > 0:
                        # First column is covered by rowspan from above.
                        active_rowspan -= 1
                        continue
                    if not cells:
                        continue

                    first = cells[0]
                    if not isinstance(first, Tag):
                        continue
                    # Promote to row-header if not already. Fix 4 may have
                    # pre-promoted this cell via its stub-column path — in
                    # that case we still need to track the rowspan so the
                    # counter stays in sync with the grid, otherwise a cell
                    # at logical col > 0 in a subsequent row would be
                    # mistaken for the first-column cell.
                    if first.name == "td":
                        first.name = "th"
                        first["scope"] = "row"
                    rowspan = clamped_span(first.get("rowspan"))
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

    # --- Fix 2, 3: Iterate remaining rows ---
    actual_rows = get_top_level_rows(table)

    for row in actual_rows:
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells:
            continue

        # --- Fix 2: Fix <tfoot> row headers ---
        if row.find_parent("tfoot") and cells[0].name == "td":
            if clamped_span(cells[0].get("colspan", 1)) > 1:
                cells[0].name = "th"
                cells[0]["scope"] = "colgroup"

        # --- Fix 3: Move footer legends to tfoot ---
        if not row.find_parent("tfoot"):
            if len(cells) == 1:
                text = cells[0].get_text(strip=True).lower()
                if "legend" in text or "footnote" in text:
                    colspan = clamped_span(cells[0].get("colspan", 1))
                    if colspan >= 3:
                        tfoot = table.find("tfoot")
                        if not isinstance(tfoot, Tag):
                            tfoot = soup.new_tag("tfoot")
                            table.append(tfoot)
                        row.extract()
                        tfoot.append(row)
                        continue

    return str(soup)
