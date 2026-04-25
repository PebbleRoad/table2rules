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

            # Locate the origin for scope and rowspan lookup.
            if cell.get("is_span_copy", False):
                origin = cell.get("origin", (r, header_col))
                origin_cell = grid[origin[0]][origin[1]]
            else:
                origin = (r, header_col)
                origin_cell = cell

            if scope == "rowgroup":
                # A rowgroup header ancestors rows within its extent:
                #   rowspan > 1  → extent = [origin_row, origin_row + rowspan - 1]
                #                  (the rowspan itself bounds the group, as in
                #                  a <th scope="rowgroup" rowspan="2"> pattern)
                #   rowspan == 1 → extent = [origin_row, next_rowgroup - 1]
                #                  (a single-cell divider row like a FinTabNet
                #                  year label runs until the next such divider
                #                  in the same column)
                origin_row, origin_col = origin
                origin_rowspan = origin_cell.get("rowspan", 1)
                if origin_rowspan > 1:
                    extent_end = origin_row + origin_rowspan - 1
                else:
                    extent_end = len(grid) - 1
                    for rr in range(origin_row + 1, len(grid)):
                        other = grid[rr][origin_col]
                        if (
                            other
                            and not other.get("is_span_copy", False)
                            and other.get("scope") == "rowgroup"
                        ):
                            extent_end = rr - 1
                            break
                if row > extent_end:
                    continue
            else:
                # Non-scope-rowgroup <th> cells outside thead are only
                # accepted from the explicit header block (headless
                # tables where the header detection promoted a row).
                is_header_row = cell.get("is_header_row", False)
                if not is_header_row:
                    continue

            if origin not in seen_origins:
                seen_origins.add(origin)
                # Insert at the beginning to maintain hierarchy
                row_headers.insert(row_header_columns.index(header_col), cell["text"])

    return row_headers, col_headers
