#!/usr/bin/env python3
"""
table2rules - Universal Table to Logic Rules
Core file with parsing and CLI only
"""

import re
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
import logging
import argparse
from table_processor_factory import TableProcessorFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LogicRule:
    conditions: List[str]
    outcome: str
    position: Tuple[int, int]
    is_summary: bool = False
    
    def to_rule_string(self) -> str:
        """Original structured format"""
        if not self.conditions:
            return f"FACT: The value is '{self.outcome}'"
        
        condition_parts = [f'"{c}"' for c in self.conditions]
        conditions_str = " AND ".join(condition_parts)
        
        if self.is_summary:
            return f"SUMMARY: IF {conditions_str} THEN the value is '{self.outcome}'"
        else:
            return f"IF {conditions_str} THEN the value is '{self.outcome}'"
    
    def to_natural_formats(self) -> Dict[str, str]:
        """Generate multiple natural language formats"""
        return {
            'conversational': self._to_conversational(),
            'question_answer': self._to_qa_format(),
            'descriptive': self._to_descriptive(),
            'searchable': self._to_searchable(),
            'structured': self.to_rule_string()
        }
    
    def _to_conversational(self) -> str:
        if not self.conditions:
            return f"The value is {self.outcome}"
        context = ", ".join(self.conditions)
        return f"For {context}, the value is {self.outcome}"
    
    def _to_qa_format(self) -> str:
        if not self.conditions:
            return f"What is the value? {self.outcome}"
        context = " ".join(self.conditions)
        return f"What is the value for {context}? The answer is {self.outcome}"
    
    def _to_descriptive(self) -> str:
        """Rich semantic description that preserves all context."""
        if not self.conditions:
            return f"The value is {self.outcome}"
        
        # Build complete context string
        all_context = " ".join(self.conditions)
        return f"{all_context}, the content is {self.outcome}"
    
    def _to_searchable(self) -> str:
        if not self.conditions:
            return f"value amount data {self.outcome}"
        context = " ".join(self.conditions)
        return f"{context} value amount {self.outcome}"
    
    def _extract_categories(self) -> Dict[str, str]:
        categories = {}
        for condition in self.conditions:
            clean = condition.lower()
            if 'day' in clean:
                categories['day'] = condition
            elif re.search(r'\d{1,2}:\d{2}', clean):
                categories['time'] = condition
            elif any(word in clean for word in ['hall', 'room', 'track']):
                categories['location'] = condition
        return categories


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
    """Parse table into grid format"""
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
    
    # Parse cells
    parsed_cells = []
    for row_idx, row in enumerate(actual_rows):
        cells = row.find_all(['td', 'th'])
        row_cells = []
        for cell in cells:
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
    
    # Build grid
    occupied_positions = set()
    max_cols = 0
    
    # Calculate grid size
    for row_idx, row_cells in enumerate(parsed_cells):
        col_idx = 0
        for cell in row_cells:
            while (row_idx, col_idx) in occupied_positions:
                col_idx += 1
            for r in range(cell['rowspan']):
                for c in range(cell['colspan']):
                    occupied_positions.add((row_idx + r, col_idx + c))
            max_cols = max(max_cols, col_idx + cell['colspan'])
            col_idx += cell['colspan']
    
    max_rows = len(actual_rows)
    grid = [[{'text': '', 'type': 'td', 'original_cell': False, 'is_footer': False} 
             for _ in range(max_cols)] for _ in range(max_rows)]
    occupied_positions.clear()
    
    # Fill grid
    for row_idx, row_cells in enumerate(parsed_cells):
        col_idx = 0
        for cell in row_cells:
            while (row_idx, col_idx) in occupied_positions:
                col_idx += 1
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
                        occupied_positions.add((target_row, target_col))
            col_idx += cell['colspan']
    
    return grid


def process_table(table_html: str) -> List[LogicRule]:
    """Main table processing function"""
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    
    grid = parse_and_unmerge_table_bulletproof(table)
    if not grid:
        logger.warning("Table parsing resulted in empty grid")
        return []
    
    logger.info(f"Parsed grid: {len(grid)} rows x {len(grid[0]) if grid else 0} columns")
    
    # Use factory to process
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