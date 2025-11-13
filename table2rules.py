#!/usr/bin/env python3
"""
table2rules - Universal Table to Logic Rules

Transforms well-formed HTML tables into queryable IF-THEN rules using
mathematical grid processing and hierarchical context extraction.

Core pipeline:
    HTML Input → Grid Parser → Processor Selection → Rule Generation → RAG Cleanup → Output

Usage:
    python3 table2rules.py --format descriptive
    python3 table2rules.py --format structured --raw
    python3 table2rules.py --input myfile.html --verbose
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
    """
    Clean HTML text, fix encoding issues, and normalize whitespace.
    
    This function handles common encoding problems from HTML sources
    while preserving important formatting like numbers with commas.
    
    Args:
        text: Raw text from HTML cell
        
    Returns:
        Cleaned text with normalized whitespace and fixed encoding
        
    Examples:
        "Hello  World" → "Hello World"
        "3,000 ,000" → "3,000,000"
        "Systems&nbsp;at&nbsp;Scale" → "Systems at Scale"
    """
    if not text:
        return ""
    
    # Step 1: Fix known bad encoding characters
    # UTF-8 characters that were misread as Windows-1252
    replacements = {
        'Ã¢â‚¬â€': '—',   # Em dash
        'Ã¢â‚¬': '—',     # Em dash variant
        'Ã¢â‚¬â„¢': "'",  # Right single quote
        'Â': ' ',         # Non-breaking space often becomes this
        '&nbsp;': ' '     # HTML non-breaking space
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Step 2: Handle standard HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # Step 3: Remove any remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Step 4: Normalize whitespace carefully
    # First, fix broken number formatting (e.g., "3,000 ,000" → "3,000,000")
    text = re.sub(r'(\d+)\s*,\s*(\d{3})', r'\1,\2', text)
    
    # Then normalize other whitespace to single spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_and_unmerge_table_bulletproof(table) -> List[List[Dict]]:
    """
    Universal grid parser - handles spans mathematically without heuristics.
    
    This parser converts HTML tables with rowspan/colspan into a logical
    2D grid where every position is filled. It uses mathematical span
    simulation rather than trying to "repair" the table structure.
    
    Algorithm:
    1. Calculate true grid dimensions by simulating span expansion
    2. Create empty logical grid
    3. Fill grid positions by processing each physical cell
    4. Fill any remaining gaps with empty cells
    
    Args:
        table: BeautifulSoup table element
        
    Returns:
        Logical 2D grid where grid[row][col] = cell_dict
        Each cell_dict contains:
            - text: cleaned cell text
            - type: 'th' or 'td'
            - rowspan: always 1 (span expanded)
            - colspan: always 1 (span expanded)
            - original_cell: True if this is the source cell, False if reference
            - original_rowspan: the original rowspan value
            - original_colspan: the original colspan value
            
    Example:
        Input:  <tr><td rowspan="2">A</td><td>B</td></tr>
                <tr><td>C</td></tr>
                
        Output: [[{text:'A', ...}, {text:'B', ...}],
                 [{text:'A', ...}, {text:'C', ...}]]
    """
    
    # Get all physical rows
    actual_rows = table.find_all('tr')
    if not actual_rows:
        logger.debug("No table rows found")
        return []
    
    # Phase 1: Calculate the true grid dimensions
    # We need to account for spans when calculating column count
    max_cols = 0
    occupied = {}  # Track (row, col) positions occupied by rowspans
    
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'])
        logical_col = 0
        
        for cell in cells:
            # Skip positions already occupied by cells from previous rows
            while (row_idx, logical_col) in occupied:
                logical_col += 1
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            
            # Mark all positions this cell will occupy
            for r in range(rowspan):
                for c in range(colspan):
                    occupied[(row_idx + r, logical_col + c)] = True
            
            logical_col += colspan
        
        max_cols = max(max_cols, logical_col)
    
    logger.debug(f"Calculated grid dimensions: {len(actual_rows)} rows x {max_cols} columns")
    
    # Phase 2: Create empty logical grid
    logical_grid = [[None for _ in range(max_cols)] for _ in range(len(actual_rows))]
    
    # Phase 3: Fill the logical grid by processing each physical cell
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'])
        logical_col = 0
        
        for cell_idx, cell in enumerate(cells):
            # Skip positions already occupied by spanning cells from above
            while (logical_col < max_cols and 
                   logical_grid[row_idx][logical_col] is not None):
                logical_col += 1
            
            if logical_col >= max_cols:
                logger.warning(f"Row {row_idx}: Cell overflow at position {logical_col}")
                break
            
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
                'is_footer': False
            }
            
            logger.debug(
                f"Cell at ({row_idx},{logical_col}): "
                f"<{cell.name}> '{cell_data['text'][:30]}...' "
                f"(rowspan={rowspan}, colspan={colspan})"
            )
            
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
                            # This is a spanned position - create a reference
                            span_cell = {
                                'text': cell_data['text'],
                                'type': cell_data['type'],
                                'rowspan': 1,
                                'colspan': 1,
                                'original_cell': False,
                                'original_rowspan': cell_data['original_rowspan'],
                                'original_colspan': cell_data['original_colspan'],
                                'is_footer': cell_data['is_footer'],
                                'span_origin': (row_idx, logical_col)
                            }
                            logical_grid[target_row][target_col] = span_cell
            
            logical_col += colspan
    
    # Phase 4: Fill any remaining None positions with empty cells
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
        
        logger.debug(f"Row {row_idx}: {len(logical_grid[row_idx])} columns filled")
    
    if empty_cells_filled > 0:
        logger.debug(f"Filled {empty_cells_filled} empty cell positions")
    
    logger.info(f"Grid parsing complete: {len(logical_grid)} x {max_cols} logical grid created")
    return logical_grid


def process_table(table_html: str, apply_rag_fix: bool = True) -> List[LogicRule]:
    """
    Main table processing function.
    
    Pipeline:
    1. Parse HTML into BeautifulSoup
    2. Check for semantic structure issues
    3. Parse into logical grid
    4. Route to appropriate processor
    5. Apply RAG cleanup (if enabled)
    
    Args:
        table_html: Raw HTML string containing <table> element
        apply_rag_fix: Whether to apply RAG cleanup (default True)
        
    Returns:
        List of LogicRule objects
    """
    
    logger.info("Processing table structure")
    
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        logger.warning("No <table> element found in HTML")
        return []
    
    # Check for semantic structure quality (informational only)
    th_cells = table.find_all('th')
    td_cells = table.find_all('td')
    total_cells = len(th_cells) + len(td_cells)
    
    if len(th_cells) == 0 and total_cells > 0:
        logger.warning("Table uses only <td> elements - no <th> header elements found")
        logger.info("Consider using <th> tags for headers to improve semantic precision")
    elif len(th_cells) < total_cells * 0.1:
        logger.warning(
            f"Table has very few header elements: {len(th_cells)} <th> vs {len(td_cells)} <td>"
        )
        logger.info("Consider marking header cells with <th> tags for better rule context")
    
    # Parse into logical grid
    grid = parse_and_unmerge_table_bulletproof(table)
    if not grid:
        logger.warning("Table parsing resulted in empty grid")
        return []
    
    # Check if table is empty (no meaningful text content)
    has_content = any(
        cell.get('text', '').strip() 
        for row in grid 
        for cell in row
    )
    
    if not has_content:
        logger.warning("Table contains no text content - skipping empty table")
        return []
    
    logger.info(f"Parsed grid: {len(grid)} rows x {len(grid[0]) if grid else 0} columns")
    
    # Route to appropriate processor
    factory = TableProcessorFactory()
    result = factory.process_table(grid, table)
    
    logger.info(f"Processed with {result.processor_type}: {len(result.rules)} rules")

    # Apply RAG cleanup if requested
    if apply_rag_fix:
        fixed_result = apply_rag_fixes(result)
        logger.info(f"After RAG fix: {len(fixed_result.rules)} rules")
        return fixed_result.rules
    else:
        logger.info("Skipping RAG fixes - returning raw rules")
        return result.rules


def main():
    """
    CLI entry point for table2rules.
    
    Parses command-line arguments and processes tables from input file.
    """
    parser = argparse.ArgumentParser(
        description='table2rules - Universal Table to Logic Rules',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate descriptive rules (default)
  python3 table2rules.py
  
  # Generate structured IF-THEN rules
  python3 table2rules.py --format structured
  
  # Skip RAG cleanup (raw output)
  python3 table2rules.py --raw
  
  # Process custom input file with verbose logging
  python3 table2rules.py --input myfile.html --verbose
        """
    )
    
    parser.add_argument(
        '--format', 
        choices=['descriptive', 'structured'], 
        default='descriptive',
        help='Output format: descriptive (RAG-optimized) or structured (IF-THEN)'
    )
    parser.add_argument(
        '--input', 
        default='input.md',
        help='Input file containing HTML table (default: input.md)'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose debug logging'
    )
    parser.add_argument(
        '--raw', 
        action='store_true',
        help='Skip RAG fixes, emit raw rules without cleanup'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine if RAG fixes should be applied
    apply_rag_fix = not args.raw
    
    try:
        # Read input file
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract all tables from the document
        table_pattern = r'<table[^>]*>.*?</table>'
        tables = re.findall(table_pattern, content, re.DOTALL)
        
        if not tables:
            logger.warning(f"No tables found in {args.input}")
            return
        
        logger.info(f"Found {len(tables)} table(s) in {args.input}")
        
        # Process all tables
        all_rules = []
        for i, table_html in enumerate(tables, 1):
            logger.info(f"Processing table {i}/{len(tables)}...")
            rules = process_table(table_html, apply_rag_fix=apply_rag_fix)
            all_rules.extend(rules)
        
        # Write output with chunking markers
        SOFT_CHUNK_SIZE = 50  # Rules per soft chunk
        
        with open('output.md', 'w', encoding='utf-8') as f:
            if all_rules:
                # Add main table start marker
                f.write(f"<!-- TABLE_START: {len(all_rules)} rules -->\n")
                f.write(f"<!-- SOURCE: {args.input} -->\n\n")
                
                # Write rules with soft chunking
                for i, rule in enumerate(all_rules, 1):
                    # Format the rule based on requested format
                    if args.format == 'structured':
                        content = rule.to_rule_string()
                    else:
                        formats = rule.to_natural_formats()
                        content = formats.get(args.format, rule.to_rule_string())
                    
                    f.write(f"{content}\n")
                    
                    # Add soft chunk markers at regular intervals
                    # Place marker AFTER every 50th rule (not before)
                    if i % SOFT_CHUNK_SIZE == 0 and i < len(all_rules):
                        chunk_start = i - SOFT_CHUNK_SIZE + 1
                        f.write(f"\n<!-- SOFT_CHUNK: Rules {chunk_start}-{i} -->\n\n")
                
                # Add final soft chunk marker if needed
                if len(all_rules) > SOFT_CHUNK_SIZE:
                    final_chunk_start = (len(all_rules) // SOFT_CHUNK_SIZE) * SOFT_CHUNK_SIZE + 1
                    if final_chunk_start <= len(all_rules):
                        f.write(f"\n<!-- SOFT_CHUNK: Rules {final_chunk_start}-{len(all_rules)} -->\n")
                
                # Add table end marker
                f.write(f"\n<!-- TABLE_END -->\n")
        
        logger.info(f"✓ Generated {len(all_rules)} rules → output.md")
        
    except FileNotFoundError:
        logger.error(f"File {args.input} not found")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()