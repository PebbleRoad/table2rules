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
    
    def to_rule_string(self) -> str:
        if not self.conditions:
            return f"FACT: The value is '{self.outcome}'"
    
        condition_parts = [f'"{c}"' for c in self.conditions]
        conditions_str = " AND ".join(condition_parts)
        return f"IF {conditions_str} THEN the value is '{self.outcome}'"


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
        Adaptively find the first row with actual headers.
        Different logic for different table types.
        """
        # Check if this looks like a scheduling table (has th elements in multiple rows)
        th_rows = 0
        for row_idx in range(min(4, num_rows)):
            row = grid[row_idx]
            th_count = sum(1 for c in range(num_cols) if row[c].get('type') == 'th')
            if th_count > 0:
                th_rows += 1
    
        # If multiple rows have th elements, this is likely a schedule table - don't skip anything
        if th_rows >= 2:
            logger.debug(f" Detected multiplicative spanning pattern ({th_rows} header rows) - starting from row 0")
            return 0
    
        # Otherwise, use the original title detection for contextual spanning tables
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
                    
                        if original_colspan >= num_cols * 0.6:
                            wide_spanning_cells += 1
        
            # Skip if this is an empty row
            if non_empty_cells == 0:
                continue
        
            # Skip if this row has only wide-spanning cells (title row)
            if total_original_cells > 0 and wide_spanning_cells == total_original_cells:
                logger.debug(f" Skipping title row {row_idx}")
                continue
            else:
                logger.debug(f" Found first header row: {row_idx}")
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
        Each node represents a header cell with its spanning information and children.
        """
        # Find where row headers likely end by looking for transition to data-heavy columns
        header_col_end = self._find_row_header_boundary(grid, num_rows, num_cols)
    
        # Build tree structure from left to right, level by level
        tree_levels = []
    
        for col_idx in range(header_col_end):
            level_nodes = []
            row_position = 0
        
            for row_idx in range(num_rows):
                cell = grid[row_idx][col_idx]
            
                # Skip if this position is already covered by a previous spanning cell
                if not cell.get('original_cell', False):
                    continue
                
                text = cell.get('text', '').strip()
                if not text:
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
                    # Child is under parent if its row range is within parent's range
                    if (child['start_row'] >= parent['start_row'] and 
                        child['end_row'] <= parent['end_row']):
                        parent['children'].append(child)
                        child['parent'] = parent
    
        # Calculate tree metrics
        max_depth = len(tree_levels)
        confidence = self._calculate_tree_confidence(tree_levels, header_col_end)
    
        return {
            'tree_levels': tree_levels,
            'max_depth': max_depth,
            'header_col_end': header_col_end,
            'confidence': confidence
        }

    def _find_row_header_boundary(self, grid: List[List[Dict]], num_rows: int, num_cols: int) -> int:
        """Find where row headers end using HTML structure and content analysis."""
    
        # Look for transition from header-heavy to data-heavy columns
        for col_idx in range(1, min(num_cols, 5)):
            th_count = sum(1 for r in range(num_rows) if grid[r][col_idx].get('type') == 'th')
            td_count = sum(1 for r in range(num_rows) if grid[r][col_idx].get('type') == 'td')
        
            # If this column has significantly more data cells, headers likely end here
            if td_count > th_count and td_count >= num_rows * 0.6:
                return col_idx
    
        # Fallback: assume headers are in first few columns
        return min(2, num_cols)
    
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
    col_context_map = build_tree_based_col_context_map(grid, col_tree, num_rows, num_cols)
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
                if c < row_header_depth or r < structure.data_start_row:
                    continue

                outcome_text = cell.get('text', '').strip()
                if not outcome_text:
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
                                position=(r, current_col_idx)
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
                                    position=(r, current_col_idx)
                                )
                                rules.append(rule)
                        
    return rules

def build_tree_based_row_context_map(grid: List[List[Dict]], row_tree: Dict, num_rows: int, num_cols: int) -> Dict[int, List[str]]:
    """
    Build row context using hierarchical tree traversal to capture full header paths.
    For each row in the entire grid, traverse across the tree to get the complete hierarchical context.
    UNIVERSAL FIX: Process ALL rows, not just detected data region.
    """
    context_map = {}
    
    if not row_tree['tree_levels']:
        return context_map
    
    # Process EVERY row in the grid, not just a subset
    for row_idx in range(num_rows):
        hierarchical_path = []
        
        # Traverse each level of the row header tree to build complete path
        for level_idx, level_nodes in enumerate(row_tree['tree_levels']):
            for node in level_nodes:
                # Use the actual grid row position and check spanning coverage
                node_start_row = node['row']
                node_end_row = node['row'] + node['rowspan']
                
                # Check if this header node covers the current row
                if node_start_row <= row_idx < node_end_row:
                    hierarchical_path.append(node['text'])
                    break  # Found the covering node for this level
        
        # Only add to context map if we found actual context
        if hierarchical_path:
            context_map[row_idx] = hierarchical_path
    
    return context_map

def build_tree_based_col_context_map(grid: List[List[Dict]], col_tree: Dict, num_rows: int, num_cols: int) -> Dict[int, List[str]]:
    """
    Build column context using hierarchical tree traversal to capture full header paths.
    For each data column, traverse down the tree to get the complete hierarchical context.
    """
    context_map = {}
    
    if not col_tree['tree_levels']:
        return context_map
    
    # For each column in the entire grid, find which header nodes cover it
    for col_idx in range(num_cols):
        hierarchical_path = []
        
        # Traverse each level of the column header tree to build complete path
        for level_idx, level_nodes in enumerate(col_tree['tree_levels']):
            for node in level_nodes:
                # Use the actual grid column position, not the node's internal positioning
                node_start_col = node['col']
                node_end_col = node['col'] + node['colspan']
                                
                if node_start_col <= col_idx < node_end_col:
                    hierarchical_path.append(node['text'])
                    break  # Found the covering node for this level
        
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
    This corrected version robustly finds <tr> elements in any table structure.
    """
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
                'row': row_idx
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
    grid = [[{'text': '', 'type': 'td', 'original_cell': False} for _ in range(max_cols)] for _ in range(max_rows)]
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
                            'colspan': 1   # For compatibility
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

    analyzer = HierarchicalTableAnalyzer()
    structure = analyzer.analyze_table_structure({"grid": grid})

    rules = extract_rules(grid, structure)
    logger.info(f"Step 2 - Generated {len(rules)} logic rules")

    return rules


def main():
    try:
        with open('input.md', 'r', encoding='utf-8') as f:
            content = f.read()
        
        table_pattern = r'<table[^>]*>.*?</table>'
        tables = re.findall(table_pattern, content, re.DOTALL)
        
        if not tables:
            logger.warning("No tables found in input.md")
            return
        
        all_rules = []
        
        for i, table_html in enumerate(tables):
            logger.info(f"Processing table {i+1} of {len(tables)}...")
            rules = process_table(table_html)
            all_rules.extend(rules)
        
        with open('output.md', 'w', encoding='utf-8') as f:
            f.write("# table2rules Output\n\n")
            for rule in all_rules:
                rule_string = rule.to_rule_string()
                f.write(f"- {rule_string}\n")
        
        logger.info(f"Generated {len(all_rules)} logic rules in output.md")
        
    except FileNotFoundError:
        logger.error("Error: input.md not found")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()