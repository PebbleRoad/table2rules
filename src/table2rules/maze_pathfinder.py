from typing import List, Dict, Tuple


def find_headers_for_cell(grid: List[List[Dict]], row: int, col: int) -> Tuple[List[str], List[str]]:
    """
    Navigate the maze from this cell to find all headers.
    
    Returns row_headers and col_headers separately.
    
    Rules:
    1. Walk LEFT on same row - collect all <th> cells
    2. Walk UP from data cell's column - collect all <th> cells
    3. Walk UP from each row header's column - collect their column headers
       (EXCEPTION: Summary rows like "Total" do not inherit column headers)
    """
    if not grid or not grid[0]:
        return [], []
    
    row_headers = []
    col_headers = []
    seen_origins = set()
    row_header_columns = []  # Track which columns have row headers
    
    # Get table properties from the first cell
    has_thead = grid[0][0].get('has_thead', False)
    
    # --- 1. Walk LEFT on same row ---
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
    
    # --- 2. Walk UP - collect headers for the data cell itself ---
    for r in range(row - 1, -1, -1):
        cell = grid[r][col]
        
        if not cell or not cell.get('text', '').strip():
            continue
        
        if cell['type'] == 'th':
            # Universal "Walk UP" Logic:
            # If a <thead> exists, only accept headers from it.
            if has_thead and not cell.get('is_thead', False):
                continue

            # Skip row-scoped headers
            scope = cell.get('scope', '')
            if scope in ('row', 'rowgroup'):
                continue
            
            if cell.get('is_span_copy', False):
                origin = cell.get('origin', (r, col))
                origin_row, origin_col = origin
                origin_cell = grid[origin_row][origin_col]
                origin_scope = origin_cell.get('scope', '')
                
                if origin_scope in ('row', 'rowgroup'):
                    continue
                
                colspan = origin_cell.get('colspan', 1)
                if origin_col <= col < origin_col + colspan:
                    if origin not in seen_origins:
                        seen_origins.add(origin)
                        col_headers.append(cell['text'])
            else:
                origin = (r, col)
                if origin not in seen_origins:
                    seen_origins.add(origin)
                    col_headers.append(cell['text'])
    
    col_headers.reverse()
    
    # --- 3. Walk UP from each row header column ---
    # This finds context for the row headers (e.g. "Region" for "North")
    for header_col in row_header_columns:
        
        # === FIX: SUMMARY ROW SUPPRESSION ===
        # If the row header is a "Total" or "Subtotal", it defines the row entirely.
        # It should NOT inherit the column header (e.g. "Qty") of the column it sits in.
        # This prevents "Qty | Subtotal".
        idx = row_header_columns.index(header_col)
        header_text = row_headers[idx].lower()
        
        summary_keywords = ['total', 'subtotal', 'sub total', 'amount due', 'amount payable', 'balance', 'tax', 'vat', 'gst']
        
        # Check if the row header starts with any summary keyword
        if any(header_text.startswith(kw) for kw in summary_keywords):
            continue
        # ====================================

        for r in range(row - 1, -1, -1):
            cell = grid[r][header_col]
            
            if not cell or not cell.get('text', '').strip():
                continue
            
            if cell['type'] == 'th':
                # Never include <thead> cells in row header context
                # Thead cells are column headers, not row header hierarchy
                # Row header context should come from tbody cells only
                if cell.get('is_thead', False):
                    continue
                
                # For non-thead cells, only accept explicit header rows (headless tables)
                is_header_row = cell.get('is_header_row', False)
                if not is_header_row:
                    continue
                
                scope = cell.get('scope', '')
                
                # Skip row-scoped headers (they're peer row headers, not parents)
                if scope in ('row', 'rowgroup'):
                    continue
                
                # Skip column-scoped headers — they name the column, not the row value
                if scope in ('col', 'colgroup'):
                    continue
                
                if cell.get('is_span_copy', False):
                    origin = cell.get('origin', (r, header_col))
                else:
                    origin = (r, header_col)
                
                if origin not in seen_origins:
                    seen_origins.add(origin)
                    # Insert at the beginning to maintain hierarchy
                    row_headers.insert(row_header_columns.index(header_col), cell['text'])
    
    return row_headers, col_headers
