from bs4 import BeautifulSoup


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
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return html
    
    actual_rows = get_top_level_rows(table)
    if not actual_rows:
        return html

    # --- Fix 1: Move title row to caption (NOW MORE ROBUST) ---
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
            
            # Decompose the title row and any empty rows before it
            for i in range(first_meaningful_row_index + 1):
                actual_rows[i].decompose()
        
        # We must re-fetch rows after deleting
        actual_rows = get_top_level_rows(table)


    # --- Fix 2 & 3: Iterate rows ONCE for final repairs ---
    for row in actual_rows:
        cells = row.find_all(['td', 'th'], recursive=False)
        if not cells:
            continue
            
        # --- Fix 2: Fix <tfoot> row headers (the "Total Revenue" fix) ---
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
    
    return str(soup)