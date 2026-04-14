from collections import defaultdict
from typing import List
from bs4 import BeautifulSoup
from .models import LogicRule
from .grid_parser import parse_table_to_grid
from .maze_pathfinder import find_headers_for_cell
from .cleanup import clean_rules
from .simple_repair import simple_repair
from .quality_gate import assess_confidence


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
        # all-th rows at the top are a multi-row header, not a reset.
        header_indices = []
        seen_data_row = False
        for idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'], recursive=False)
            if not cells:
                continue
            all_th = len(cells) >= 2 and all(c.name == 'th' for c in cells)
            if all_th:
                non_empty = sum(1 for c in cells if c.get_text(strip=True))
                if non_empty >= len(cells) // 2:
                    if not seen_data_row:
                        # Part of the initial header block
                        if not header_indices:
                            header_indices.append(idx)
                    else:
                        # Data rows seen before this — genuine reset
                        header_indices.append(idx)
            elif len(cells) >= 2:
                # Only multi-cell non-th rows count as data.
                # Single-cell rows (titles, captions) don't flip the flag.
                seen_data_row = True

        # Need at least 2 header positions to indicate a reset
        if len(header_indices) < 2:
            continue

        # Verify the headers actually differ (same headers = just a repeat,
        # different = column redefinition — both worth splitting)
        boundaries = header_indices + [len(rows)]
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

        # Replace original table with the split sections
        for section in reversed(sections_html):
            table.insert_after(section)
        table.decompose()


def flatten_table(table_html: str) -> List[str]:
    """Flat fallback for tables that fail the confidence gate.

    Returns one line per row: cell texts joined with ' | ', skipping empty rows.
    No header attribution — just readable text for the LLM.
    """
    try:
        soup = BeautifulSoup(table_html, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
        rows = [r for r in table.find_all('tr') if r.find_parent('table') is table]
        lines = []
        for row in rows:
            cells = row.find_all(['td', 'th'], recursive=False)
            texts = [c.get_text(strip=True) for c in cells]
            # Skip completely empty rows
            if not any(texts):
                continue
            lines.append(" | ".join(texts))
        return lines
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
                            col_headers=col_headers
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


def group_rules_by_row(rules: List[LogicRule]) -> List[str]:
    """
    Groups rules by row position and serializes each row as a single line.
    Includes BOTH row headers and column data.
    """
    # Group rules by row index
    rows_dict = defaultdict(list)
    for rule in rules:
        row_idx = rule.position[0]
        rows_dict[row_idx].append(rule)

    serialized_rows = []

    for row_idx in sorted(rows_dict.keys()):
        row_rules = rows_dict[row_idx]

        # Sort by column position
        row_rules.sort(key=lambda r: r.position[1])

        # Collect row headers (appears once per row)
        row_header_parts = []
        if row_rules[0].row_headers:
            row_header_parts = row_rules[0].row_headers

        # Collect column data: "header: value"
        column_parts = []
        for rule in row_rules:
            # Get full column header hierarchy (joined with |)
            if rule.col_headers:
                header = " | ".join(rule.col_headers)
                column_parts.append(f"{header}: {rule.outcome.strip()}")
            else:
                # No column header (e.g., key-value table) — just output value
                column_parts.append(rule.outcome.strip())

        # Combine: "RowHeader | Col1: Val1 | Col2: Val2"
        if row_header_parts:
            if column_parts:
                row_line = " | ".join(row_header_parts) + ": " + " | ".join(column_parts)
            else:
                row_line = " | ".join(row_header_parts)
        else:
            row_line = " | ".join(column_parts)

        serialized_rows.append(row_line)

    # Drop identical rows (e.g. from rowspan copies producing the same rule)
    seen = set()
    unique = []
    for row in serialized_rows:
        if row not in seen:
            seen.add(row)
            unique.append(row)
    return unique


def process_tables_to_text(html_content: str) -> str:
    """
    SINGLE ENTRY POINT: HTML -> Formatted text.

    Takes HTML content, returns formatted text with one line per table row.
    This is the main function that should be called by external code.
    """
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
            # Group rows per table to avoid row-index collisions across tables
            output_chunks.extend(group_rules_by_row(rules))
        else:
            # Confidence gate failed — emit flat rows (cell text joined with |)
            # so the LLM gets readable text instead of raw HTML.
            flat = flatten_table(table_html)
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
