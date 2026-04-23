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
    0. Fix mismatched opening/closing tags (<td>...</th> and vice versa)
    1. Move title rows (full-width th) to caption
    2. Fix <td> headers in <tfoot> (for totals)
    3. Move footer legends to tfoot
    4. Convert first data row to proper header row (<th> tags)
    5. Promote summary labels (Total, Subtotal) in <tbody> to <th>
    6. Merge "hanging" description rows (e.g. Dates below items)
    """
    # --- Fix 0: Repair mismatched opening/closing tags ---
    # <td ...>text</th> and <th ...>text</td> cause html.parser to nest
    # subsequent sibling cells inside the unclosed element.
    # Fix by normalising closing tags to match their opener.
    # [^<]* restricts to plain-text content so we never span across tags.
    html = re.sub(r'(<td\b[^>]*>)([^<]*)</th>', r'\1\2</td>', html)
    html = re.sub(r'(<th\b[^>]*>)([^<]*)</td>', r'\1\2</th>', html)

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return html
    
    # --- Fix 9: Inline nested tables ---
    # Replace <table> elements inside cells with their flattened text
    # so the outer grid parser sees clean content instead of nested markup.
    for nested in table.find_all('table'):
        rows = nested.find_all('tr')
        lines = []
        for row in rows:
            cells = row.find_all(['td', 'th'], recursive=False)
            texts = [c.get_text(strip=True) for c in cells]
            if any(texts):
                lines.append(", ".join(t for t in texts if t))
        nested.replace_with("; ".join(lines))

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
        # Treat the first row as a title iff it is a single cell whose colspan
        # covers the full width of the remaining rows (width >= 2). This
        # captures 2-col and 3-col tables correctly without over-promoting.
        later_widths = [
            len(r.find_all(['td', 'th'], recursive=False))
            for r in actual_rows[first_meaningful_row_index + 1:]
        ]
        max_later_width = max(later_widths, default=0)
        first_cell_span = int(cells[0].get('colspan', 1))
        if (
            len(cells) == 1
            and max_later_width >= 2
            and first_cell_span >= max_later_width
        ):
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


    # --- Fix 1b: Decompose mid-table section-title rows ---
    # A <tr> whose sole cell is a <th> with colspan covering the grid
    # width is structurally a section label (e.g. "Personal" / "Work"
    # delimiting A/V blocks in two <tbody>s). If it survives into the
    # grid, the span expansion turns the label into a fabricated column
    # header for the rows below. Decompose these rows so section labels
    # don't pollute the header walk. Fix 1 already handles the first-row
    # instance by moving it to <caption>; this handles mid-table ones.
    if actual_rows:
        row_widths = [
            len(r.find_all(['td', 'th'], recursive=False))
            for r in actual_rows
        ]
        max_width = max(row_widths, default=0)
        if max_width >= 2:
            for row in list(actual_rows):
                cells = row.find_all(['td', 'th'], recursive=False)
                if len(cells) != 1:
                    continue
                cell = cells[0]
                if cell.name != 'th':
                    continue
                colspan = int(cell.get('colspan', 1))
                if colspan >= max_width:
                    row.decompose()
        actual_rows = get_top_level_rows(table)


    # --- Fix 7: Wrap header rows in <thead> ---
    # If table lacks <thead>, detect contiguous leading rows that are "header-like"
    # (all <th> cells, or all <th>/empty cells) and wrap them in <thead>.
    # This ensures downstream logic can rely on is_thead to identify column headers.
    if not table.find('thead') and actual_rows:
        header_rows = []
        seen_non_empty = False

        for row in actual_rows:
            cells = row.find_all(['td', 'th'], recursive=False)

            # Ignore leading empty rows; do not treat them as headers
            if not cells and not seen_non_empty:
                continue

            if not cells and seen_non_empty:
                # Empty row after header block means header detection ends
                break

            seen_non_empty = True

            # A row is "header-like" if all cells are <th> or empty
            is_header_like = all(
                cell.name == 'th' or not cell.get_text(strip=True)
                for cell in cells
            )

            if is_header_like:
                header_rows.append(row)
            else:
                # Stop at first non-header row
                break
        
        # Only wrap if we found header rows (and they're not ALL the rows)
        if header_rows and len(header_rows) < len(actual_rows):
            thead = soup.new_tag('thead')
            
            # Insert thead at the beginning of the table
            # (after caption if present)
            caption = table.find('caption')
            if caption:
                caption.insert_after(thead)
            else:
                table.insert(0, thead)
            
            # Move header rows into thead
            for row in header_rows:
                row.extract()
                thead.append(row)
            
            actual_rows = get_top_level_rows(table)


    # --- Fix 8: Promote row headers based on <thead> structure ---
    # If <thead> has multi-row structure (hierarchical column headers), the first
    # column typically contains row identifiers. Promote first-column <td> cells 
    # in <tbody> to <th scope="row">.
    # 
    # We only promote cells that:
    # 1. Are the first cell in their DOM row, AND
    # 2. Either have rowspan > 1 (explicit row group identifier), OR
    # 3. Are not "covered" by a rowspan from a previous row
    thead = table.find('thead')
    if thead:
        thead_rows = thead.find_all('tr', recursive=False)
        header_depth = len(thead_rows)
        
        if header_depth > 1:
            # Multi-row header structure suggests dimensional table
            tbody = table.find('tbody')
            if tbody:
                active_rowspan = 0  # Track if a rowspan from above covers first column
                
                for row in tbody.find_all('tr', recursive=False):
                    cells = row.find_all(['td', 'th'], recursive=False)
                    
                    if active_rowspan > 0:
                        # First column is covered by rowspan from above
                        # Don't promote the first DOM cell (it's in column 1+)
                        active_rowspan -= 1
                    elif cells and cells[0].name == 'td':
                        # This cell is truly in the first column
                        cells[0].name = 'th'
                        cells[0]['scope'] = 'row'
                        # Track rowspan for subsequent rows
                        rowspan = int(cells[0].get('rowspan', 1))
                        if rowspan > 1:
                            active_rowspan = rowspan - 1


    # --- Fix 6: Merge "Hanging" Description Rows ---
    # Detects "wrap continuation" rows: a row with text in only the first cell
    # (rest empty) that follows a fully-populated data row. Historically meant
    # to rejoin labels that wrapped to a new line in some extractor outputs.
    #
    # In practice, this pattern is vastly more often a SECTION DIVIDER row
    # (scientific / financial tables introducing a sub-group) than a genuine
    # wrap continuation. Merging section dividers corrupts adjacent data
    # rows (observed on PubTabNet, HiTab). So we only fire when the row is
    # very likely to be a continuation:
    #   - current sparse row has a wide trailing colspan  → section marker
    #   - next row has a continuation-like shape          → probably wrap
    # For now, the safer default is to NOT merge. The edge case where this
    # merge was useful (single-column wrapped descriptions on narrow tables)
    # hasn't resurfaced across the corpus and red-team fixtures.

    # (merge loop intentionally disabled — see commit log for context)


    # --- Fix 2, 3, 5: Iterate remaining rows ---
    # Re-fetch rows just in case, though pop() should keep list valid
    # (Safe to use existing list references if we were careful, but let's be safe)
    actual_rows = get_top_level_rows(table)
    
    summary_keywords = ['total', 'subtotal', 'sub total', 'amount due', 'amount payable', 'balance', 'tax', 'vat', 'gst']

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
        # Only applies in tbody — 'Total', 'Subtotal', etc. inside <thead>
        # are legitimate column headers (PubTabNet-style financial tables
        # have a 'Total' column under a 'Year Ended' grouping), and marking
        # them scope="row" would hide them from the column-header walk.
        if idx > 0 and not row.find_parent('thead'):
            for cell in cells:
                if cell.name == 'td':
                    txt = cell.get_text(strip=True).lower()
                    if any(txt.startswith(kw) for kw in summary_keywords):
                        cell.name = 'th'
                        cell['scope'] = 'row'

    
    # --- Fix 4: Convert first data row to header row ---
    # Only applies to tables without thead where first row looks like headers
    # Skip if row already has <th> cells (key-value table pattern)
    actual_rows = get_top_level_rows(table) 
    
    if actual_rows and not table.find('thead'):
        first_data_row = actual_rows[0]
        if not first_data_row.find_parent('tfoot'):
            cells = first_data_row.find_all(['td', 'th'], recursive=False)
            # Only convert if ALL cells are <td> (no <th> present)
            # This preserves key-value tables where first cell is <th>
            all_td = cells and all(cell.name == 'td' for cell in cells)
            if all_td:
                first_cell_colspan = int(cells[0].get('colspan', 1))
                is_section_header = (
                    first_cell_colspan == 1 and
                    len(cells) > 1 and
                    all(not cell.get_text(strip=True) for cell in cells[1:])
                )
                # Only promote to headers if every cell is non-empty. Real
                # header rows don't have blanks — if row 0 has empty cells,
                # it's data (typical of receipts where amount columns shift
                # between rows). Numeric cells are allowed here; the
                # confidence gate catches numeric column headers later.
                texts = [c.get_text(strip=True) for c in cells]
                looks_header_like = bool(texts) and all(t for t in texts)
                # Structural contrast check: promote row 0 to <th> only when
                # at least one subsequent multi-cell row has at least one
                # empty cell. A real header uniquely labels every column;
                # data rows legitimately have gaps. Without contrast, we
                # have no structural evidence that row 0 plays a different
                # role from the rows below it. Inventing <th> where the
                # source has <td> is synthesis, not repair.
                has_sparse_subsequent = False
                for r in actual_rows[1:]:
                    subsequent_cells = r.find_all(['td', 'th'], recursive=False)
                    if len(subsequent_cells) <= 1:
                        continue
                    if any(not c.get_text(strip=True) for c in subsequent_cells):
                        has_sparse_subsequent = True
                        break
                if (
                    first_cell_colspan == 1
                    and not is_section_header
                    and looks_header_like
                    and has_sparse_subsequent
                ):
                    for cell in cells:
                        cell.name = 'th'
    
    return str(soup)
