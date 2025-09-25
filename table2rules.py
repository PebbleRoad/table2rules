#!/usr/bin/env python3
"""
table2rules - Universal Table to Logic Rules
Core file with parsing and CLI only
"""

import re
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Tuple
import logging
import argparse
from models import LogicRule
from table_processor_factory import TableProcessorFactory
from table_repair import needs_universal_repair, universal_table_repair


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Clean HTML text and fix encoding issues"""
    if not text:
        return ""
    
    # Handle HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # Fix common encoding issues
    text = text.replace('â€"', '—')  # Em dash
    text = text.replace('â€œ', '"')  # Left double quote
    text = text.replace('â€', '"')   # Right double quote
    text = text.replace('â€™', "'")  # Right single quote
    
    # Handle specific HTML patterns
    text = re.sub(r'(\w+\s+\d+)<br\s*/?><small>([^<]+)</small>', r'\1 \2', text, flags=re.IGNORECASE)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_and_unmerge_table_bulletproof(table) -> List[List[Dict]]:
    """Parse table into grid format - handles post-repair structure"""
    # Find footer rows
    footer_row_indices = set()
    tfoot = table.find('tfoot')
    if tfoot:
        all_trs = table.find_all('tr')
        tfoot_trs = tfoot.find_all('tr')
        for tfoot_tr in tfoot_trs:
            try:
                footer_row_indices.add(all_trs.index(tfoot_tr))
            except ValueError:
                continue
    
    # Get all rows
    actual_rows = table.find_all('tr')
    if not actual_rows:
        return []
    
    # Parse cells - CRITICAL FIX: Don't assume spans exist after repair
    parsed_cells = []
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'])
        row_cells = []
        for cell in cells:
            # After repair, all spans should be 1, but check anyway
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            cell_data = {
                'text': clean_text(cell.get_text(separator=' ')),
                'type': cell.name,
                'rowspan': rowspan,
                'colspan': colspan,
                'row': row_idx,
                'is_footer': row_idx in footer_row_indices
            }
            row_cells.append(cell_data)
        parsed_cells.append(row_cells)
    
    # Calculate grid dimensions more robustly
    max_cols = 0
    for row_cells in parsed_cells:
        col_count = 0
        for cell in row_cells:
            col_count += cell['colspan']
        max_cols = max(max_cols, col_count)
    
    max_rows = len(actual_rows)
    
    # Initialize grid
    grid = [[{'text': '', 'type': 'td', 'original_cell': False, 'is_footer': False} 
             for _ in range(max_cols)] for _ in range(max_rows)]
    
    # Fill grid - simpler logic since repair removed all multi-spans
    for row_idx, row_cells in enumerate(parsed_cells):
        col_idx = 0
        for cell in row_cells:
            # Fill the cell and any spans it covers
            for r in range(cell['rowspan']):
                for c in range(cell['colspan']):
                    target_row, target_col = row_idx + r, col_idx + c
                    if target_row < max_rows and target_col < max_cols:
                        grid[target_row][target_col] = {
                            'text': cell['text'],
                            'type': cell['type'],
                            'original_cell': (r == 0 and c == 0),
                            'original_rowspan': cell['rowspan'] if (r == 0 and c == 0) else 1,
                            'original_colspan': cell['colspan'] if (r == 0 and c == 0) else 1,
                            'rowspan': 1,
                            'colspan': 1,
                            'is_footer': cell['is_footer']
                        }
            col_idx += cell['colspan']
    
    return grid

def needs_repair(html_content: str) -> bool:
    """Enhanced malformation detection"""
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return False
    
    # Pattern 1: ANY td elements with rowspan > 1 (shared resource cells)
    malformed_rowspan = table.find_all('td', {'rowspan': True})
    for cell in malformed_rowspan:
        if int(cell.get('rowspan', 1)) > 1:
            text = cell.get_text(strip=True)
            logger.info(f"Malformation detected: td with rowspan={cell.get('rowspan')} ('{text}')")
            return True
    
    # Pattern 2: ANY td elements with colspan > 1 (consolidated cells) 
    malformed_colspan = table.find_all('td', {'colspan': True})
    for cell in malformed_colspan:
        if int(cell.get('colspan', 1)) > 1:  # Changed from > 2
            text = cell.get_text(strip=True)
            logger.info(f"Malformation detected: td with colspan={cell.get('colspan')} ('{text}')")
            return True
    
    return False


def process_table(table_html: str) -> List[LogicRule]:
    """Main table processing function with systematic repair"""
    
    # Step 1: Use your original systematic repair (not the grid reconstruction)
    if needs_universal_repair(table_html):
        table_html = universal_table_repair(table_html)
        logger.info("Applied universal structure repair")
    
    # Step 2: Your existing universal processing (unchanged)
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    
    grid = parse_and_unmerge_table_bulletproof(table)
    if not grid:
        logger.warning("Table parsing resulted in empty grid")
        return []
    
    logger.info(f"Parsed grid: {len(grid)} rows x {len(grid[0]) if grid else 0} columns")
    
    # Step 3: Factory processing (unchanged)
    factory = TableProcessorFactory()
    result = factory.process_table(grid, table)
    
    logger.info(f"Processed with {result.processor_type}: {len(result.rules)} rules")
    
    return result.rules




def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description='table2rules - Universal Table to Logic Rules')
    parser.add_argument('--format', choices=['structured', 'conversational', 'qa', 'descriptive', 'searchable', 'all'], 
                       default='structured', help='Output format')
    parser.add_argument('--input', default='input.md', help='Input file')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        table_pattern = r'<table[^>]*>.*?</table>'
        tables = re.findall(table_pattern, content, re.DOTALL)
        
        if not tables:
            logger.warning(f"No tables found in {args.input}")
            return
        
        all_rules = []
        for i, table_html in enumerate(tables):
            logger.info(f"Processing table {i+1}...")
            rules = process_table(table_html)
            all_rules.extend(rules)
        
        # Write output
        with open('output.md', 'w', encoding='utf-8') as f:
            for rule in all_rules:
                if args.format == 'structured':
                    content = rule.to_rule_string()
                else:
                    formats = rule.to_natural_formats()
                    content = formats[args.format]
                f.write(f"{content}\n")
        
        logger.info(f"Generated {len(all_rules)} rules")
        
    except FileNotFoundError:
        logger.error(f"File {args.input} not found")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()