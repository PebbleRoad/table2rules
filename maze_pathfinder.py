from typing import List, Dict, Tuple, Set


def find_headers_for_cell(grid: List[List[Dict]], row: int, col: int) -> Tuple[List[str], List[str]]:
    """
    Navigate the maze from this cell to find all headers.
    
    Returns row_headers and col_headers separately.
    
    Rules:
    1. Walk LEFT on same row - collect all <th> cells
    2. Walk UP from data cell's column - collect all <th> cells
    3. Walk UP from each row header's column - collect their column headers
    """
    if not grid or not grid[0]:
        return []
    
    row_headers = []
    col_headers = []
    seen_origins = set()
    row_header_columns = []  # Track which columns have row headers
    
    # Get table properties from the first cell
    # (We assume grid is not empty)
    has_thead = grid[0][0].get('has_thead', False)
    
    # Walk LEFT on same row
    for c in range(col - 1, -1, -1):
        cell = grid[row][c]
        
        if not cell or not cell.get('text', '').strip():
            continue
        
        if cell['type'] == 'th':
            if cell.get('is_span_copy', False):
                origin = cell.get('origin', (row, c))
            else:
                origin = (row, c)
            
            if origin not in seen_origins:
                seen_origins.add(origin)
                row_headers.append(cell['text'])
                row_header_columns.append(c)  # Remember this column
    
    row_headers.reverse()
    row_header_columns.reverse()
    
    # Walk UP - collect headers that apply to our column
    for r in range(row - 1, -1, -1):
        cell = grid[r][col]
        
        if not cell or not cell.get('text', '').strip():
            continue
        
        if cell['type'] == 'th':
            
            # --- NEW UNIVERSAL "Walk UP" LOGIC ---
            # If a <thead> exists, only accept headers from it.
            # If no <thead> exists, accept any <th> we find above.
            if has_thead and not cell.get('is_thead', False):
                continue
            # --- END NEW LOGIC ---

            # Skip row-scoped headers (they don't apply to columns below)
            scope = cell.get('scope', '')
            if scope in ('row', 'rowgroup'):
                continue
            
            if cell.get('is_span_copy', False):
                origin = cell.get('origin', (r, col))
                origin_row, origin_col = origin
                
                # Get the original cell to check its colspan and scope
                origin_cell = grid[origin_row][origin_col]
                origin_scope = origin_cell.get('scope', '')
                
                # Skip if origin has row scope
                if origin_scope in ('row', 'rowgroup'):
                    continue
                
                colspan = origin_cell.get('colspan', 1)
                
                # Check if this header spans over our column
                if origin_col <= col < origin_col + colspan:
                    if origin not in seen_origins:
                        seen_origins.add(origin)
                        col_headers.append(cell['text'])
            else:
                # Origin cell at our column
                origin = (r, col)
                if origin not in seen_origins:
                    seen_origins.add(origin)
                    col_headers.append(cell['text'])
    
    col_headers.reverse()
    
    # Walk UP from each row header column to find their column headers
    # This applies to ALL tables - the row header column needs its header too
    for header_col in row_header_columns:
        for r in range(row - 1, -1, -1):
            cell = grid[r][header_col]
            
            if not cell or not cell.get('text', '').strip():
                continue
            
            if cell['type'] == 'th':
                # Apply same filtering as main Walk UP
                if has_thead and not cell.get('is_thead', False):
                    continue
                
                scope = cell.get('scope', '')
                if scope in ('row', 'rowgroup'):
                    continue
                
                if cell.get('is_span_copy', False):
                    origin = cell.get('origin', (r, header_col))
                else:
                    origin = (r, header_col)
                
                if origin not in seen_origins:
                    seen_origins.add(origin)
                    # Insert at the beginning of row_headers to maintain proper order
                    # Column header for row header comes before the row header itself
                    row_headers.insert(row_header_columns.index(header_col), cell['text'])
    
    return row_headers, col_headers