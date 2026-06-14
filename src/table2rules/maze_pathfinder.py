from typing import Dict, List, Tuple


def find_headers_for_cell(
    grid: List[List[Dict]], row: int, col: int
) -> Tuple[List[str], List[str]]:
    """
    Navigate the maze from this cell to find all headers.

    Returns row_headers and col_headers separately.

    Rules:
    1. Walk LEFT on same row - collect all <th> cells
    2. Walk UP from data cell's column - collect all <th> cells
    3. Walk UP from each row header's column - collect their column headers
    """
    if not grid or not grid[0]:
        return [], []

    row_headers = []
    col_headers = []
    seen_origins = set()
    row_header_columns = []  # Track which columns have row headers

    # Get table properties from the first cell
    has_thead = grid[0][0].get("has_thead", False)

    # --- 1. Walk LEFT on same row ---
    for c in range(col - 1, -1, -1):
        cell = grid[row][c]

        if not cell or not cell.get("text", "").strip():
            continue

        if cell["type"] == "th":
            if cell.get("is_span_copy", False):
                origin = cell.get("origin", (row, c))
            else:
                origin = (row, c)

            if origin not in seen_origins:
                seen_origins.add(origin)
                row_headers.append(cell["text"])
                row_header_columns.append(c)  # Remember this column

    row_headers.reverse()
    row_header_columns.reverse()

    # --- 2. Walk UP - collect headers for the data cell itself ---
    for r in range(row - 1, -1, -1):
        cell = grid[r][col]

        if not cell or not cell.get("text", "").strip():
            continue

        if cell["type"] == "th":
            # Universal "Walk UP" Logic:
            # If a <thead> exists, only accept headers from it.
            if has_thead and not cell.get("is_thead", False):
                continue

            # Skip row-scoped headers
            scope = cell.get("scope", "")
            if scope in ("row", "rowgroup"):
                continue

            if cell.get("is_span_copy", False):
                origin = cell.get("origin", (r, col))
                origin_row, origin_col = origin
                origin_cell = grid[origin_row][origin_col]
                origin_scope = origin_cell.get("scope", "")

                if origin_scope in ("row", "rowgroup"):
                    continue

                colspan = origin_cell.get("colspan", 1)
                if origin_col <= col < origin_col + colspan:
                    if origin not in seen_origins:
                        seen_origins.add(origin)
                        col_headers.append(cell["text"])
            else:
                origin = (r, col)
                if origin not in seen_origins:
                    seen_origins.add(origin)
                    col_headers.append(cell["text"])

    col_headers.reverse()

    # --- 3. Walk UP from each row header column ---
    # Find ancestor headers for the row headers (e.g. "Region" for "North").
    # Peer row labels are skipped via the scope='row' check below; group
    # ancestors are bounded by their rowspan/divider extent. No text-level
    # check is needed.
    for header_col in row_header_columns:
        for r in range(row - 1, -1, -1):
            cell = grid[r][header_col]

            if not cell or not cell.get("text", "").strip():
                continue

            if cell["type"] != "th":
                continue

            # Never include <thead> cells in row header context —
            # thead cells are column headers, not row-header hierarchy.
            if cell.get("is_thead", False):
                continue

            scope = cell.get("scope", "")

            # Skip column-scoped headers — they name the column.
            if scope in ("col", "colgroup"):
                continue

            # scope='row' = peer row label (not an ancestor). Skip.
            if scope == "row":
                continue

            # scope='rowgroup' bands are handled uniformly in Step 4 (which also
            # reaches bands spanning the data column when the row-label is
            # empty), so they can be ordered across columns by nesting level.
            if scope == "rowgroup":
                continue

            # Non-scope-rowgroup <th> cells outside thead are only accepted from
            # the explicit header block (headless tables where header detection
            # promoted a row).
            if not cell.get("is_header_row", False):
                continue

            # Locate the origin for dedup.
            if cell.get("is_span_copy", False):
                origin = cell.get("origin", (r, header_col))
            else:
                origin = (r, header_col)

            if origin not in seen_origins:
                seen_origins.add(origin)
                # Insert at the beginning to maintain hierarchy
                row_headers.insert(row_header_columns.index(header_col), cell["text"])

    # --- 4. Row-group bands ---
    # A band / group header ancestors the data rows within its extent. Bands are
    # collected from the data cell's own column AND every row-label column: the
    # own column reaches bands that span the value region even when this row's
    # label cell is empty (which would otherwise drop the band, e.g. an
    # unlabeled continuation row under a group divider); the row-label columns
    # reach narrow stub-column dividers (a FinTabNet year label). Extent is
    # bounded by COLSPAN — a band ends at the next band whose span is equal or
    # wider — so a narrower inner group header does not close an outer one.
    # Bands are ordered topmost-first (origin row ascending) and prepended, so
    # the row path reads outer-band > inner-group > row-labels, mirroring the
    # multi-level column path.
    #
    # A *label-only* band (one carrying an explicit ``rowgroup_extent_end``)
    # groups a ROW RANGE, so it must reach every value row in its extent
    # regardless of which column its single label cell sits in — e.g. a numbered
    # schedule whose group header is in the line-number/stub column while the
    # sub-rows leave that column empty and carry their identity in a different
    # column. Such bands are therefore scanned across ALL columns. Full-width and
    # source ``scope="rowgroup"`` bands keep the column-restricted scan (own
    # column + row-label columns) so unrelated stub dividers don't cross-attach.
    own_cols = {col, *row_header_columns}
    bands: List[Tuple[int, str]] = []  # (origin_row, text)
    for scan_col in range(len(grid[0])):
        for r in range(row - 1, -1, -1):
            cell = grid[r][scan_col]
            if not cell or not cell.get("text", "").strip():
                continue
            if cell["type"] != "th" or cell.get("is_thead", False):
                continue
            if cell.get("scope") != "rowgroup":
                continue
            if cell.get("is_span_copy", False):
                origin = cell.get("origin", (r, scan_col))
                origin_cell = grid[origin[0]][origin[1]]
            else:
                origin = (r, scan_col)
                origin_cell = cell
            # A column-restricted band (no stored extent) is only honored from
            # the value's own column or a row-label column; a label-only band
            # (stored extent) is honored from any column.
            if origin_cell.get("rowgroup_extent_end") is None and scan_col not in own_cols:
                continue
            if origin in seen_origins:
                continue
            origin_row, origin_col = origin
            my_colspan = origin_cell.get("colspan", 1)
            origin_rowspan = origin_cell.get("rowspan", 1)
            stored_extent = origin_cell.get("rowgroup_extent_end")
            if stored_extent is not None:
                # Label-only bands carry an explicit extent (the run of value
                # rows they group, bounded by the next stack or section band),
                # because their colspan=1 label cannot encode nesting depth the
                # way a full-width band's width does.
                extent_end = stored_extent
            elif origin_rowspan > 1:
                extent_end = origin_row + origin_rowspan - 1
            else:
                extent_end = len(grid) - 1
                for rr in range(origin_row + 1, len(grid)):
                    other = grid[rr][origin_col]
                    if (
                        other
                        and not other.get("is_span_copy", False)
                        and other.get("scope") == "rowgroup"
                        and other.get("colspan", 1) >= my_colspan
                    ):
                        extent_end = rr - 1
                        break
            if row > extent_end:
                continue
            seen_origins.add(origin)
            bands.append((origin_row, cell["text"]))
    bands.sort(key=lambda b: b[0])
    row_headers[:0] = [text for _row, text in bands]

    return row_headers, col_headers
