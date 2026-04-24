from typing import List, Dict
from bs4 import NavigableString
import re

from .simple_repair import detect_header_block
from .spans import assert_grid_size, clamped_span


def clean_text(text: str) -> str:
    if not text:
        return ""
    
    # Basic HTML entity cleanup
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')

    # Strip residual HTML tags if any slipped through
    text = re.sub(r'<[^>]+>', ' ', text)

    # 1) Fix double dollar patterns like "$$200,000" or "S$$3,000"
    #    Turn them into "$200,000" or "S$3,000"
    text = re.sub(r'\bS\$\$(\d)', r'S$\1', text)
    text = re.sub(r'\$\$(\d)', r'$\1', text)

    # 2) Remove a trailing standalone "$" after a word/number
    #    e.g. "per Sickness$" -> "per Sickness"
    text = re.sub(r'(\w)\$(\s|$)', r'\1\2', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def _is_textualish(text: str) -> bool:
    """Return True when text carries alphabetic descriptor content.

    Uses ``str.isalpha`` on individual characters so the check is Unicode-aware
    — a cell containing any letter in any writing system (Latin, Cyrillic, CJK,
    Arabic, Devanagari, etc.) counts as textual. This is the single content
    signal the parser relies on; the alphabetic-vs-numeric distinction is
    universal across writing systems ("letters label, digits measure").
    """
    if not text:
        return False
    return any(ch.isalpha() for ch in text)


def get_row_cells(row, table) -> List:
    """
    Return logical cells for a row, including malformed sibling cells that may
    be nested due to broken closing tags, while excluding nested-table cells.
    """
    cells = row.find_all(['td', 'th'])
    return [
        cell for cell in cells
        if cell.find_parent('tr') is row and cell.find_parent('table') is table
    ]


def extract_cell_text(cell) -> str:
    """
    Extract text from a logical cell while excluding text from malformed nested
    sibling cells that can appear after HTML recovery.
    """
    parts: List[str] = []
    for node in cell.descendants:
        if not isinstance(node, NavigableString):
            continue

        text = str(node).strip()
        if not text:
            continue

        parent = node.parent
        if parent is None:
            continue

        if parent.name in ('td', 'th'):
            nearest_cell = parent
        else:
            nearest_cell = parent.find_parent(['td', 'th'])

        if nearest_cell is cell:
            parts.append(text)

    return clean_text(" ".join(parts))


def parse_table_to_grid(table) -> List[List[Dict]]:
    # 1. Get all top-level rows
    all_rows_in_dom = table.find_all('tr')
    actual_rows = []
    for row in all_rows_in_dom:
        if row.find_parent('table') is table:
            actual_rows.append(row)
    if not actual_rows:
        return []

    # --- UNIVERSAL HEADER LOGIC ---
    
    data_start_row_idx = 0
    has_thead = table.find('thead') is not None

    if has_thead:
        # --- Logic for tables WITH <thead> ---
        thead = table.find('thead')
        data_start_row_idx = len(thead.find_all('tr', recursive=False))

    else:
        # --- Logic for "Headless" tables (NO <thead>) ---

        # Step 1: Prefer an explicit header row that uses <th>.
        # A column-header row has <th> cells whose scope is NOT 'row':
        # scope='row' marks a row-stub header (row label), not a
        # column label, so those cells cannot make a row qualify as the
        # primary column-header row. Otherwise a single mid-body
        # <th scope='row'> summary row (e.g. an explicit-markup totals
        # line like <tr><th scope="row">Total</th>...</tr>) would be
        # mistaken for the table header.
        def _is_col_header_cell(cell):
            return cell.name == 'th' and cell.get('scope') != 'row'

        header_row_idx = None
        for idx, row in enumerate(actual_rows):
            cells = get_row_cells(row, table)
            if not cells or len(cells) == 1:
                # Skip empty or title rows
                continue

            has_col_th = any(_is_col_header_cell(cell) for cell in cells)
            all_col_th_or_empty = all(
                _is_col_header_cell(cell) or not cell.get_text(strip=True)
                for cell in cells
            )

            if has_col_th and all_col_th_or_empty:
                header_row_idx = idx
                break

        if header_row_idx is not None:
            # We have a clear header row made of <th>
            main_header_row_idx = header_row_idx

            # If some cells in this header row span multiple body rows,
            # use the maximum rowspan to determine how many header rows exist.
            cells = get_row_cells(actual_rows[main_header_row_idx], table)
            header_row_span = max(clamped_span(cell.get('rowspan', 1)) for cell in cells) or 1

            # Data starts after the header row span
            data_start_row_idx = main_header_row_idx + header_row_span

        else:
            # Step 2: Fallback – no explicit <th> header row.
            # Re-use the original rowspan-based heuristic on the first cell.
            main_header_row_idx = 0
            header_row_span = 1
            found_header_row = False

            for idx, row in enumerate(actual_rows):
                cells = get_row_cells(row, table)
                if not cells or len(cells) == 1:
                    continue

                first_cell_rowspan = clamped_span(cells[0].get('rowspan', 1))
                if first_cell_rowspan > 1:
                    main_header_row_idx = idx
                    header_row_span = first_cell_rowspan
                    found_header_row = True
                    break

            if found_header_row:
                data_start_row_idx = main_header_row_idx + header_row_span
            else:
                # Step 3: structural fallback via the same universal rule
                # that simple_repair.Fix 4 uses. This path runs only when
                # simple_repair didn't promote (e.g. upstream repairs left
                # the table in a shape Fix 4 couldn't normalize) — it
                # keeps the parser aligned with the repair's structural
                # definition rather than reintroducing a separate
                # "row 0 all non-empty" heuristic. If no header block is
                # confidently identified, leave data_start_row_idx = 0 so
                # every row is treated as data and the confidence gate
                # decides whether to emit rules or flat.
                detection = detect_header_block(actual_rows)
                if detection is not None:
                    data_start_row_idx = detection[0]
                else:
                    data_start_row_idx = 0

    # --- END HEADER HEURISTIC ---

    # --- KEY-VALUE TABLE DETECTION ---
    # Detect simple key-value tables (no thead, 2 columns, th+td pattern)
    # This prevents row headers from being treated as column headers
    is_key_value_table = False
    if not has_thead:
        # Check if ALL rows follow the key-value pattern
        is_key_value_table = True
        for row in actual_rows:
            cells = get_row_cells(row, table)
            # Skip empty rows
            if not cells:
                continue
            # Must have exactly 2 cells
            if len(cells) != 2:
                is_key_value_table = False
                break
            # First must be th, second must be td
            if cells[0].name != 'th' or cells[1].name != 'td':
                is_key_value_table = False
                break
            # No colspan/rowspan (keep it simple)
            if clamped_span(cells[0].get('colspan', 1)) > 1 or clamped_span(cells[0].get('rowspan', 1)) > 1:
                is_key_value_table = False
                break
            if clamped_span(cells[1].get('colspan', 1)) > 1 or clamped_span(cells[1].get('rowspan', 1)) > 1:
                is_key_value_table = False
                break
    # Key-value tables have no header rows — every row is data.
    if is_key_value_table:
        data_start_row_idx = 0
    # --- END KEY-VALUE DETECTION ---

    # Phase 1: Calculate dimensions
    max_cols = 0
    occupied = {}

    for row_idx, row in enumerate(actual_rows):
        cells = get_row_cells(row, table)
        logical_col = 0

        for cell in cells:
            while (row_idx, logical_col) in occupied:
                logical_col += 1
            rowspan = clamped_span(cell.get('rowspan', 1))
            colspan = clamped_span(cell.get('colspan', 1))
            assert_grid_size(len(actual_rows), logical_col + colspan)
            for r in range(min(rowspan, len(actual_rows) - row_idx)):
                for c in range(colspan):
                    occupied[(row_idx + r, logical_col + c)] = True
            logical_col += colspan
        max_cols = max(max_cols, logical_col)

    if max_cols == 0:
        return []

    assert_grid_size(len(actual_rows), max_cols)
    
    # Clamp inferred structure to valid ranges
    data_start_row_idx = max(0, min(data_start_row_idx, len(actual_rows)))

    # Phase 2: Create empty grid
    grid = [[None for _ in range(max_cols)] for _ in range(len(actual_rows))]
    
    # Phase 3: Fill grid
    for row_idx, row in enumerate(actual_rows):
        cells = get_row_cells(row, table)
        logical_col = 0
        
        # A row is a "header row" if it's before the data start (headless only)
        is_header_row = (row_idx < data_start_row_idx) and not has_thead
        
        for cell in cells:
            while logical_col < max_cols and grid[row_idx][logical_col] is not None:
                logical_col += 1
            if logical_col >= max_cols:
                break
            
            rowspan = clamped_span(cell.get('rowspan', 1))
            colspan = clamped_span(cell.get('colspan', 1))

            # Universal cell_type logic
            cell_type = cell.name
            is_body_row = not (cell.find_parent('thead') or cell.find_parent('tfoot'))

            # Heuristic 1: header row (for headless)
            # Skip this for key-value tables - they don't have header rows
            if is_header_row and cell.name == 'td' and not is_key_value_table:
                cell_type = 'th'

            # Heuristic 1b: <td> cells inside <thead> are structural headers
            # regardless of tag. Word / Markdown-to-HTML converters, and many
            # CMS outputs, emit <thead><tr><td><b>Header</b></td></tr></thead>
            # — the <thead> wrapper is the authoritative signal. Promote to
            # <th> so downstream header-walking treats these as column
            # headers.
            if cell.name == 'td' and cell.find_parent('thead') is not None:
                cell_type = 'th'

            is_footer = cell.find_parent('tfoot') is not None
            is_thead = cell.find_parent('thead') is not None

            # Override scope for key-value tables
            cell_scope = cell.get('scope')
            if is_key_value_table and logical_col == 0 and cell_type == 'th':
                cell_scope = 'row'

            cell_data = {
                'text': extract_cell_text(cell),
                'type': cell_type,
                'rowspan': rowspan,
                'colspan': colspan,
                'scope': cell_scope,
                'is_footer': is_footer,
                'is_thead': is_thead,
                'has_thead': has_thead,
                'is_header_row': is_header_row,
                'header_depth': data_start_row_idx if has_thead else 0
            }
            
            for r_offset in range(min(rowspan, len(grid) - row_idx)):
                for c_offset in range(colspan):
                    target_row = row_idx + r_offset
                    target_col = logical_col + c_offset
                    if target_row < len(grid) and target_col < max_cols:
                        if r_offset == 0 and c_offset == 0:
                            grid[target_row][target_col] = cell_data
                        else:
                            span_ref = {
                                'text': cell_data['text'],
                                'type': cell_data['type'],
                                'rowspan': 1,
                                'colspan': 1,
                                'scope': cell_data.get('scope'),
                                'is_footer': cell_data['is_footer'],
                                'is_thead': cell_data['is_thead'],
                                'has_thead': cell_data['has_thead'],
                                'is_header_row': cell_data['is_header_row'],
                                'is_span_copy': True,
                                'origin': (row_idx, logical_col),
                                'header_depth': cell_data.get('header_depth', 0),
                            }
                            grid[target_row][target_col] = span_ref
            logical_col += colspan
    
    # Phase 3.5: Promote dimensional body columns to row headers.
    #
    # Universal structural signals:
    #   A) Rowspan signal: leading body columns with rowspan>1 origins are
    #      dimensional/grouping columns.
    #   B) Unlabeled descriptor signal: a body column has non-empty cells but
    #      no non-empty <thead> header text at that column and is text-like.
    #
    # Signal B is guarded to avoid over-promotion: only contiguous descriptor
    # columns from the left edge (or directly after a promoted descriptor
    # column) are promoted.
    if has_thead and data_start_row_idx < len(grid):
        # --- Per-column stats over body origins ---
        body_nonempty = [0] * max_cols
        body_textual = [0] * max_cols
        body_th = [0] * max_cols
        has_thead_text = [False] * max_cols

        for c in range(max_cols):
            for r in range(len(grid)):
                cell = grid[r][c]
                if not cell or cell.get('is_span_copy'):
                    continue
                txt = (cell.get('text') or '').strip()
                if cell.get('is_thead', False):
                    if txt:
                        has_thead_text[c] = True
                    continue
                if r < data_start_row_idx:
                    continue
                if cell.get('is_footer', False):
                    continue
                if not txt:
                    continue
                body_nonempty[c] += 1
                if cell.get('type') == 'th':
                    body_th[c] += 1
                if _is_textualish(txt):
                    body_textual[c] += 1

        def _descriptor_like(col: int) -> bool:
            # A column is "descriptor-like" iff strictly more of its
            # non-empty body cells are textual than non-textual. Using a
            # strict-majority count (integer comparison) instead of a
            # fixed ratio keeps the rule deterministic and aligned with
            # the stub-column rule in simple_repair.detect_header_block.
            n = body_nonempty[col]
            if n < 2:
                return False
            return body_textual[col] * 2 > n

        # --- Signal A: rowspan-driven leading dimensional columns ---
        body_dimensional = []
        for c in range(max_cols):
            col_has_rowspan = False
            for r in range(data_start_row_idx, len(grid)):
                cell = grid[r][c]
                if (cell and not cell.get('is_span_copy')
                        and cell.get('rowspan', 1) > 1):
                    col_has_rowspan = True
                    break
            if col_has_rowspan:
                body_dimensional.append(c)
            else:
                break  # Stop at first non-dimensional column

        # --- Signal B: full-depth header columns (multi-row headers) ---
        if data_start_row_idx >= 2:
            full_depth_count = 0
            for c in range(max_cols):
                cell = grid[0][c]
                if (cell and cell.get('is_thead')
                        and not cell.get('is_span_copy')
                        and cell.get('rowspan', 1) == data_start_row_idx):
                    full_depth_count += 1
                else:
                    break  # Stop at first non-full-depth header
            # Cap body signal at the header-derived count
            body_dimensional = body_dimensional[:full_depth_count]

        promote_cols = set()
        if len(body_dimensional) >= 2:
            promote_cols.update(body_dimensional)
        elif len(body_dimensional) == 1:
            c0 = body_dimensional[0]
            if not has_thead_text[c0]:
                promote_cols.add(c0)

        # Seed only strong pre-promotions from upstream repair on unlabeled
        # columns. A single summary-row <th> should not turn a labeled data
        # column into a row-header column.
        for c in range(max_cols):
            if (
                body_nonempty[c] >= 2
                and not has_thead_text[c]
                and (body_th[c] / max(1, body_nonempty[c])) >= 0.60
            ):
                promote_cols.add(c)

        # --- Signal B: unlabeled descriptor columns ---
        for c in range(max_cols):
            if c in promote_cols:
                continue
            if has_thead_text[c]:
                continue
            if not _descriptor_like(c):
                continue

            left_is_dimensional = (c == 0) or ((c - 1) in promote_cols)
            left_is_descriptor = (c > 0) and _descriptor_like(c - 1)
            if not (left_is_dimensional or left_is_descriptor):
                continue
            promote_cols.add(c)

        if promote_cols:
            for c in sorted(promote_cols):
                for r in range(data_start_row_idx, len(grid)):
                    cell = grid[r][c]
                    if not cell or cell.get('is_footer', False):
                        continue
                    if cell['type'] == 'td' and (cell.get('text') or '').strip():
                        cell['type'] = 'th'
                        if not cell.get('scope'):
                            cell['scope'] = 'row'

    # Phase 4: Fill gaps
    for r in range(len(grid)):
        for c in range(max_cols):
            if grid[r][c] is None:
                grid[r][c] = {
                    'text': '',
                    'type': 'td',
                    'rowspan': 1,
                    'colspan': 1,
                    'has_thead': has_thead,
                }

    return grid
