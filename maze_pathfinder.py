from typing import List, Dict, Tuple, Set


def find_headers_for_cell(grid: List[List[Dict]], row: int, col: int) -> List[str]:
    """
    Navigate the maze from this cell to find all headers.
    
    Rules:
    1. Walk LEFT on same row - collect all <th> cells
    2. Walk UP - collect all <th> cells whose origin is in our column
    """
    if not grid or not grid[0]:
        return []
    
    row_headers = []
    col_headers = []
    seen_origins = set()
    
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
    
    row_headers.reverse()
    
    # Walk UP - collect headers that apply to our column
    for r in range(row - 1, -1, -1):
        cell = grid[r][col]
        
        if not cell or not cell.get('text', '').strip():
            continue
        
        if cell['type'] == 'th':
            # Skip row-scoped headers (they don't apply to columns below)
            scope = cell.get('scope', '')
            if not cell.get('is_thead', False):
                continue
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
    
    return row_headers + col_headers