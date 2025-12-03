from typing import List, Dict
from bs4 import BeautifulSoup
import re


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
    
    num_row_headers = 1
    data_start_row_idx = 0
    has_thead = table.find('thead') is not None

    if has_thead:
        # --- Logic for tables WITH <thead> ---
        thead = table.find('thead')
        data_start_row_idx = len(thead.find_all('tr', recursive=False))
        
        # For tables with <thead>, default to 1 row header column
        # This is the safest assumption - most tables have a single identifier column
        num_row_headers = 1

    else:
        # --- Logic for "Headless" tables (NO <thead>) ---

        # Step 1: Prefer an explicit header row that uses <th>
        header_row_idx = None
        for idx, row in enumerate(actual_rows):
            cells = row.find_all(['th', 'td'], recursive=False)
            if not cells or len(cells) == 1:
                # Skip empty or title rows
                continue

            has_th = any(cell.name == 'th' for cell in cells)
            all_th_or_empty = all(
                (cell.name == 'th') or not cell.get_text(strip=True)
                for cell in cells
            )

            if has_th and all_th_or_empty:
                header_row_idx = idx
                break

        if header_row_idx is not None:
            # We have a clear header row made of <th>
            main_header_row_idx = header_row_idx

            # If some cells in this header row span multiple body rows,
            # use the maximum rowspan to determine how many header rows exist.
            cells = actual_rows[main_header_row_idx].find_all(['th', 'td'], recursive=False)
            header_row_span = max(int(cell.get('rowspan', 1)) for cell in cells) or 1

            # Learn num_row_headers:
            # If there is vertical structure (rowspan > 1), treat all leading cells
            # with that rowspan as row-header columns (like Section / Claim event(s)).
            # Otherwise, default to a single row-header column.
            if header_row_span > 1:
                num_row_headers = 0
                for cell in cells:
                    if int(cell.get('rowspan', 1)) == header_row_span:
                        num_row_headers += 1
                    else:
                        break
                if num_row_headers == 0:
                    num_row_headers = 1
            else:
                num_row_headers = 1

            # Data starts after the header row span
            data_start_row_idx = main_header_row_idx + header_row_span

        else:
            # Step 2: Fallback – no explicit <th> header row.
            # Re-use the original rowspan-based heuristic on the first cell.
            main_header_row_idx = 0
            header_row_span = 1
            found_header_row = False

            for idx, row in enumerate(actual_rows):
                cells = row.find_all(['th', 'td'], recursive=False)
                if not cells or len(cells) == 1:
                    continue

                first_cell_rowspan = int(cells[0].get('rowspan', 1))
                if first_cell_rowspan > 1:
                    main_header_row_idx = idx
                    header_row_span = first_cell_rowspan
                    found_header_row = True

                    num_row_headers = 0
                    for cell in cells:
                        if int(cell.get('rowspan', 1)) == header_row_span:
                            num_row_headers += 1
                        else:
                            break
                    break

            if found_header_row:
                data_start_row_idx = main_header_row_idx + header_row_span
            else:
                # Last-resort fallback: first non-title, non-empty row,
                # with a single row-header column.
                for idx, row in enumerate(actual_rows):
                    cells = row.find_all(['th', 'td'], recursive=False)
                    if len(cells) > 1:
                        data_start_row_idx = idx + 1
                        num_row_headers = 1
                        break
                if data_start_row_idx == 0:
                    data_start_row_idx = 1

    # --- END HEADER HEURISTIC ---

    # --- KEY-VALUE TABLE DETECTION ---
    # Detect simple key-value tables (no thead, 2 columns, th+td pattern)
    # This prevents row headers from being treated as column headers
    is_key_value_table = False
    if not has_thead:
        # Check if ALL rows follow the key-value pattern
        is_key_value_table = True
        for row in actual_rows:
            cells = row.find_all(['th', 'td'], recursive=False)
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
            if int(cells[0].get('colspan', 1)) > 1 or int(cells[0].get('rowspan', 1)) > 1:
                is_key_value_table = False
                break
            if int(cells[1].get('colspan', 1)) > 1 or int(cells[1].get('rowspan', 1)) > 1:
                is_key_value_table = False
                break
    # --- END KEY-VALUE DETECTION ---

    # Phase 1: Calculate dimensions
    max_cols = 0
    occupied = {}
    
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        logical_col = 0
        
        for cell in cells:
            while (row_idx, logical_col) in occupied:
                logical_col += 1
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            for r in range(rowspan):
                for c in range(colspan):
                    occupied[(row_idx + r, logical_col + c)] = True
            logical_col += colspan
        max_cols = max(max_cols, logical_col)
    
    if max_cols == 0:
        return []
    
    # Clamp inferred structure to valid ranges
    num_row_headers = max(0, min(num_row_headers, max_cols))
    data_start_row_idx = max(0, min(data_start_row_idx, len(actual_rows)))

    # Phase 2: Create empty grid
    grid = [[None for _ in range(max_cols)] for _ in range(len(actual_rows))]
    
    # Phase 3: Fill grid
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        logical_col = 0
        
        # A row is a "header row" if it's before the data start (headless only)
        is_header_row = (row_idx < data_start_row_idx) and not has_thead
        
        for cell in cells:
            while logical_col < max_cols and grid[row_idx][logical_col] is not None:
                logical_col += 1
            if logical_col >= max_cols:
                break
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # Universal cell_type logic
            cell_type = cell.name
            is_body_row = not (cell.find_parent('thead') or cell.find_parent('tfoot'))
            
            # Heuristic 1: header row (for headless)
            # Skip this for key-value tables - they don't have header rows
            if is_header_row and cell.name == 'td' and not is_key_value_table:
                cell_type = 'th'
            
            # Heuristic 2: row header in first N columns
            # Skip this for key-value tables - already handled by scope setting
            if (
                is_body_row and 
                cell.name == 'td' and 
                logical_col < num_row_headers and
                not is_key_value_table
            ):
                cell_type = 'th'

            is_footer = cell.find_parent('tfoot') is not None
            is_thead = cell.find_parent('thead') is not None

            # Override scope for key-value tables
            cell_scope = cell.get('scope')
            if is_key_value_table and logical_col == 0 and cell_type == 'th':
                cell_scope = 'row'

            cell_data = {
                'text': clean_text(cell.get_text(separator=' ')),
                'type': cell_type,
                'rowspan': rowspan,
                'colspan': colspan,
                'scope': cell_scope,
                'is_footer': is_footer,
                'is_thead': is_thead,
                'has_thead': has_thead,
                'is_header_row': is_header_row
                
            }
            
            for r_offset in range(rowspan):
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
                            }
                            grid[target_row][target_col] = span_ref
            logical_col += colspan
    
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