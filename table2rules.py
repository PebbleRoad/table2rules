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
from rag_fix import apply_rag_fixes



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Clean HTML text, fix common encoding issues, and normalize whitespace."""
    if not text:
        return ""
    
    # 1. Fix known bad encoding characters first.
    # UTF-8 characters that were misread as Windows-1252.
    replacements = {
        'â€”': '—',  # Em dash
        'â€': '”',  # Right double quote or superscript dagger
        'â€™': '’',  # Right single quote
        'Â': ' ',    # Non-breaking space often becomes this
        '&nbsp;': ' ' # Handle HTML non-breaking space
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # 2. Handle standard HTML entities.
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # 3. Remove any remaining HTML tags.
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 4. Normalize all whitespace (spaces, tabs, newlines) to a single space.
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_and_unmerge_table_bulletproof(table) -> List[List[Dict]]:
    """Universal grid parser - handles spans mathematically without repair"""
    
    # Get all rows
    actual_rows = table.find_all('tr')
    if not actual_rows:
        logger.debug("No table rows found")
        return []
    
    # Phase 1: Calculate the true grid dimensions
    # We need to simulate span expansion to find the real column count
    max_cols = 0
    for row in actual_rows:
        cells = row.find_all(['td', 'th'])
        row_width = sum(int(cell.get('colspan', 1)) for cell in cells)
        max_cols = max(max_cols, row_width)
    
    logger.debug(f"Calculated grid dimensions: {len(actual_rows)} rows x {max_cols} columns")
    
    # Phase 2: Build the logical grid
    # Create empty grid filled with None
    logical_grid = [[None for _ in range(max_cols)] for _ in range(len(actual_rows))]
    
    # Phase 3: Fill the logical grid by processing each physical cell
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'])
        logical_col = 0
        
        for cell in cells:
            # Skip positions already occupied by spanning cells
            while (logical_col < max_cols and 
                   logical_grid[row_idx][logical_col] is not None):
                logical_col += 1
            
            # Get span dimensions
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # Create cell data
            cell_data = {
                'text': clean_text(cell.get_text(separator=' ')),
                'type': cell.name,
                'rowspan': rowspan,
                'colspan': colspan,
                'original_cell': True,
                'original_rowspan': rowspan,
                'original_colspan': colspan,
                'is_footer': False  # We'll handle footer detection separately
            }
            
            logger.debug(f"Processing cell at ({row_idx},{logical_col}): '{cell_data['text'][:30]}...' "
                        f"spans={rowspan}x{colspan}")
            
            # Fill all positions this cell spans
            for r_offset in range(rowspan):
                for c_offset in range(colspan):
                    target_row = row_idx + r_offset
                    target_col = logical_col + c_offset
                    
                    if (target_row < len(logical_grid) and 
                        target_col < max_cols):
                        
                        if r_offset == 0 and c_offset == 0:
                            # This is the original cell position
                            logical_grid[target_row][target_col] = cell_data
                        else:
                            # This is a spanned position - create a reference that preserves key info
                            span_cell = {
                                'text': cell_data['text'],  # Same text content
                                'type': cell_data['type'],  # Same cell type
                                'rowspan': 1,  # Individual cell properties
                                'colspan': 1,
                                'original_cell': False,  # This is a reference
                                'original_rowspan': cell_data['original_rowspan'],  # Preserve original span info
                                'original_colspan': cell_data['original_colspan'],
                                'is_footer': cell_data['is_footer'],
                                'span_origin': (row_idx, logical_col)  # Track where this span originated
                            }
                            logical_grid[target_row][target_col] = span_cell
            
            logical_col += colspan
    
    # Phase 4: Convert logical grid to the expected format
    # Fill any remaining None positions with empty cells
    empty_cells_filled = 0
    for row_idx in range(len(logical_grid)):
        for col_idx in range(len(logical_grid[row_idx])):
            if logical_grid[row_idx][col_idx] is None:
                logical_grid[row_idx][col_idx] = {
                    'text': '',
                    'type': 'td',
                    'rowspan': 1,
                    'colspan': 1,
                    'original_cell': False,
                    'original_rowspan': 1,
                    'original_colspan': 1,
                    'is_footer': False
                }
                empty_cells_filled += 1
        
        logger.debug(f"Row {row_idx}: {len(logical_grid[row_idx])} columns")
    
    if empty_cells_filled > 0:
        logger.debug(f"Filled {empty_cells_filled} empty cell positions")
    
    logger.info(f"Grid parsing complete: {len(logical_grid)} x {max_cols} logical grid created")
    return logical_grid

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


def process_table(table_html: str, apply_rag_fix: bool = True) -> List[LogicRule]:
    """Main table processing function with semantic diagnostics"""
    
    logger.info("Processing original table structure directly")
    
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    
    # Check for semantic structure issues
    th_cells = table.find_all('th')
    td_cells = table.find_all('td')
    total_cells = len(th_cells) + len(td_cells)
    
    if len(th_cells) == 0 and total_cells > 0:
        logger.warning("Table uses only <td> elements - no <th> header elements found")
        logger.info("This may reduce semantic precision of extracted rules")
        logger.info("Consider using <th> tags for headers to improve processing")
    elif len(th_cells) < total_cells * 0.1:  # Less than 10% headers
        logger.warning(f"Table has very few header elements: {len(th_cells)} <th> vs {len(td_cells)} <td>")
        logger.info("Consider marking header cells with <th> tags for better rule context")
    
    grid = parse_and_unmerge_table_bulletproof(table)
    if not grid:
        logger.warning("Table parsing resulted in empty grid")
        return []
    
    # Check if table is empty (no meaningful text content)
    has_content = False
    for row in grid:
        for cell in row:
            if cell.get('text', '').strip():
                has_content = True
                break
        if has_content:
            break
    
    if not has_content:
        logger.warning("Table contains no text content - skipping empty table")
        return []
    
    logger.info(f"Parsed grid: {len(grid)} rows x {len(grid[0]) if grid else 0} columns")
    
    # Rest of processing...
    factory = TableProcessorFactory()
    result = factory.process_table(grid, table)
    
    logger.info(f"Processed with {result.processor_type}: {len(result.rules)} rules")

    if apply_rag_fix:
        fixed_result = apply_rag_fixes(result)
        logger.info(f"After RAG fix: {len(fixed_result.rules)} rules")
        return fixed_result.rules
    else:
        logger.info("Skipping RAG fixes - returning raw rules")
        return result.rules

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description='table2rules - Universal Table to Logic Rules')
    parser.add_argument('--format', choices=['descriptive', 'structured'], 
                   default='descriptive', help='Output format')
    parser.add_argument('--input', default='input.md', help='Input file')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('--raw', action='store_true', help='Skip RAG fixes, emit raw rules')
    
    args = parser.parse_args()
    
    # Determine if RAG fixes should be applied
    apply_rag_fix = not args.raw
    
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
            rules = process_table(table_html, apply_rag_fix=apply_rag_fix)
            all_rules.extend(rules)
        
        # Format-aware output writer with soft chunking for large tables
        SOFT_CHUNK_SIZE = 50  # Rules per soft chunk

        with open('output.md', 'w', encoding='utf-8') as f:
            if all_rules:
                # Add main table start marker
                f.write(f"<!-- TABLE_START: {len(all_rules)} rules -->\n")
                f.write(f"<!-- SOURCE: {args.input} -->\n\n")
                
                for i, rule in enumerate(all_rules):
                    # Add soft chunk markers for large tables
                    if i > 0 and i % SOFT_CHUNK_SIZE == 0:
                        f.write(f"\n<!-- SOFT_CHUNK: Rules {i-SOFT_CHUNK_SIZE+1}-{i} -->\n\n")
                    
                    if args.format == 'structured':
                        content = rule.to_rule_string()
                    else:
                        formats = rule.to_natural_formats()
                        content = formats.get(args.format, rule.to_rule_string())
                    
                    f.write(f"{content}\n")
                
                # Add final soft chunk marker if needed
                if len(all_rules) > SOFT_CHUNK_SIZE:
                    remaining_start = (len(all_rules) // SOFT_CHUNK_SIZE) * SOFT_CHUNK_SIZE + 1
                    f.write(f"\n<!-- SOFT_CHUNK: Rules {remaining_start}-{len(all_rules)} -->\n")
                
                # Add table end marker
                f.write(f"\n<!-- TABLE_END -->\n")

        
        logger.info(f"Generated {len(all_rules)} rules")
        
    except FileNotFoundError:
        logger.error(f"File {args.input} not found")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()