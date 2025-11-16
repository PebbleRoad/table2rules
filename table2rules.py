from typing import List
from bs4 import BeautifulSoup
from models import LogicRule
from grid_parser import parse_table_to_grid
from maze_pathfinder import find_headers_for_cell
from cleanup import clean_rules
from simple_repair import simple_repair


def process_table(table_html: str) -> List[LogicRule]:
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
                    headers = find_headers_for_cell(grid, target_row, target_col)
                    
                    rule = LogicRule(
                        conditions=headers,
                        outcome=cell['text'],
                        position=(target_row, target_col),
                        is_footer=cell.get('is_footer', False)
                    )
                    
                    rules.append(rule)
    
    # Post-processing cleanup
    rules = clean_rules(rules)
    
    return rules


def main():
    import argparse
    from bs4 import BeautifulSoup # <-- Import BeautifulSoup here
    
    parser = argparse.ArgumentParser(
        description='Table2Rules - Convert HTML tables to rules'
    )
    parser.add_argument(
        '--format',
        choices=['descriptive', 'keyvalue'],
        default='descriptive',
        help='Output format: descriptive (default, RAG-optimized) or keyvalue (compact)'
    )
    args = parser.parse_args()
    
    with open('input.md', 'r', encoding='utf-8') as f:
        content = f.read()

    
    soup = BeautifulSoup(content, 'html.parser')
    
    # 1. Find ALL tables
    all_tables = soup.find_all('table')
    
    if not all_tables:
        print("No tables found")
        return

    all_rules = []
    
    # 2. Process ONLY top-level tables
    for table in all_tables:
        # If a table's parent is *another* table, it's nested. Skip it.
        if table.find_parent('table'):
            continue
            
        # 3. Pass the full, correct HTML string of this table
        table_html = str(table)
        rules = process_table(table_html)
        all_rules.extend(rules)


    with open('output.md', 'w', encoding='utf-8') as f:
        for rule in all_rules:
            if args.format == 'keyvalue':
                f.write(rule.to_keyvalue() + '\n')
            else:
                f.write(rule.to_string() + '\n')
    
    print(f"Generated {len(all_rules)} rules → output.md")


if __name__ == "__main__":
    main()