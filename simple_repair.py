from bs4 import BeautifulSoup
import re

def get_top_level_rows(table):
    """
    Helper function to robustly get ONLY the rows
    belonging to the main table, skipping nested tables.
    """
    all_rows_in_dom = table.find_all('tr')
    top_level_rows = []
    
    for row in all_rows_in_dom:
        if row.find_parent('table') is table:
            top_level_rows.append(row)
            
    return top_level_rows


def simple_repair(html: str) -> str:
    """
    Simple targeted repairs for common issues:
    1. Move title rows (full-width th) to caption
    2. Fix <td> headers in <tfoot> (for totals)
    3. Move footer legends to tfoot
    4. Convert first data row to proper header row (<th> tags)
    5. Promote summary labels (Total, Subtotal) in <tbody> to <th>
    6. Merge "hanging" description rows (e.g. Dates below items)
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return html
    
    actual_rows = get_top_level_rows(table)
    if not actual_rows:
        return html

    # --- Fix 1: Move title row to caption ---
    first_meaningful_row = None
    first_meaningful_row_index = 0
    for idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        if cells:
            first_meaningful_row = row
            first_meaningful_row_index = idx
            break
            
    if first_meaningful_row:
        cells = first_meaningful_row.find_all(['td', 'th'], recursive=False)
        if len(cells) == 1 and int(cells[0].get('colspan', 1)) >= 4:
            title_text = cells[0].get_text(strip=True)
            caption = table.find('caption')
            if caption:
                caption.string = title_text
            else:
                new_caption = soup.new_tag('caption')
                new_caption.string = title_text
                table.insert(0, new_caption)
            for i in range(first_meaningful_row_index + 1):
                actual_rows[i].decompose()
        actual_rows = get_top_level_rows(table)


    # --- Fix 6: Merge "Hanging" Description Rows (NEW) ---
    # Detect rows that contain only text in the first cell (and empty elsewhere),
    # and follow a fully-populated data row. These are likely wrapped descriptions.
    # We do this BEFORE converting types to ensure we catch them while they are still just structure.
    
    i = 0
    while i < len(actual_rows):
        row = actual_rows[i]
        cells = row.find_all(['td', 'th'], recursive=False)
        
        # Condition 1: Current row is "Sparse" (Text in 1st cell, others empty)
        is_sparse = False
        if cells:
            first_cell_text = cells[0].get_text(strip=True)
            # Check if all other cells are empty
            other_cells_empty = all(not c.get_text(strip=True) for c in cells[1:])
            
            # Additional check: Don't merge if it looks like a Summary Row
            # (We want Subtotal to stay its own row)
            summary_keywords = ['total', 'subtotal', 'amount due', 'amount payable', 'balance', 'tax', 'vat', 'gst']
            is_summary = any(first_cell_text.lower().startswith(kw) for kw in summary_keywords)
            
            if first_cell_text and other_cells_empty and not is_summary:
                is_sparse = True
        
        # Condition 2: Previous row has data
        if is_sparse and i > 0:
            prev_row = actual_rows[i-1]
            prev_cells = prev_row.find_all(['td', 'th'], recursive=False)
            
            # Check if previous row has data in columns 1+
            # (This prevents merging two section headers together)
            has_data = False
            if len(prev_cells) > 1:
                has_data = any(c.get_text(strip=True) for c in prev_cells[1:])
            
            if has_data:
                # MERGE LOGIC:
                # Append current text to previous row's first cell
                separator = " "  # Use space or newline
                prev_cells[0].string = prev_cells[0].get_text(strip=True) + separator + cells[0].get_text(strip=True)
                
                # Delete the hanging row
                row.decompose()
                actual_rows.pop(i)
                # Do NOT increment i, because the next row is now at index i
                continue
        
        i += 1


    # --- Fix 2, 3, 5: Iterate remaining rows ---
    # Re-fetch rows just in case, though pop() should keep list valid
    # (Safe to use existing list references if we were careful, but let's be safe)
    actual_rows = get_top_level_rows(table)
    
    summary_keywords = ['total', 'subtotal', 'amount due', 'amount payable', 'balance', 'tax', 'vat', 'gst']

    for idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'], recursive=False)
        if not cells:
            continue
            
        # --- Fix 2: Fix <tfoot> row headers ---
        if row.find_parent('tfoot') and cells[0].name == 'td':
            if int(cells[0].get('colspan', 1)) > 1:
                cells[0].name = 'th'
                cells[0]['scope'] = 'colgroup'
        
        # --- Fix 3: Move footer legends to tfoot ---
        if not row.find_parent('tfoot'):
            if len(cells) == 1:
                text = cells[0].get_text(strip=True).lower()
                if 'legend' in text or 'footnote' in text:
                    colspan = int(cells[0].get('colspan', 1))
                    if colspan >= 3:
                        tfoot = table.find('tfoot')
                        if not tfoot:
                            tfoot = soup.new_tag('tfoot')
                            table.append(tfoot)
                        row.extract()
                        tfoot.append(row)
                        continue 

        # --- Fix 5: Promote Summary Labels ---
        if idx > 0: 
            for cell in cells:
                if cell.name == 'td':
                    txt = cell.get_text(strip=True).lower()
                    if any(txt.startswith(kw) for kw in summary_keywords):
                        cell.name = 'th'
                        cell['scope'] = 'row'

    
    # --- Fix 4: Convert first data row to header row ---
    actual_rows = get_top_level_rows(table) 
    
    if actual_rows:
        first_data_row = actual_rows[0]
        if not first_data_row.find_parent('tfoot'):
            cells = first_data_row.find_all(['td', 'th'], recursive=False)
            if cells and any(cell.name == 'td' for cell in cells):
                first_cell_colspan = int(cells[0].get('colspan', 1))
                first_cell_text = cells[0].get_text(strip=True).lower()
                is_section_header = (
                    first_cell_colspan == 1 and 
                    len(cells) > 1 and 
                    all(not cell.get_text(strip=True) for cell in cells[1:])
                )
                if first_cell_colspan == 1 and not is_section_header:
                    for cell in cells:
                        if cell.name == 'td':
                            cell.name = 'th'
    
    return str(soup)