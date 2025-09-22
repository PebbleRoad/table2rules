#!/usr/bin/env python3
"""
table2rules - Universal Table to Logic Rules
"""

import re
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import argparse
from table_classifier import TableClassifier, TableType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_html_table_structure(table_html: str) -> Dict[str, Any]:
    """
    Validate HTML table structure for common issues that cause extraction problems.
    Returns validation results with errors and warnings.
    """
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'table_found': False
    }
    
    # Check raw HTML for mismatched tags before BeautifulSoup auto-corrects them
    if '<table' in table_html.lower():
        validation_result['table_found'] = True
        
        # Check for mismatched td/th tags in raw HTML (more precise matching)
        # Look for individual cells, not multi-line spans
        lines = table_html.split('\n')
        for line_num, line in enumerate(lines):
            line = line.strip()
            # Only check lines that contain a complete cell definition
            if '<td' in line and '</th>' in line and line.count('<td') == 1 and line.count('</th>') == 1:
                validation_result['errors'].append(f"Line {line_num + 1}: Cell opens with <td> but closes with </th>")
            elif '<th' in line and '</td>' in line and line.count('<th') == 1 and line.count('</td>') == 1:
                validation_result['errors'].append(f"Line {line_num + 1}: Cell opens with <th> but closes with </td>")
        
    else:
        validation_result['is_valid'] = False
        validation_result['errors'].append("No <table> element found in HTML")
        return validation_result
    
    # Continue with BeautifulSoup validation for other issues
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    
    if not table:
        validation_result['is_valid'] = False
        validation_result['errors'].append("No <table> element found after HTML parsing")
        return validation_result
    
    # Check for invalid rowspan/colspan values
    rows = table.find_all('tr')
    for row_idx, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        for cell_idx, cell in enumerate(cells):
            rowspan = cell.get('rowspan')
            colspan = cell.get('colspan')
            
            if rowspan:
                try:
                    rowspan_val = int(rowspan)
                    if rowspan_val < 1:
                        validation_result['errors'].append(f"Row {row_idx}, Cell {cell_idx}: Invalid rowspan '{rowspan}' (must be >= 1)")
                except ValueError:
                    validation_result['errors'].append(f"Row {row_idx}, Cell {cell_idx}: Non-numeric rowspan '{rowspan}'")
            
            if colspan:
                try:
                    colspan_val = int(colspan)
                    if colspan_val < 1:
                        validation_result['errors'].append(f"Row {row_idx}, Cell {cell_idx}: Invalid colspan '{colspan}' (must be >= 1)")
                except ValueError:
                    validation_result['errors'].append(f"Row {row_idx}, Cell {cell_idx}: Non-numeric colspan '{colspan}'")
    
    # Check for empty table
    if len(rows) == 0:
        validation_result['errors'].append("Table contains no rows")
    elif all(len(row.find_all(['td', 'th'])) == 0 for row in rows):
        validation_result['errors'].append("Table contains no cells")
    
    if validation_result['errors']:
        validation_result['is_valid'] = False
    
    return validation_result


class TableOrientation(Enum):
    COLUMN_BASED = "column_based"
    ROW_BASED = "row_based"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class TableStructure:
    orientation: TableOrientation
    confidence: float
    data_start_row: int
    data_start_col: int
    analysis: Dict[str, Any]


@dataclass
class LogicRule:
    conditions: List[str]
    outcome: str
    position: Tuple[int, int]
    is_summary: bool = False
    
    def to_rule_string(self) -> str:
        """Original structured format for backward compatibility"""
        if not self.conditions:
            return f"FACT: The value is '{self.outcome}'"
    
        condition_parts = [f'"{c}"' for c in self.conditions]
        conditions_str = " AND ".join(condition_parts)
        
        if self.is_summary:
            return f"SUMMARY: IF {conditions_str} THEN the value is '{self.outcome}'"
        else:
            return f"IF {conditions_str} THEN the value is '{self.outcome}'"
    
    def to_natural_formats(self) -> Dict[str, str]:
        """Generate multiple natural language formats for RAG optimization"""
        return {
            'conversational': self._to_conversational(),
            'question_answer': self._to_qa_format(),
            'descriptive': self._to_descriptive(),
            'searchable': self._to_searchable(),
            'structured': self.to_rule_string()  # Keep original for exact matching
        }
    
    def _to_conversational(self) -> str:
        """Natural language format optimized for vector similarity"""
        if not self.conditions:
            return f"The value is {self.outcome}"
        
        # Clean and join conditions naturally
        clean_conditions = [c.strip('"\'') for c in self.conditions]
        context = ", ".join(clean_conditions)
        
        return f"For {context}, the value is {self.outcome}"
    
    def _to_qa_format(self) -> str:
        """Question-answer format for query matching"""
        if not self.conditions:
            return f"What is the value? {self.outcome}"
        
        clean_conditions = [c.strip('"\'') for c in self.conditions]
        context = " ".join(clean_conditions)
        
        return f"What is the value for {context}? The answer is {self.outcome}"
    
    def _to_descriptive(self) -> str:
        """Rich semantic description with category extraction"""
        if not self.conditions:
            return f"The value is {self.outcome}"
        
        categories = self._extract_categories()
        
        if categories.get('plan') and categories.get('benefit_type'):
            return f"Under {categories['plan']}, the {categories['benefit_type']} benefit provides {self.outcome}"
        elif categories.get('time') and categories.get('location'):
            return f"At {categories['time']} in {categories['location']}, the content is {self.outcome}"
        else:
            # Generic descriptive format
            clean_conditions = [c.strip('"\'') for c in self.conditions]
            context = " ".join(clean_conditions)
            return f"The {context} value is {self.outcome}"
    
    def _to_searchable(self) -> str:
        """Keyword-optimized format for search engines"""
        if not self.conditions:
            return f"value amount data {self.outcome}"
        
        clean_conditions = [c.strip('"\'') for c in self.conditions]
        
        # Add relevant keywords based on content
        keywords = []
        for condition in clean_conditions:
            if any(word in condition.lower() for word in ['plan', 'coverage', 'benefit']):
                keywords.extend(['insurance', 'coverage', 'benefit', 'plan'])
            elif any(word in condition.lower() for word in ['day', 'time', 'session']):
                keywords.extend(['schedule', 'time', 'session', 'event'])
            elif '$' in self.outcome or any(word in self.outcome.lower() for word in ['cost', 'price']):
                keywords.extend(['cost', 'price', 'amount', 'value'])
        
        unique_keywords = list(dict.fromkeys(keywords))  # Remove duplicates while preserving order
        keyword_str = " ".join(unique_keywords)
        
        context = " ".join(clean_conditions)
        return f"{context} {keyword_str} value amount {self.outcome}"
    
    def _extract_categories(self) -> Dict[str, str]:
        """Extract semantic categories from conditions for better natural language"""
        categories = {}
        
        for condition in self.conditions:
            clean = condition.strip('"\'').lower()
            
            # Plan/type detection
            if clean in ['a', 'b', 'c'] or 'plan' in clean:
                categories['plan'] = condition.strip('"\'')
            elif clean in ['basic', 'classic', 'premium', 'standard']:
                categories['benefit_type'] = condition.strip('"\'')
            elif 'benefit' in clean or 'coverage' in clean:
                categories['coverage_area'] = condition.strip('"\'')
            
            # Time/location detection
            elif 'day' in clean or clean.startswith('q') or ':' in clean:
                categories['time'] = condition.strip('"\'')
            elif 'hall' in clean or 'room' in clean or 'track' in clean:
                categories['location'] = condition.strip('"\'')
                
        return categories


def _get_cell_type(cell: Dict) -> str:
    """Categorize a cell's content as TEXT, NUMERIC, or EMPTY."""
    text = cell.get('text', '').strip()
    if not text:
        return 'EMPTY'
    
    numeric_part = re.sub(r'[$,S%()-]', '', text).strip().replace(',', '')
    if numeric_part.replace('.', '', 1).isdigit() and len(numeric_part) > 0:
        return 'NUMERIC'
    
    return 'TEXT'

def _should_skip_as_likely_header(outcome_text: str, conditions: List[str]) -> bool:
    """
    Universal filter to detect when text that appears to be data is actually a header
    that got misclassified due to complex table structure.
    """
    if len(conditions) >= 2:
            return False
            
    if not outcome_text or not conditions:
        return False
    
    outcome_lower = outcome_text.lower().strip()
    
    # Pattern 1: Text that spans multiple logical data columns is likely a header
    if len(conditions) >= 6:  # Only filter if we have excessive conditions (true spanning)
        condition_text = ' '.join(conditions).lower()
        
        spanning_indicators = [
            len(set(len(c.split()) for c in conditions)) == 1 and len(conditions) >= 3,
            len(conditions) >= 4 and len(set(c.lower() for c in conditions)) != len(conditions),
            any(len(c) <= 3 for c in conditions) and any(len(c) > 10 for c in conditions),
        ]
        
        if any(spanning_indicators):
            return True
    
    # Pattern 2: Structural headers (things that clearly span contexts inappropriately)
    structural_header_patterns = [
        # Very long text that's clearly a label, not content
        len(outcome_text) > 100 and ('legend' in outcome_lower or 'note' in outcome_lower),
        
        # Text that matches common structural patterns
        outcome_lower.strip() in ('total', 'subtotal'), # Check for exact match
        
        # Parenthetical descriptions that are too detailed for content
        '(' in outcome_text and ')' in outcome_text and len(outcome_text) > 50 and outcome_text.count('(') > 1,
    ]
    
    # Pattern 3: Context-aware filtering - only filter if content lacks proper context
    # Content with specific time/location context is likely legitimate data
    has_specific_context = (
        len(conditions) >= 2 and  # Has some context
        any('day' in str(c).lower() for c in conditions) or  # Has day context
        any(c.replace(':', '').isdigit() for c in conditions)  # Has time context
    )
    
    # If content has specific context, be very conservative about filtering
    if has_specific_context:
        # Only filter obvious structural elements
        return any(structural_header_patterns)
    
    # For content without specific context, apply broader filtering
    header_linguistic_patterns = [
            # This line is changed to add a length check
            len(outcome_text.split()) >= 3 and any(word.istitle() for word in outcome_text.split()) and len(outcome_text) < 50,
            outcome_text.count(' ') >= 2 and len(outcome_text) > 20,
            outcome_text.endswith(('total', 'Total')) or '(' in outcome_text and len(outcome_text.split()) >= 3,
        ]
    
    if any(structural_header_patterns or header_linguistic_patterns):
        return True
    
    return False

def is_placeholder_content(text: str, is_spanning: bool = False) -> bool:
    """
    Detect if content is a placeholder that shouldn't generate rules.
    Universal detection for any table type.
    """
    if not text or not text.strip():
        return True
    
    text = text.strip()
    
    # Common placeholder patterns across all domains
    placeholder_patterns = [
        'N/A', 'n/a', 'NA', 'na',
        'TBD', 'tbd', 'TBA', 'tba',
        '...', '…',
        'null', 'NULL', 'None', 'none',
        'empty', 'Empty', 'EMPTY'
    ]
    
    # Exact matches for common placeholders
    if text in placeholder_patterns:
        return True
    
    # For spanning cells, be more aggressive about placeholder detection
    if is_spanning:
        # Text that's just punctuation or symbols
        if re.match(r'^[^\w]*$', text):
            return True
        
        # Very short generic text in spanning positions
        if len(text) <= 3 and text.lower() in ['tbd', 'na', 'no', 'yes']:
            return True
    
    return False

def debug_context_maps(grid: List[List[Dict]], row_context_map: Dict, col_context_map: Dict, structure: TableStructure):
    """
    Debug function to validate context mapping is working correctly.
    Works for any table structure - no domain assumptions.
    """
    num_rows = len(grid)
    num_cols = len(grid[0])
    
    logger.debug("=== CONTEXT MAP VALIDATION ===")
    
    # Check a few key data positions using actual detected boundaries
    data_start_row = structure.data_start_row
    data_start_col = structure.data_start_col
    
    for r in range(data_start_row, min(data_start_row + 3, num_rows)):
        for c in range(data_start_col, min(data_start_col + 3, num_cols)):
            cell = grid[r][c]
            if cell.get('text', '').strip():
                row_context = row_context_map.get(r, [])
                col_context = col_context_map.get(c, [])
                logger.debug(f"Position ({r},{c}): '{cell.get('text', '')}' -> Row: {row_context}, Col: {col_context}")
    
    # Validate spanning cell coverage
    for r in range(num_rows):
        for c in range(num_cols):
            cell = grid[r][c]
            if cell.get('original_cell', False):
                original_rowspan = cell.get('original_rowspan', 1)
                original_colspan = cell.get('original_colspan', 1)
                if original_rowspan > 1 or original_colspan > 1:
                    logger.debug(f"Spanning cell at ({r},{c}): rowspan={original_rowspan}, colspan={original_colspan}, text='{cell.get('text', '')}'")

class HierarchicalTableAnalyzer:
    """
    Analyzes table structure using hierarchy-aware tree-based detection.
    Builds separate trees for column and row headers to handle complex spanning structures.
    """
    
    def analyze_table_structure(self, table_data: Dict[str, Any]) -> TableStructure:
        grid = table_data.get("grid", [])
        if not grid or not grid[0]:
            return TableStructure(orientation=TableOrientation.UNKNOWN, confidence=0.0, data_start_row=0, data_start_col=0, analysis={})

        num_rows = len(grid)
        num_cols = len(grid[0])

        # Build hierarchical trees for headers
        column_header_tree = self._build_column_header_tree(grid, num_rows, num_cols)
        row_header_tree = self._build_row_header_tree(grid, num_rows, num_cols)
        
        # Find data region boundaries based on tree analysis
        data_boundaries = self._find_data_boundaries_from_trees(column_header_tree, row_header_tree, num_rows, num_cols)
        
        orientation = self._determine_orientation(data_boundaries['row_start'], data_boundaries['col_start'])
        confidence = min(column_header_tree['confidence'], row_header_tree['confidence'])

        analysis = {
            "detected_data_start_row": data_boundaries['row_start'],
            "detected_data_start_col": data_boundaries['col_start'],
            "grid_size": (num_rows, num_cols),
            "detection_method": "hierarchical_tree_based",
            "column_header_depth": column_header_tree['max_depth'],
            "row_header_depth": row_header_tree['max_depth']
        }
        
        logger.info(f"Table analysis: {orientation.value} (Data region starts at row {data_boundaries['row_start']}, col {data_boundaries['col_start']}, col_tree_depth: {column_header_tree['max_depth']}, row_tree_depth: {row_header_tree['max_depth']})")

        return TableStructure(
            orientation=orientation,
            confidence=confidence,
            data_start_row=data_boundaries['row_start'],
            data_start_col=data_boundaries['col_start'],
            analysis=analysis
        )
    
    def _classify_processing_approach(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> str:
        """
        Determine processing approach based on structural characteristics.
        Returns 'skip_titles' or 'simple_boundary' based on table structure.
        """
        # Analyze structural patterns
        wide_spanning_rows = 0
        multi_th_rows = 0
    
        for row_idx in range(min(4, num_rows)):
            row = grid[row_idx]
            th_count = sum(1 for c in range(num_cols) if row[c].get('type') == 'th')
        
            # Count rows with multiple th elements (structural headers)
            if th_count >= 2:
                multi_th_rows += 1
        
            # Count rows with wide-spanning cells (potential interfering titles)
            for col_idx in range(num_cols):
                cell = row[col_idx]
                if (cell.get('original_cell', False) and 
                    cell.get('original_colspan', 1) >= num_cols * 0.8):
                    wide_spanning_rows += 1
                    break
    
        logger.debug(f" Structural analysis - multi_th_rows: {multi_th_rows}, wide_spanning_rows: {wide_spanning_rows}")
    
        # Decision based on structural patterns
        if wide_spanning_rows >= 1 and multi_th_rows <= 1:
            logger.debug("Using SKIP_TITLES approach (contextual spanning pattern)")
            return 'skip_titles'  # Tables with shared context across data groups
        elif multi_th_rows >= 2:
            logger.debug("Using SIMPLE_BOUNDARY approach (multiplicative spanning pattern)")
            return 'simple_boundary'  # Tables with independent data relationships
        else:
            logger.debug("Using SIMPLE_BOUNDARY approach (default multiplicative spanning)")
            return 'simple_boundary'  # Default to independent data relationships
    
    def _find_column_header_boundary_simple(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> int:
        """Simple boundary detection for schedule tables (from working version)."""
        for row_idx in range(1, min(num_rows, 6)):
            th_count = sum(1 for c in range(num_cols) if grid[row_idx][c].get('type') == 'th')
            td_count = sum(1 for c in range(num_cols) if grid[row_idx][c].get('type') == 'td')
    
            if td_count > th_count and td_count >= num_cols * 0.6:
                return row_idx
    
        return min(3, num_rows)

    def _find_column_header_boundary_enhanced(self, grid: List[List[Dict]], num_rows: int, num_cols: int, start_row: int) -> int:
        """Enhanced boundary detection for contextual spanning tables (content-aware)"""
        for row_idx in range(start_row + 1, min(num_rows, start_row + 6)):
            row = grid[row_idx]
        
            numeric_cells = 0
            text_cells = 0
            empty_cells = 0
        
            for col_idx in range(num_cols):
                cell_text = row[col_idx].get('text', '').strip()
                if not cell_text:
                    empty_cells += 1
                elif any(char.isdigit() for char in cell_text) or '$' in cell_text:
                    numeric_cells += 1
                else:
                    text_cells += 1
        
            filled_cells = numeric_cells + text_cells
        
            if numeric_cells >= filled_cells * 0.5 and filled_cells >= num_cols * 0.5:
                return row_idx
        
            if text_cells > 0 and numeric_cells == 0:
                continue
    
        return min(start_row + 3, num_rows)
    
    def _build_column_header_tree(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> Dict[str, Any]:
        # Determine processing approach based on structure
        approach = self._classify_processing_approach(grid, num_rows, num_cols)
    
        if approach == 'skip_titles':
            # Handle tables with interfering title rows
            header_start_row = self._find_first_non_title_row(grid, num_rows, num_cols)
            header_row_end = self._find_column_header_boundary_enhanced(grid, num_rows, num_cols, header_start_row)
        else:
            # Handle tables with clean structural headers
            header_start_row = 0
            header_row_end = self._find_column_header_boundary_simple(grid, num_rows, num_cols)
    
        # Build tree structure
        tree_levels = []
    
        for row_idx in range(header_start_row, header_row_end):
            level_nodes = []
            col_position = 0
    
            for col_idx in range(num_cols):
                cell = grid[row_idx][col_idx]
            
                if not cell.get('original_cell', False):
                    continue
                
                text = cell.get('text', '').strip()
                if not text:
                    continue
            
                node = {
                    'text': text,
                    'row': row_idx,
                    'col': col_idx,
                    'rowspan': cell.get('rowspan', 1),
                    'colspan': cell.get('original_colspan', 1),
                    'start_col': col_position,
                    'end_col': col_position + cell.get('colspan', 1),
                    'children': [],
                    'parent': None
                }
        
                level_nodes.append(node)
                col_position += cell.get('colspan', 1)
    
            tree_levels.append(level_nodes)

        # Connect parent-child relationships
        for level_idx in range(len(tree_levels) - 1):
            current_level = tree_levels[level_idx]
            next_level = tree_levels[level_idx + 1]

            for parent in current_level:
                for child in next_level:
                    parent_start = parent['col']
                    parent_end = parent['col'] + parent['colspan']
                    child_start = child['col']
                    child_end = child['col'] + child['colspan']

                    if (child_start >= parent_start and child_end <= parent_end):
                        parent['children'].append(child)
                        child['parent'] = parent

        max_depth = len(tree_levels)
        confidence = self._calculate_tree_confidence(tree_levels, header_row_end - header_start_row)

        return {
            'tree_levels': tree_levels,
            'max_depth': max_depth,
            'header_row_end': header_row_end,
            'header_start_row': header_start_row,
            'confidence': confidence,
            'approach': approach
        }
        
    def _find_first_non_title_row(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> int:
        """
        Adaptively find the first row with actual headers, filtering out table titles.
        Enhanced to detect full-width spanning title rows more reliably.
        """
        for row_idx in range(min(3, num_rows)):
            row = grid[row_idx]
            
            wide_spanning_cells = 0
            total_original_cells = 0
            non_empty_cells = 0
            
            for col_idx in range(num_cols):
                cell = row[col_idx]
                if cell.get('original_cell', False):
                    total_original_cells += 1
                    original_colspan = cell.get('original_colspan', 1)
                    
                    if cell.get('text', '').strip():
                        non_empty_cells += 1
                        
                        # Enhanced title detection: check for full or near-full width spanning
                        if original_colspan >= num_cols * 0.8:  # 80% or more of table width
                            text = cell.get('text', '').strip()
                            # Additional check: does this look like a title?
                            is_title_like = (
                                len(text.split()) >= 3 or  # Multi-word titles
                                '—' in text or '-' in text or  # Title separators
                                any(word in text.lower() for word in ['schedule', 'report', 'summary', 'overview'])
                            )
                            if is_title_like:
                                wide_spanning_cells += 1
            
            # Skip if this is an empty row
            if non_empty_cells == 0:
                continue
            
            # Skip if this row has only wide-spanning title-like cells
            if total_original_cells > 0 and wide_spanning_cells == total_original_cells:
                print(f"DEBUG: Skipping title row {row_idx}: wide spanning title detected")
                continue
            else:
                print(f"DEBUG: Found first header row: {row_idx}")
                return row_idx
        
        return 0

    def _find_column_header_boundary(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> int:
        """Find where column headers end using HTML structure and content analysis."""
    
        # Start looking after any title/empty rows that were skipped
        start_search_row = self._find_first_non_title_row(grid, num_rows, num_cols)
    
        logger.debug(f" Header boundary search starting from row {start_search_row}")
    
        # Look for the first row that looks like actual data (not headers)
        for row_idx in range(start_search_row + 1, min(num_rows, start_search_row + 6)):
            row = grid[row_idx]
        
            # Analyze the content of this row
            numeric_cells = 0
            text_cells = 0
            empty_cells = 0
        
            for col_idx in range(num_cols):
                cell_text = row[col_idx].get('text', '').strip()
                if not cell_text:
                    empty_cells += 1
                elif any(char.isdigit() for char in cell_text) or '$' in cell_text:
                    numeric_cells += 1  # Contains numbers or currency
                else:
                    text_cells += 1
        
            filled_cells = numeric_cells + text_cells
        
            logger.debug(f" Row {row_idx}: {numeric_cells} numeric, {text_cells} text, {empty_cells} empty")
        
            # If this row has significant numeric/currency content, it's likely data
            if numeric_cells >= filled_cells * 0.5 and filled_cells >= num_cols * 0.5:
                logger.debug(f" Found header boundary at row {row_idx} (data row detected)")
                return row_idx
        
            # If this row looks like header labels (short text, no numbers), continue
            if text_cells > 0 and numeric_cells == 0:
                logger.debug(f" Row {row_idx} looks like headers (text only), continuing")
                continue

        # Fallback: headers end a few rows after the start
        fallback_boundary = min(start_search_row + 3, num_rows)
        logger.debug(f" Using fallback boundary: {fallback_boundary}")
        return fallback_boundary
    
    
    def _build_row_header_tree(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> Dict[str, Any]:
        """
        Build hierarchical tree structure for row headers by analyzing rowspan/colspan patterns.
        FIXED: Includes row headers from data region (like section identifiers A, B, C).
        """
        # Find where row headers likely end by looking for transition to data-heavy columns
        header_col_end = self._find_row_header_boundary(grid, num_rows, num_cols)
        
        # Simple header row detection for column headers
        header_row_end = num_rows  # Default to all rows if no clear boundary
        for row_idx in range(min(4, num_rows)):
            th_count = sum(1 for c in range(num_cols) if grid[row_idx][c].get('type') == 'th')
            td_count = sum(1 for c in range(num_cols) if grid[row_idx][c].get('type') == 'td')
            
            if td_count > th_count and td_count >= num_cols * 0.6:
                header_row_end = row_idx
                break

        # Build tree structure from left to right, level by level
        tree_levels = []

        for col_idx in range(header_col_end):
            level_nodes = []
            row_position = 0
        
            for row_idx in range(num_rows):
                cell = grid[row_idx][col_idx]
            
                if not cell.get('original_cell', False):
                    continue
                
                text = cell.get('text', '').strip()
                if not text:
                    row_position += 1
                    continue
                
                # NEW: Include row headers from data region if they're in header columns
                # Skip only if in column header region AND the cell looks like data
                skip_cell = False
                if row_idx < header_row_end:
                    # In column header region - use existing logic
                    skip_cell = False
                else:
                    # In data region - only include if this looks like a row header
                    is_row_header = (
                        col_idx == 0 or  # First column is typically row headers
                        len(text) <= 3 or  # Short identifiers like "A", "B", "C"
                        not any(char in text for char in ['$', '%', ',']) or  # Not monetary/percentage
                        cell.get('original_rowspan', 1) > 1  # Spanning cells are often headers
                    )
                    skip_cell = not is_row_header
                
                if skip_cell:
                    row_position += 1
                    continue
                
                # Create node for this header cell
                node = {
                    'text': text,
                    'row': row_idx,
                    'col': col_idx,
                    'rowspan': cell.get('original_rowspan', 1),
                    'colspan': cell.get('colspan', 1),
                    'start_row': row_position,
                    'end_row': row_position + cell.get('rowspan', 1),
                    'children': [],
                    'parent': None
                }
            
                level_nodes.append(node)
                row_position += cell.get('rowspan', 1)
        
            tree_levels.append(level_nodes)

        # Connect parent-child relationships based on row coverage
        for level_idx in range(len(tree_levels) - 1):
            current_level = tree_levels[level_idx]
            next_level = tree_levels[level_idx + 1]
        
            for parent in current_level:
                for child in next_level:
                    if (child['start_row'] >= parent['start_row'] and 
                        child['end_row'] <= parent['end_row']):
                        parent['children'].append(child)
                        child['parent'] = parent

        max_depth = len(tree_levels)
        confidence = self._calculate_tree_confidence(tree_levels, header_col_end)

        return {
            'tree_levels': tree_levels,
            'max_depth': max_depth,
            'header_col_end': header_col_end,
            'confidence': confidence
        }

    def _is_footer_content(self, cell: Dict, row_idx: int, num_rows: int, num_cols: int) -> bool:
        """
        Detect if a cell contains footer content that should be excluded from rule generation.
        Uses structural analysis: wide-spanning cells in bottom region with metadata-like content.
        """
        # Check if cell is marked as footer from HTML structure
        if cell.get('is_footer', False):
            return True
        
        # Check if this is in the bottom region of the table
        bottom_region_threshold = max(1, num_rows - 2)  # Last 2 rows
        if row_idx < bottom_region_threshold:
            return False
        
        # Check if cell spans wide (typically footer behavior)
        original_colspan = cell.get('original_colspan', 1)
        if original_colspan >= num_cols * 0.6:  # Spans 60% or more of columns
            text = cell.get('text', '').strip().lower()
            
            # Footer-like content patterns (structural, not domain-specific)
            footer_indicators = [
                'reference' in text and 'only' in text,
                'total' in text and len(text.split()) <= 3,
                'note' in text or 'notes' in text,
                text.startswith('*') or text.startswith('('),
                len(text.split()) >= 3 and any(word in text for word in ['see', 'refer', 'contact', 'more'])
            ]
            
            if any(footer_indicators):
                return True
        
        return False
    
    def _is_title_content(self, text: str, row_idx: int, colspan: int, num_cols: int) -> bool:
        """
        Detect if content is a table title that should be excluded from context.
        Uses structural analysis: wide spanning + title-like content patterns.
        """
        if not text or row_idx > 2:  # Titles are typically in first few rows
            return False
        
        # Check for wide spanning (80%+ of table width)
        if colspan < num_cols * 0.8:
            return False
        
        text_lower = text.lower().strip()
        
        # Title content patterns (structural, not domain-specific)
        title_indicators = [
            len(text.split()) >= 3,  # Multi-word titles
            '—' in text or '-' in text or '–' in text,  # Title separators  
            any(word in text_lower for word in ['schedule', 'report', 'summary', 'overview', 'table', 'data']),
            text.isupper() and len(text.split()) >= 2,  # ALL CAPS titles
            any(char.isdigit() for char in text) and len(text.split()) >= 2,  # Titles with years/numbers
        ]
        
        return any(title_indicators)

    def _find_row_header_boundary(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> int:
        """
        Find where row headers end using structural analysis of content types and HTML semantics.
        UNIVERSAL FIX: Adapts to different table patterns without hardcoded assumptions.
        """
        
        print(f"DEBUG: _find_row_header_boundary called with {num_rows}x{num_cols} grid")
        
        # Enhanced HTML semantic analysis - require BOTH td dominance AND quantitative content
        for col_idx in range(1, min(num_cols, 5)):
            th_count = sum(1 for r in range(num_rows) if grid[r][col_idx].get('type') == 'th')
            td_count = sum(1 for r in range(num_rows) if grid[r][col_idx].get('type') == 'td')
            
            print(f"DEBUG: Col {col_idx} - th_count: {th_count}, td_count: {td_count}")
            
            # First check: HTML structure suggests data column
            if td_count > th_count and td_count >= num_rows * 0.6:
                
                # Second check: Verify the td content is actually quantitative, not categorical
                quantitative_td_count = 0
                categorical_td_count = 0
                total_td_checked = 0
                
                for row_idx in range(num_rows):
                    cell = grid[row_idx][col_idx]
                    if cell.get('type') == 'td' and cell.get('original_cell', False):
                        text = cell.get('text', '').strip()
                        if text:  # Only check non-empty cells
                            total_td_checked += 1
                            if self._is_quantitative_content(text):
                                quantitative_td_count += 1
                                print(f"DEBUG: Found quantitative td content: '{text}'")
                            else:
                                categorical_td_count += 1
                                print(f"DEBUG: Found categorical td content: '{text}'")
                
                if total_td_checked > 0:
                    quantitative_ratio = quantitative_td_count / total_td_checked
                    categorical_ratio = categorical_td_count / total_td_checked
                    print(f"DEBUG: Col {col_idx} - {quantitative_ratio:.2f} quantitative, {categorical_ratio:.2f} categorical")
                    
                    # UNIVERSAL LOGIC: Consider both content type AND minimum threshold
                    # Only exclude column if it's BOTH heavily categorical AND has meaningful categorical data
                    if categorical_ratio >= 0.8 and categorical_td_count >= 3:  # Strong categorical evidence
                        print(f"DEBUG: Col {col_idx} appears to be categorical row headers, continuing")
                        continue
                    
                    # Accept as data column if either:
                    # 1. Strong quantitative evidence (60%+ quantitative)
                    # 2. Mixed content but not strongly categorical
                    if quantitative_ratio >= 0.6 or categorical_ratio < 0.8:
                        print(f"DEBUG: Row header boundary at col {col_idx} (quantitative or mixed content detected)")
                        return col_idx
                    else:
                        print(f"DEBUG: Col {col_idx} has ambiguous content, continuing analysis")
        
        # Enhanced content-based analysis with flexible thresholds
        for col_idx in range(1, min(num_cols, 4)):  # Check fewer columns to be conservative
            
            # Analyze content characteristics of this column
            numeric_content = 0
            categorical_content = 0
            empty_content = 0
            total_cells = 0
            
            # Skip header rows when analyzing content
            start_analysis_row = min(3, num_rows // 3)  # Skip top portion that's likely headers
            
            print(f"DEBUG: Analyzing col {col_idx} content from row {start_analysis_row}")
            
            for row_idx in range(start_analysis_row, num_rows):
                cell = grid[row_idx][col_idx]
                if not cell.get('original_cell', False):
                    continue
                    
                total_cells += 1
                text = cell.get('text', '').strip()
                
                if not text:
                    empty_content += 1
                elif self._is_quantitative_content(text):
                    numeric_content += 1
                    print(f"DEBUG: Found quantitative content: '{text}'")
                else:
                    categorical_content += 1
                    print(f"DEBUG: Found categorical content: '{text}'")
            
            if total_cells == 0:
                print(f"DEBUG: Col {col_idx} has no cells to analyze")
                continue
                
            # Calculate ratios for decision making
            quantitative_ratio = numeric_content / total_cells
            categorical_ratio = categorical_content / total_cells
            
            print(f"DEBUG: Col {col_idx}: {quantitative_ratio:.2f} quantitative, {categorical_ratio:.2f} categorical")
            
            # FLEXIBLE LOGIC: Lower threshold for quantitative, but require some evidence
            if quantitative_ratio >= 0.4 and numeric_content >= 2:  # Reduced from 0.7 to 0.4
                print(f"DEBUG: Row header boundary at col {col_idx} (sufficient quantitative evidence)")
                return col_idx
            
            # If this column is heavily categorical with enough samples, it's likely headers
            if categorical_ratio >= 0.8 and categorical_content >= 3:
                print(f"DEBUG: Col {col_idx} appears to be categorical headers, continuing")
                continue
        
        # Conservative fallback: assume first column is header for simple tables
        fallback_boundary = min(1, num_cols - 1)
        print(f"DEBUG: Using conservative fallback boundary: {fallback_boundary}")
        return fallback_boundary

    def _is_quantitative_content(self, text: str) -> bool:
        """
        Determine if text content represents quantitative data using structural analysis.
        Returns True for numeric values, currency, percentages, measurements.
        """
        if not text:
            return False
        
        # Remove common formatting characters
        cleaned = re.sub(r'[$,\s%()-]', '', text)
        
        # Check if remaining content is primarily numeric
        if cleaned.replace('.', '', 1).isdigit():
            return True
        
        # Check for decimal numbers
        if re.match(r'^\d+\.\d+$', cleaned):
            return True
        
        # Check for currency patterns (even without $ symbol)
        if re.match(r'^\d{1,3}(,\d{3})*(\.\d{2})?$', text.replace('$', '')):
            return True
        
        return False
    
    def _is_meaningful_categorical_content(self, text: str) -> bool:
        """
        Determine if text represents meaningful categorical data (like session names, products, etc.)
        rather than structural labels (like 'Track', 'Day', 'Time').
        """
        if not text or len(text.strip()) < 2:
            return False
        
        text = text.strip()
        
        # Skip obvious placeholders
        if text.lower() in ['—', 'tbd', 'n/a', 'na', 'null', 'none']:
            return False
        
        # Skip obvious structural labels (typically short, single words)
        if len(text.split()) == 1 and len(text) <= 8 and text.lower() in [
            'track', 'day', 'time', 'date', 'type', 'category', 'group', 'section'
        ]:
            return False
        
        # Skip time patterns (09:00, 14:00, etc.)
        if re.match(r'^\d{1,2}:\d{2}$', text):
            return False
        
        # If it's descriptive content (multiple words), it's likely meaningful data
        if len(text.split()) >= 2:
            return True
        
        # Single meaningful words that aren't structural
        if len(text) > 8 or any(char.islower() for char in text):
            return True
        
        return False
    
    def _is_row_identifier_column(self, grid: List[List[Dict]], col_idx: int, num_rows: int) -> bool:
        """
        Determine if a column contains row identifiers rather than data content.
        More conservative approach: only flag columns with very obvious identifier patterns.
        """
        texts = []
        for row_idx in range(num_rows):
            cell = grid[row_idx][col_idx]
            if cell.get('original_cell', False) and cell.get('type') == 'td':
                text = cell.get('text', '').strip()
                if text:
                    texts.append(text)
        
        if len(texts) < 2:
            return False
        
        # Very conservative check: only flag obvious identifier patterns
        # 1. Very short labels (1-2 words max)
        # 2. All unique AND very similar length/structure
        # 3. Look like codes, categories, or simple labels
        
        avg_word_count = sum(len(text.split()) for text in texts) / len(texts)
        unique_ratio = len(set(texts)) / len(texts)
        
        # Only flag as identifiers if ALL conditions met:
        # - Very short (avg 1-2 words)
        # - All unique 
        # - Look like simple category labels
        if avg_word_count <= 2.0 and unique_ratio == 1.0:
            # Additional check: do they look like simple category labels?
            simple_labels = all(
                len(text.split()) <= 2 and 
                not any(word in text.lower() for word in ['at', 'for', 'with', 'and', 'or']) 
                for text in texts
            )
            return simple_labels
        
        return False
    
    def _calculate_tree_confidence(self, tree_levels: List[List[Dict]], boundary: int) -> float:
        """Calculate confidence score based on tree structure quality."""
        if not tree_levels:
            return 0.1
    
        confidence = 0.5  # Base confidence
    
        # Boost confidence for clear hierarchical structure
        if len(tree_levels) > 1:
            confidence += 0.2
    
        # Boost confidence for parent-child relationships
        total_nodes = sum(len(level) for level in tree_levels)
        nodes_with_children = 0
    
        for level in tree_levels:
            for node in level:
                if node['children']:
                    nodes_with_children += 1
    
        if total_nodes > 0:
            hierarchy_ratio = nodes_with_children / total_nodes
            confidence += hierarchy_ratio * 0.3
    
        return min(1.0, confidence)

    def _find_data_boundaries_from_trees(self, col_tree: Dict, row_tree: Dict, num_rows: int, num_cols: int) -> Dict[str, int]:
        """Determine data region boundaries based on header tree analysis."""
    
        # Data starts where headers end
        row_start = col_tree['header_row_end']
        col_start = row_tree['header_col_end']
    
        # Ensure boundaries are within table bounds
        row_start = min(row_start, num_rows - 1)
        col_start = min(col_start, num_cols - 1)
    
        return {
            'row_start': max(1, row_start),  # At least 1 to ensure some header space
            'col_start': max(1, col_start)   # At least 1 to ensure some header space
        }

    def _determine_orientation(self, data_start_row: int, data_start_col: int) -> TableOrientation:
        """Determine table orientation based on header presence."""
        has_col_headers = data_start_row > 0
        has_row_headers = data_start_col > 0

        if has_col_headers and has_row_headers:
            return TableOrientation.MIXED
        elif has_col_headers:
            return TableOrientation.COLUMN_BASED
        elif has_row_headers:
            return TableOrientation.ROW_BASED
        else:
            return TableOrientation.UNKNOWN

def extract_rules(grid: List[List[Dict]], structure: TableStructure) -> List[LogicRule]:
    if not grid or not grid[0]:
        return []
    
    num_rows = len(grid)
    num_cols = len(grid[0])
    
    # Re-build the context maps which are essential for getting header info
    analyzer = HierarchicalTableAnalyzer()
    col_tree = analyzer._build_column_header_tree(grid, num_rows, num_cols)
    row_tree = analyzer._build_row_header_tree(grid, num_rows, num_cols)
    row_context_map = build_tree_based_row_context_map(grid, row_tree, num_rows, num_cols)
    col_context_map = build_tree_based_col_context_map(grid, col_tree, num_rows, num_cols, analyzer)
    # Enable debugging for the insurance table
    debug_context_maps(grid, row_context_map, col_context_map, structure)

    rules = []
    
    # Determine the depth of the row headers to know where data columns begin
    row_header_depth = structure.analysis.get("row_header_depth", 1)

    for r in range(num_rows):
        for c in range(num_cols):
            cell = grid[r][c]

            # Only process a cell if it's the ORIGINAL source cell from the HTML
            if cell.get('original_cell', False):
                
                # Skip cells that are clearly headers and not data
                if c < structure.data_start_col or r < structure.data_start_row:
                    continue

                outcome_text = cell.get('text', '').strip()
                if not outcome_text:
                    continue

                # Skip footer content before processing
                if analyzer._is_footer_content(cell, r, num_rows, num_cols):
                    print(f"DEBUG: Skipping footer content at ({r},{c}): '{outcome_text}'")
                    continue

                # Skip placeholder content using our new detection function
                original_colspan = cell.get('original_colspan', 1)
                original_rowspan = cell.get('original_rowspan', 1)
                is_spanning = original_colspan > 1 or original_rowspan > 1

                if is_placeholder_content(outcome_text, is_spanning):
                    continue

                # Handle spanning based on detected table structure pattern
                approach = col_tree['approach']  # Get structural classification

                if approach == 'skip_titles':
                    # Contextual spanning: shared context across data groups
                    # Use original single-loop logic for colspan only
                    for col_offset in range(original_colspan):
                        current_col_idx = c + col_offset
                        if current_col_idx >= num_cols:
                            continue
                        
                        # Get hierarchical context for the ORIGINAL row and CURRENT column
                        row_conditions = row_context_map.get(r, [])
                        col_conditions = col_context_map.get(current_col_idx, [])
                        
                        all_conditions = []
                        for cond in (row_conditions + col_conditions):
                            if cond != outcome_text and cond.strip():
                                all_conditions.append(cond)
                        
                        unique_conditions = list(dict.fromkeys(all_conditions))
                        
                        if unique_conditions and not _should_skip_as_likely_header(outcome_text, unique_conditions):
                            rule = LogicRule(
                                conditions=unique_conditions,
                                outcome=outcome_text,
                                position=(r, current_col_idx),
                                is_summary=cell.get('is_footer', False)
                            )
                            rules.append(rule)
                else:
                    # Multiplicative spanning: independent data relationships
                    # Use nested-loop logic for both rowspan and colspan
                    for row_offset in range(original_rowspan):
                        current_row_idx = r + row_offset
                        if current_row_idx >= num_rows:
                            continue
                            
                        for col_offset in range(original_colspan):
                            current_col_idx = c + col_offset
                            if current_col_idx >= num_cols:
                                continue
                            
                            # Get hierarchical context for the CURRENT row and column position
                            row_conditions = row_context_map.get(current_row_idx, [])
                            col_conditions = col_context_map.get(current_col_idx, [])
                            
                            all_conditions = []
                            for cond in (row_conditions + col_conditions):
                                if cond != outcome_text and cond.strip():
                                    all_conditions.append(cond)
                            
                            unique_conditions = list(dict.fromkeys(all_conditions))
                            
                            if unique_conditions and not _should_skip_as_likely_header(outcome_text, unique_conditions):
                                rule = LogicRule(
                                    conditions=unique_conditions,
                                    outcome=outcome_text,
                                    position=(r, current_col_idx),
                                    is_summary=cell.get('is_footer', False)
                                )
                                rules.append(rule)
                        
    return rules


def format_form_fact(label: str, value: str, section: str | None = None, entity: str | None = None) -> str:
    """
    Universal formatter for form facts using structural disambiguation principles.
    """
    label = (label or "").strip()
    value = (value or "").strip()
    section = (section or "").strip() or None
    entity = (entity or "").strip() or None
    
    # Universal heuristic: Very short, generic words are ambiguous
    label_lower = label.lower()
    
    # Only the most generic single words need disambiguation
    truly_generic_labels = {'name', 'id', 'date', 'number', 'contact', 'type', 'code'}
    
    needs_section = section and label_lower in truly_generic_labels
    
    parts = []
    if needs_section:
        parts.append(section)
    if entity and not needs_section:
        parts.append(entity)
    
    if parts:
        ctx = " | ".join(parts)
        return f"{ctx} | {label}: {value}"
    else:
        return f"{label}: {value}"


def extract_form_table_content(grid: List[List[Dict]], table_element) -> List[LogicRule]:
    """
    Extract form field information from form tables.
    Creates rules that describe form structure and field relationships.
    """
    
    rules = []
    current_section = None
    
    num_rows = len(grid)
    num_cols = len(grid[0]) if grid else 0
    
    for r in range(num_rows):
        # Get all original cells in this row
        original_cells = []
        for c in range(num_cols):
            cell = grid[r][c]
            if cell.get('original_cell', False):
                text = cell.get('text', '').strip()
                colspan = cell.get('original_colspan', 1)
                if text:
                    original_cells.append((text, c, colspan))
        
        if not original_cells:
            continue
        
        # Check for section headers (full-width spanning)
        if len(original_cells) == 1 and original_cells[0][2] >= num_cols:
            current_section = original_cells[0][0]
            rule = LogicRule(
                conditions=['form_section'],
                outcome=original_cells[0][0],
                position=(r, original_cells[0][1])
            )
            rules.append(rule)
            continue
        
        # Process label-value pairs in this row
        i = 0
        while i + 1 < len(original_cells):
            label_text, label_col, _ = original_cells[i]
            value_text, value_col, _ = original_cells[i + 1]
            
            if not is_placeholder_value(value_text):
                clean_label = label_text.rstrip(':').strip()
                field_output = format_form_fact(clean_label, value_text, current_section)
                rule = LogicRule(
                    conditions=['form_field'],
                    outcome=field_output,
                    position=(r, label_col)
                )
                rules.append(rule)
            
            i += 2  # Skip to next pair
    
    return rules



def is_placeholder_value(value: str) -> bool:
    """
    Universal detection for placeholder values that don't add meaningful information.
    """
    if not value or not value.strip():
        return True
    
    value_clean = value.strip().lower()
    
    # Common placeholder patterns across all domains
    placeholders = {
        'n/a', 'na', 'none', 'null', 'nil', 'empty', 
        'tbd', 'tba', 'pending', 'unknown', 'not applicable',
        '...', '—', '-', 'xxx', 'n.a.', 'not available'
    }
    
    return value_clean in placeholders


def extract_layout_table_content(grid: List[List[Dict]]) -> List[LogicRule]:
    """
    Extract linearized content from layout tables.
    Creates rules that preserve content without imposing false logical structure.
    """
    rules = []
    
    # Collect all non-empty content in reading order
    content_items = []
    for r in range(len(grid)):
        for c in range(len(grid[0])):
            cell = grid[r][c]
            if cell.get('original_cell', False):
                text = cell.get('text', '').strip()
                if text and len(text) > 1:  # Skip single characters that are likely spacers
                    content_items.append({
                        'text': text,
                        'position': (r, c),
                        'is_navigation': any(nav_word in text.lower() 
                                           for nav_word in ['home', 'about', 'contact', 'menu', 'nav'])
                    })
    
    # Group content logically
    navigation_items = [item for item in content_items if item['is_navigation']]
    content_items = [item for item in content_items if not item['is_navigation']]
    
    # Create rules for navigation items
    for item in navigation_items:
        rule = LogicRule(
            conditions=['layout_navigation'],
            outcome=item['text'],
            position=item['position']
        )
        rules.append(rule)
    
    # Create rules for content items
    for item in content_items:
        # Determine content type based on characteristics
        text = item['text']
        if len(text) > 100:
            content_type = 'layout_main_content'
        elif len(text.split()) <= 3:
            content_type = 'layout_label'
        else:
            content_type = 'layout_content'
        
        rule = LogicRule(
            conditions=[content_type],
            outcome=text,
            position=item['position']
        )
        rules.append(rule)
    
    return rules


def build_tree_based_row_context_map(grid: List[List[Dict]], row_tree: Dict, num_rows: int, num_cols: int) -> Dict[int, List[str]]:
    """
    Build row context using hierarchical tree traversal to capture full header paths.
    UNIVERSAL FIX: Handles both standard rowspan sections AND rowspan with multiple logical data rows.
    """
    context_map = {}
    
    if not row_tree['tree_levels']:
        return context_map
    
    # Get the boundary where headers end and data begins
    header_col_end = row_tree.get('header_col_end', 1)
    
    # Process EVERY row in the grid
    for row_idx in range(num_rows):
        hierarchical_path = []
        
        # For each header column (left to right), find the header that covers this row
        for col_idx in range(header_col_end):
            # Look through all tree levels to find nodes in this column
            for level_nodes in row_tree['tree_levels']:
                for node in level_nodes:
                    # Check if this node is in the current column
                    if node['col'] != col_idx:
                        continue
                    
                    # Check if this header node covers the current row via rowspan
                    node_start_row = node['row']
                    node_end_row = node['row'] + node['rowspan']
                    
                    # Include this node if it spans to cover the current row
                    if node_start_row <= row_idx < node_end_row:
                        node_text = node['text']
                        
                        # Filter out obvious data values but keep legitimate headers
                        is_data_value = (
                            # Currency values with $ symbols
                            '$' in node_text or
                            # Pure numeric values (but not single letters/short codes)
                            (node_text.replace(',', '').replace('.', '').isdigit() and len(node_text) > 2) or
                            # Percentage values
                            '%' in node_text or
                            # Very long descriptive text that's clearly content, not headers
                            (len(node_text.split()) > 10)
                        )
                        
                        # Special case: preserve single character section identifiers (A, B, C, D, E)
                        is_section_identifier = (
                            len(node_text.strip()) <= 3 and 
                            node_text.strip().replace(' ', '').isalnum()
                        )
                        
                        # Include if it's a section identifier OR not a data value
                        if is_section_identifier or not is_data_value:
                            hierarchical_path.append(node_text)
                        break  # Found the covering node for this column
        
        # UNIVERSAL ENHANCEMENT: Detect if this row needs logical sub-row differentiation
        # This handles cases where rowspan creates multiple logical data rows
        if hierarchical_path:
            # Check if this row has multiple data cells that suggest it's a sub-row
            data_cell_count = 0
            for c in range(header_col_end, num_cols):
                if row_idx < len(grid) and c < len(grid[row_idx]):
                    cell = grid[row_idx][c]
                    if cell.get('original_cell') and cell.get('text', '').strip():
                        data_cell_count += 1
            
            # If this row has significant data AND we already have context for a previous row
            # with the same hierarchical path, this might be a logical sub-row
            if data_cell_count >= 2:  # Has meaningful data content
                # Check if there's already a row with identical context
                duplicate_context_rows = [r for r, ctx in context_map.items() if ctx == hierarchical_path]
                
                if duplicate_context_rows:
                    # This is likely a logical sub-row within a rowspan
                    # Add a sub-row indicator to distinguish it
                    sub_row_number = len(duplicate_context_rows) + 1
                    hierarchical_path_with_subrow = hierarchical_path + [f"row_{sub_row_number}"]
                    context_map[row_idx] = hierarchical_path_with_subrow
                else:
                    # First occurrence of this context
                    context_map[row_idx] = hierarchical_path
            else:
                # Low data content - likely a header or continuation row
                context_map[row_idx] = hierarchical_path
    
    return context_map

def build_tree_based_col_context_map(grid: List[List[Dict]], col_tree: Dict, num_rows: int, num_cols: int, analyzer) -> Dict[int, List[str]]:
    """
    Build column context using hierarchical tree traversal to capture full header paths.
    FIXED: Properly builds hierarchical paths like "2025 > Q1 > Jan" for complex headers.
    """
    context_map = {}
    
    if not col_tree['tree_levels']:
        return context_map
    
    # For each column in the entire grid, build the hierarchical path
    for col_idx in range(num_cols):
        hierarchical_path = []
        
        # Traverse each level of the column header tree from top to bottom
        for level_idx, level_nodes in enumerate(col_tree['tree_levels']):
            found_covering_node = False
            
            for node in level_nodes:
                # Check if this node covers the current column
                node_start_col = node['col']
                node_end_col = node['col'] + node['colspan']
                
                if node_start_col <= col_idx < node_end_col:
                    # Filter out title content from context
                    if not analyzer._is_title_content(node['text'], node['row'], node['colspan'], num_cols):
                        # Also filter out empty cells and meaningless text
                        node_text = node['text'].strip()
                        if node_text and len(node_text) > 0:
                            hierarchical_path.append(node_text)
                    
                    found_covering_node = True
                    break  # Found the covering node for this level
            
            # If no node covers this column at this level, we can't build a complete path
            if not found_covering_node:
                break
        
        # Only add to context map if we found a meaningful hierarchical path
        if hierarchical_path:
            context_map[col_idx] = hierarchical_path
    
    return context_map


def clean_text(text: str) -> str:
    """
    Universal text cleaning that preserves compound terms and technical language.
    Handles HTML entities and normalizes spacing without breaking meaningful word boundaries.
    """
    if not text:
        return ""
    
    # Handle HTML entities first  
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # Handle the specific pattern: Day 1<br><small>Mon, 12 May</small>
    # This ensures proper spacing between "Day 1" and "Mon, 12 May"
    text = re.sub(r'(\w+\s+\d+)<br\s*/?><small>([^<]+)</small>', r'\1 \2', text, flags=re.IGNORECASE)
    
    # Remove all remaining HTML tags and replace with space
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Fix spacing around common separators (but preserve compound terms)
    text = re.sub(r'\s*&\s*', ' & ', text)
    
    # Fix spacing around em dashes and hyphens (preserve meaning)
    text = re.sub(r'\s*—\s*', ' — ', text)  # Em dash
    text = re.sub(r'(?<=\w)\s*-\s*(?=\w)', '-', text)  # Hyphen in compound words (no spaces)
    
    # Final whitespace cleanup
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def parse_and_unmerge_table_bulletproof(table) -> List[List[Dict]]:
    """
    Step 1: Bulletproof unmerging - create perfect 2D grid.
    This corrected version robustly finds <tr> elements in any table structure
    and preserves semantic context from HTML structure.
    """
    # STEP 1: Map footer rows before processing
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
    
    # This is the simplified and corrected row-finding logic
    actual_rows = table.find_all('tr')
    if not actual_rows:
        return []

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
                'is_footer': row_idx in footer_row_indices  # STEP 2: Tag cells with footer context
            }
            row_cells.append(cell_data)
        parsed_cells.append(row_cells)
    
    occupied_positions = set()
    max_cols = 0
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
    grid = [[{'text': '', 'type': 'td', 'original_cell': False, 'is_footer': False} for _ in range(max_cols)] for _ in range(max_rows)]
    occupied_positions.clear()

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
                            'rowspan': 1,  # For compatibility
                            'colspan': 1,  # For compatibility
                            'is_footer': cell['is_footer']  # STEP 3: Preserve footer context in grid
                        }
                        occupied_positions.add((target_row, target_col))
            col_idx += cell['colspan']
    return grid


def process_table(table_html: str) -> List[LogicRule]:
    # Validate HTML table structure before processing
    validation_result = validate_html_table_structure(table_html)
    
    if not validation_result['is_valid']:
        error_msg = "HTML table validation failed:\n"
        for error in validation_result['errors']:
            error_msg += f"  - {error}\n"
        logger.error(error_msg)
        raise ValueError(f"Invalid HTML table structure. Errors found:\n{error_msg}")
    
    if validation_result['warnings']:
        for warning in validation_result['warnings']:
            logger.warning(f"Table validation warning: {warning}")
    
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')

    grid = parse_and_unmerge_table_bulletproof(table)
    logger.info(f"Step 1 - Unmerged grid: {len(grid)} rows x {len(grid[0]) if grid else 0} columns")

    # Classify table type before processing
    classifier = TableClassifier()
    classification = classifier.classify_table(table, grid)
    
    logger.info(f"Table classified as: {classification['type'].value} (confidence: {classification['confidence']:.2f})")
    
    # Route to appropriate extraction strategy based on classification
    if classification['type'] == TableType.DATA_TABLE:
        # Use existing logic rule extraction for data tables
        analyzer = HierarchicalTableAnalyzer()
        structure = analyzer.analyze_table_structure({"grid": grid})
        rules = extract_rules(grid, structure)
        logger.info(f"Step 2 - Generated {len(rules)} logic rules from data table")
        return rules
        
    elif classification['type'] == TableType.FORM_TABLE:
        # Extract form content (different approach)
        form_content = extract_form_table_content(grid, table)
        logger.info(f"Step 2 - Extracted form content with {len(form_content)} fields")
        return form_content
        
    elif classification['type'] == TableType.LAYOUT_TABLE:
        # Extract linearized layout content
        layout_content = extract_layout_table_content(grid)
        logger.info(f"Step 2 - Extracted layout content with {len(layout_content)} items")
        return layout_content
        
    else:
        # Unknown type - use conservative data table approach with warning
        logger.warning(f"Unknown table type, applying data table extraction conservatively")
        analyzer = HierarchicalTableAnalyzer()
        structure = analyzer.analyze_table_structure({"grid": grid})
        rules = extract_rules(grid, structure)
        logger.info(f"Step 2 - Generated {len(rules)} logic rules (unknown table type)")
        return rules


def main():
    parser = argparse.ArgumentParser(description='table2rules - Universal Table to Logic Rules')
    parser.add_argument('--format', choices=['structured', 'conversational', 'qa', 'descriptive', 'searchable', 'all'], 
                       default='structured', help='Output format (default: structured)')
    parser.add_argument('--output', choices=['markdown', 'json', 'both'], default='markdown',
                       help='Output type (default: markdown)')
    parser.add_argument('--chunking', action='store_true', help='Add chunking metadata for RAG systems')
    parser.add_argument('--input', default='input.md', help='Input file (default: input.md)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
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
            logger.info(f"Processing table {i+1} of {len(tables)}...")
            rules = process_table(table_html)
            all_rules.extend(rules)
        
        # Generate output based on selected format
        if args.output in ['markdown', 'both']:
            _write_markdown_output(all_rules, args.format, args.chunking)
        
        if args.output in ['json', 'both']:
            _write_json_output(all_rules, args.format)
        
        logger.info(f"Generated {len(all_rules)} logic rules in {args.format} format")
        
    except FileNotFoundError:
        logger.error(f"Error: {args.input} not found")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()


def _write_markdown_output(rules: List[LogicRule], format_type: str, include_chunking_metadata: bool = False):
    """Write markdown output based on selected format"""
    with open('output.md', 'w', encoding='utf-8') as f:
        # Add chunking metadata if requested
        if include_chunking_metadata:
            f.write("<!-- TABLE_CHUNK_START -->\n")
            f.write("<!-- CHUNK_TYPE: table_rules -->\n")
            f.write("<!-- SOURCE_TYPE: structured_table_data -->\n")
            f.write(f"<!-- RULE_COUNT: {len(rules)} -->\n")
            f.write("<!-- KEEP_TOGETHER: true -->\n\n")
        
        if format_type == 'all':
            format_configs = [
                ('structured', 'Structured Format'),
                ('conversational', 'Conversational Format'),
                ('qa', 'Question-Answer Format'),
                ('descriptive', 'Descriptive Format'),
                ('searchable', 'Searchable Format')
            ]
            
            for fmt_key, fmt_title in format_configs:
                f.write(f"## {fmt_title}\n\n")
                
                for rule in rules:
                    if fmt_key == 'structured':
                        f.write(f"- {rule.to_rule_string()}\n")
                    else:
                        formats = rule.to_natural_formats()
                        f.write(f"- {formats[fmt_key]}\n")
                f.write("\n")
        else:
            # Single format output - no header
            for i, rule in enumerate(rules):
                if format_type == 'structured':
                    content = rule.to_rule_string()
                else:
                    formats = rule.to_natural_formats()
                    content = formats[format_type]
                
                f.write(f"{content}\n")
                
                # Add soft boundary markers for chunking guidance
                if include_chunking_metadata and (i + 1) % 5 == 0 and i < len(rules) - 1:
                    f.write("<!-- CHUNK_BOUNDARY_SOFT -->\n")
        
        if include_chunking_metadata:
            f.write("\n<!-- TABLE_CHUNK_END -->\n")


def _write_json_output(rules: List[LogicRule], format_type: str):
    """Write JSON output based on selected format"""
    import json
    
    if format_type == 'all':
        # Include all formats in JSON
        json_output = []
        for rule in rules:
            formats = rule.to_natural_formats()
            json_output.append({
                'position': rule.position,
                'is_summary': rule.is_summary,
                'formats': formats,
                'conditions': rule.conditions,
                'outcome': rule.outcome
            })
    else:
        # Single format in JSON
        json_output = []
        for rule in rules:
            if format_type == 'structured':
                content = rule.to_rule_string()
            else:
                formats = rule.to_natural_formats()
                content = formats[format_type]
            
            json_output.append({
                'content': content,
                'position': rule.position,
                'is_summary': rule.is_summary,
                'conditions': rule.conditions,
                'outcome': rule.outcome
            })
    
    with open('output.json', 'w', encoding='utf-8') as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()