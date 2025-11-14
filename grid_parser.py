from typing import List, Dict
from bs4 import BeautifulSoup
import re


def clean_text(text: str) -> str:
    if not text:
        return ""
    
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = re.sub(r'<[^>]+>', ' ', text)
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

    # --- NEW "UNIVERSAL" HEADER LOGIC ---
    
    num_row_headers = 1
    data_start_row_idx = 0
    has_thead = table.find('thead') is not None

    if has_thead:
        # --- Logic for tables WITH <thead> ---
        thead = table.find('thead')
        data_start_row_idx = len(thead.find_all('tr', recursive=False))
        first_thead_row = thead.find('tr', recursive=False)
        
        if first_thead_row:
            num_row_headers = 0 # Reset to count
            header_cells = first_thead_row.find_all(['th', 'td'], recursive=False)
            for cell in header_cells:
                if int(cell.get('rowspan', 1)) > 1:
                    num_row_headers += 1
                else:
                    break # Stop when rowspans end
        
        if num_row_headers == 0:
            num_row_headers = 1 # Default to 1 if no rowspans
            
    else:
        # --- Logic for "Headless" tables (NO <thead>) ---
        
        # 1. Find the "main header row" (the one that defines row headers)
        # Heuristic: It's the first row with a rowspan > 1 in its first cell.
        main_header_row_idx = 0
        header_row_span = 1
        found_header_row = False
        
        for idx, row in enumerate(actual_rows):
            cells = row.find_all(['th', 'td'], recursive=False)
            if not cells or len(cells) == 1: # Skip empty or title rows
                continue
            
            first_cell_rowspan = int(cells[0].get('rowspan', 1))
            if first_cell_rowspan > 1:
                main_header_row_idx = idx
                header_row_span = first_cell_rowspan
                found_header_row = True
                
                # 2. Learn num_row_headers from this row
                num_row_headers = 0
                for cell in cells:
                    if int(cell.get('rowspan', 1)) == header_row_span:
                        num_row_headers += 1
                    else:
                        break # Stop when rowspans don't match
                break
        
        # 3. Define the header/data boundaries
        if found_header_row:
            # Data starts *after* this row's rowspan block
            data_start_row_idx = main_header_row_idx + header_row_span
        else:
            # Fallback: Find first non-title, non-empty row
            for idx, row in enumerate(actual_rows):
                cells = row.find_all(['th', 'td'], recursive=False)
                if len(cells) > 1:
                    data_start_row_idx = idx + 1
                    num_row_headers = 1
                    break
            if data_start_row_idx == 0: data_start_row_idx = 1
            
    # --- END NEW HEURISTIC ---

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

    # Phase 2: Create empty grid
    grid = [[None for _ in range(max_cols)] for _ in range(len(actual_rows))]
    
    # Phase 3: Fill grid
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        logical_col = 0
        
        # A row is a "header row" if it's before the data start
        is_header_row = (row_idx < data_start_row_idx) and not has_thead
        
        for cell in cells:
            while logical_col < max_cols and grid[row_idx][logical_col] is not None:
                logical_col += 1
            if logical_col >= max_cols:
                break
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # --- Universal `cell_type` logic ---
            cell_type = cell.name
            is_body_row = not (cell.find_parent('thead') or cell.find_parent('tfoot'))
            
            # Heuristic 1: It's a header if it's in a "header row" (for headless)
            if is_header_row and cell.name == 'td':
                cell_type = 'th'
            
            # Heuristic 2: It's a row header if it's in the first N columns
            if (is_body_row and 
                cell.name == 'td' and 
                logical_col < num_row_headers):
                cell_type = 'th'
            # --- END ---

            is_footer = cell.find_parent('tfoot') is not None
            is_thead = cell.find_parent('thead') is not None

            cell_data = {
                'text': clean_text(cell.get_text(separator=' ')),
                'type': cell_type,
                'rowspan': rowspan,
                'colspan': colspan,
                'scope': cell.get('scope'),
                'is_footer': is_footer,
                'is_thead': is_thead,
                'has_thead': has_thead 
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
                                'is_span_copy': True,
                                'origin': (row_idx, logical_col)
                            }
                            grid[target_row][target_col] = span_ref
            logical_col += colspan
    
    # Phase 4: Fill gaps
    for r in range(len(grid)):
        for c in range(max_cols):
            if grid[r][c] is None:
                grid[r][c] = {'text': '', 'type': 'td', 'rowspan': 1, 'colspan': 1, 'has_thead': has_thead}
    
    return grid