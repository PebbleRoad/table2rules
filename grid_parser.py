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
    # NEW LOGIC:
    # 1. Find ALL <tr> tags, even in nested tables.
    all_rows_in_dom = table.find_all('tr')
    if not all_rows_in_dom:
        return []
    
    # 2. Filter this list to get only rows that are
    #    DIRECT children of this table (not a nested table).
    actual_rows = []
    for row in all_rows_in_dom:
        if row.find_parent('table') is table:
            actual_rows.append(row)

    if not actual_rows:
        return []

    # --- NEW: Learn num_row_headers from the <thead> ---
    num_row_headers = 0
    thead = table.find('thead')
    if thead:
        first_thead_row = thead.find('tr', recursive=False)
        if first_thead_row:
            header_cells = first_thead_row.find_all(['th', 'td'], recursive=False)
            for cell in header_cells:
                if int(cell.get('rowspan', 1)) > 1:
                    num_row_headers += 1
                else:
                    # Stop counting if we hit a non-rowspan header
                    break
    
    # If we couldn't learn from thead, default to 1 (our old heuristic)
    if num_row_headers == 0:
        num_row_headers = 1
    # --- END NEW ---

    # Phase 1: Calculate dimensions (using our filtered list)
    max_cols = 0
    occupied = {}
    
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False) # This is correct
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
        cells = row.find_all(['td', 'th'], recursive=False) # This is correct
        logical_col = 0
        
        for cell in cells:
            while logical_col < max_cols and grid[row_idx][logical_col] is not None:
                logical_col += 1
            
            if logical_col >= max_cols:
                break
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # --- NEW: The "Pure" Fix ---
            # Use logical_col to convert <td> to <th>
            cell_type = cell.name
            if (cell.find_parent('tbody') and 
                cell.name == 'td' and 
                logical_col < num_row_headers):
                
                cell_type = 'th'
            # --- END NEW ---

            is_footer = False
            if cell.find_parent('tfoot'):
                is_footer = True

            is_thead = False
            if cell.find_parent('thead'):
                is_thead = True

            cell_data = {
                'text': clean_text(cell.get_text(separator=' ')),
                'type': cell_type,  # <-- Use the new variable
                'rowspan': rowspan,
                'colspan': colspan,
                'scope': cell.get('scope'),
                'is_footer': is_footer,
                'is_thead': is_thead
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
                                'is_span_copy': True,
                                'origin': (row_idx, logical_col)
                            }
                            grid[target_row][target_col] = span_ref
            
            logical_col += colspan
    
    # Phase 4: Fill any gaps
    for row_idx in range(len(grid)):
        for col_idx in range(max_cols):
            if grid[row_idx][col_idx] is None:
                grid[row_idx][col_idx] = {
                    'text': '',
                    'type': 'td',
                    'rowspan': 1,
                    'colspan': 1
                }
    
    return grid