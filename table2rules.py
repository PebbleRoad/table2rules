from typing import List
from bs4 import BeautifulSoup
from models import LogicRule
from grid_parser import parse_table_to_grid
from maze_pathfinder import find_headers_for_cell
from cleanup import clean_rules
from simple_repair import simple_repair

def process_table(table_html: str) -> List[LogicRule]:
    """Process a single table and return rules (one per cell)."""
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
    
    return rules


def group_rules_by_row(rules: List[LogicRule]) -> List[str]:
    """
    Groups rules by row position and serializes each row as a single line.
    Includes BOTH row headers and column data.
    """
    from collections import defaultdict
    
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
            # Get column header
            if rule.col_headers:
                header = rule.col_headers[0]
            else:
                header = f"Col{rule.position[1]}"
            
            value = rule.outcome.strip()
            column_parts.append(f"{header}: {value}")
        
        # Combine: "RowHeader | Col1: Val1 | Col2: Val2"
        if row_header_parts:
            row_line = " | ".join(row_header_parts) + " | " + " | ".join(column_parts)
        else:
            row_line = " | ".join(column_parts)
        
        serialized_rows.append(row_line)
    
    return serialized_rows


def process_tables_to_text(html_content: str) -> str:
    """
    SINGLE ENTRY POINT: HTML → Formatted text.
    
    Takes HTML content, returns formatted text with one line per table row.
    This is the main function that should be called by external code.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    all_tables = soup.find_all('table')
    
    if not all_tables:
        return ""
    
    all_rules = []
    
    # Process only top-level tables (skip nested)
    for table in all_tables:
        if table.find_parent('table'):
            continue
        
        table_html = str(table)
        rules = process_table(table_html)
        all_rules.extend(rules)
    
    if not all_rules:
        return ""
    
    # Group by row and serialize
    serialized_rows = group_rules_by_row(all_rules)
    
    # Format output
    output_lines = ["\n"]
    output_lines.extend(serialized_rows)
    output_lines.append("\n\n")
    
    return '\n'.join(output_lines)


def main():
    """Standalone testing entry point."""
    with open('input.md', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Use the single entry point
    result = process_tables_to_text(content)

    with open('output.md', 'w', encoding='utf-8') as f:
        f.write(result)
    
    print(f"Generated table output → output.md")


if __name__ == "__main__":
    main()