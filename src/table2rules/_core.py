from typing import List, Union
from bs4 import BeautifulSoup
from .models import LogicRule
from .grid_parser import parse_table_to_grid
from .maze_pathfinder import find_headers_for_cell
from .cleanup import clean_rules
from .simple_repair import simple_repair
from .quality_gate import assess_confidence
from .exporters import DEFAULT_FORMAT, Exporter, get_exporter


def _split_compound_tables(soup) -> None:
    """Split tables with mid-body header resets into separate tables.

    Detects all-<th> rows in the body that redefine column names (e.g. OCR
    page-break repeats where "Sales" becomes "Returns").  Each section gets
    its own <table> so it is parsed with the correct headers.

    Operates on the raw soup BEFORE simple_repair to avoid false positives
    from summary rows promoted to <th>.
    """
    for table in list(soup.find_all('table')):
        rows = [r for r in table.find_all('tr') if r.find_parent('table') is table]
        if len(rows) < 3:
            continue

        # Find all-th rows in source markup, but only treat them as
        # split points when data rows appear in between.  Consecutive
        # all-th rows (top or post-data) form a single multi-row header,
        # not separate boundaries.  Summary rows that simple_repair later
        # promotes to <th> (e.g. "Total", "Subtotal") must not be treated
        # as boundaries either.
        SUMMARY_LABELS = {"total", "subtotal", "sub total", "grand total"}
        header_indices = []
        seen_data_row = False
        prev_was_header_row = False
        for idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'], recursive=False)
            if not cells:
                continue
            all_th = len(cells) >= 2 and all(c.name == 'th' for c in cells)
            looks_like_summary = any(
                c.get_text(strip=True).lower() in SUMMARY_LABELS for c in cells
            )
            if all_th and not looks_like_summary:
                non_empty = sum(1 for c in cells if c.get_text(strip=True))
                if non_empty >= len(cells) // 2:
                    if not seen_data_row:
                        # Part of the initial header block
                        if not header_indices:
                            header_indices.append(idx)
                    elif not prev_was_header_row:
                        # Genuine reset (previous content row was data, not
                        # another header row continuing a multi-row header)
                        header_indices.append(idx)
                prev_was_header_row = True
            elif len(cells) >= 2:
                # Only multi-cell non-th rows count as data.
                # Single-cell rows (titles, captions) don't flip the flag.
                seen_data_row = True
                prev_was_header_row = False
            else:
                prev_was_header_row = False

        # Need at least 2 header positions to indicate a reset
        if len(header_indices) < 2:
            continue

        # Verify the headers actually differ (same headers = just a repeat,
        # different = column redefinition — both worth splitting).
        # Also require every proposed section to contain at least one
        # multi-cell data row; header-only sections are never useful and
        # indicate a bogus boundary.
        boundaries = header_indices + [len(rows)]
        for i in range(len(header_indices)):
            section_rows = rows[boundaries[i]:boundaries[i + 1]]
            has_data = any(
                len(r.find_all(['td', 'th'], recursive=False)) >= 2
                and any(c.name == 'td' for c in r.find_all(['td', 'th'], recursive=False))
                for r in section_rows
            )
            if not has_data:
                break
        else:
            # Every section has data — proceed with split.
            sections_html = []
            for i in range(len(header_indices)):
                start = boundaries[i]
                end = boundaries[i + 1]
                section_rows = rows[start:end]
                new_table = soup.new_tag('table')
                for row in section_rows:
                    row.extract()
                    new_table.append(row)
                sections_html.append(new_table)
            for section in reversed(sections_html):
                table.insert_after(section)
            table.decompose()


def _extract_cell_rows(table_html: str) -> List[List[str]]:
    """Return raw cell text for each row (header-free). Used as gate-fail fallback."""
    try:
        soup = BeautifulSoup(table_html, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
        rows = [r for r in table.find_all('tr') if r.find_parent('table') is table]
        out: List[List[str]] = []
        for row in rows:
            cells = row.find_all(['td', 'th'], recursive=False)
            texts = [c.get_text(strip=True) for c in cells]
            if any(texts):
                out.append(texts)
        return out
    except Exception:
        return []




def process_table(table_html: str) -> List[LogicRule]:
    """Process a single table and return rules (one per cell)."""
    try:
        # Step 1: Apply simple repairs
        table_html = simple_repair(table_html)
        soup = BeautifulSoup(table_html, 'html.parser')
        table = soup.find('table')

        if not table:
            return []

        grid = parse_table_to_grid(table)
        if not grid:
            return []

        rules = []

        for row_idx in range(len(grid)):
            for col_idx in range(len(grid[0])):
                cell = grid[row_idx][col_idx]

                # Only <td> cells are data cells
                # <th> cells are always headers (either column or row headers)
                if cell['type'] != 'td':
                    continue

                # Defensive guard: never emit rules from explicit/implicit header rows
                if cell.get('is_thead', False) or cell.get('is_header_row', False):
                    continue

                # Skip empty cells
                if not cell.get('text', '').strip():
                    continue

                # If this is a span copy, skip it (we'll process it from origin)
                if cell.get('is_span_copy', False):
                    continue

                # Get the span dimensions
                rowspan = cell.get('rowspan', 1)
                colspan = cell.get('colspan', 1)

                # Generate a rule for each position this cell occupies
                for r_offset in range(rowspan):
                    for c_offset in range(colspan):
                        target_row = row_idx + r_offset
                        target_col = col_idx + c_offset

                        if target_row >= len(grid) or target_col >= len(grid[0]):
                            continue

                        # Find headers from THIS position (not the origin)
                        row_headers, col_headers = find_headers_for_cell(grid, target_row, target_col)

                        rule = LogicRule(
                            conditions=row_headers + col_headers,  # Keep for backward compatibility
                            outcome=cell['text'],
                            position=(target_row, target_col),
                            is_footer=cell.get('is_footer', False),
                            row_headers=row_headers,
                            col_headers=col_headers,
                            origin=(row_idx, col_idx),
                        )

                        rules.append(rule)

        # Post-processing cleanup
        rules = clean_rules(rules)

        # Confidence gate: if parse quality is weak, fail open to passthrough HTML.
        gate = assess_confidence(grid, rules)
        if not gate.ok:
            return []

        return rules
    except Exception:
        # Fail open for hostile / pathological table markup
        return []


def process_tables_to_text(
    html_content: str,
    format: Union[str, Exporter] = DEFAULT_FORMAT,
) -> str:
    """
    SINGLE ENTRY POINT: HTML -> Formatted text.

    Args:
        html_content: raw HTML containing one or more <table> elements.
        format: exporter name (e.g. "rules") or an Exporter instance.
                Defaults to "rules" (one rule per line, full header paths).
    """
    exporter = get_exporter(format)
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    all_tables = soup.find_all('table')

    if not all_tables:
        return ""

    output_chunks = []

    # Pre-process: split compound tables that have mid-body header resets
    # (all-<th> rows appearing after the first header row with different
    # column names).  Must happen BEFORE repair to avoid false positives
    # from summary rows that Fix 5 promotes to <th>.
    _split_compound_tables(soup)
    all_tables = soup.find_all('table')

    # Process only top-level tables (skip nested)
    for table in all_tables:
        if table.find_parent('table'):
            continue

        table_html = str(table)
        rules = process_table(table_html)

        if rules:
            output_chunks.extend(exporter.export_rules(rules))
        else:
            # Confidence gate failed — fall back to header-free cell rows.
            cell_rows = _extract_cell_rows(table_html)
            flat = exporter.export_flat(cell_rows) if cell_rows else []
            if flat:
                output_chunks.extend(flat)
            else:
                output_chunks.append(table_html)

    if not output_chunks:
        return ""

    # Format output
    output_lines = ["\n"]
    output_lines.extend(output_chunks)
    output_lines.append("\n\n")

    return '\n'.join(output_lines)
