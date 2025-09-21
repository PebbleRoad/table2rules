#!/usr/bin/env python3
"""
Table Classification System for table2rules
Distinguishes between data tables, form tables, and layout tables
"""

import re
from typing import Dict, List, Any, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TableType(Enum):
    DATA_TABLE = "data_table"
    FORM_TABLE = "form_table" 
    LAYOUT_TABLE = "layout_table"
    UNKNOWN = "unknown"


class TableClassifier:
    """
    Classifies HTML tables into data, form, or layout types using scoring-based analysis.
    Prevents false logic-rule extraction from non-data tables.
    """
    
    def __init__(self):
        # Confidence thresholds for classification
        self.high_confidence_threshold = 0.7
        self.medium_confidence_threshold = 0.4
        
    def classify_table(self, table_element, grid: List[List[Dict]]) -> Dict[str, Any]:
        """
        Main classification method that scores table against all types.
        Returns classification with confidence and reasoning.
        """
        if not grid or not grid[0]:
            return {
                'type': TableType.UNKNOWN,
                'confidence': 0.0,
                'scores': {},
                'reasoning': 'Empty or invalid table structure'
            }
        
        num_rows = len(grid)
        num_cols = len(grid[0])
        
        # Calculate scores for each table type
        data_score = self._score_data_table(table_element, grid, num_rows, num_cols)
        form_score = self._score_form_table(table_element, grid, num_rows, num_cols)
        layout_score = self._score_layout_table(table_element, grid, num_rows, num_cols)
        
        scores = {
            'data_table': data_score,
            'form_table': form_score,
            'layout_table': layout_score
        }
        
        # DEBUG: Print detailed scoring breakdown
        print(f"\n=== TABLE CLASSIFICATION DEBUG ===")
        print(f"Table size: {num_rows} rows x {num_cols} cols")
        print(f"Data table score: {data_score:.3f}")
        print(f"Form table score: {form_score:.3f}")
        print(f"Layout table score: {layout_score:.3f}")
        
        # DEBUG: Show first few cells of content
        print(f"First row content:")
        for c in range(min(num_cols, 3)):
            cell = grid[0][c] if grid else {}
            print(f"  Col {c}: '{cell.get('text', '')}'")
        
        # Determine classification with tie-breaking
        max_score = max(scores.values())
        if max_score < self.medium_confidence_threshold:
            classification = TableType.UNKNOWN
            confidence = max_score
            reasoning = f"All scores below threshold (max: {max_score:.2f})"
        else:
            # Handle ties with preference order: form > data > layout
            if abs(scores['form_table'] - scores['data_table']) < 0.05:  # Close scores
                if scores['form_table'] >= scores['data_table']:
                    best_type = 'form_table'
                    reasoning = "Tie-breaker: form table preferred for close scores"
                else:
                    best_type = 'data_table'
                    reasoning = "Data table wins close decision"
            else:
                # Clear winner
                best_type = max(scores.keys(), key=lambda k: scores[k])
                reasoning = f"Clear winner: {best_type} ({scores[best_type]:.2f})"
            
            classification = TableType(best_type)
            confidence = max_score
        
        print(f"FINAL CLASSIFICATION: {classification.value} (confidence: {confidence:.2f})")
        print(f"REASONING: {reasoning}")
        print("=====================================\n")
        
        logger.info(f"Table classified as {classification.value} (confidence: {confidence:.2f})")
        logger.debug(f"Scores - Data: {data_score:.2f}, Form: {form_score:.2f}, Layout: {layout_score:.2f}")
        
        return {
            'type': classification,
            'confidence': confidence,
            'scores': scores,
            'reasoning': reasoning
        }
    
    def _score_data_table(self, table_element, grid: List[List[Dict]], num_rows: int, num_cols: int) -> float:
        """
        Score likelihood that this is a data table containing relational information.
        Data tables encode facts or semantic triples with regular structure.
        IMPROVED: More conservative when form patterns are detected.
        """
        score = 0.0
        
        # PRE-CHECK: Detect strong form indicators that should reduce data table confidence
        form_indicators = 0
        total_text_cells = 0
        
        for r in range(num_rows):
            for c in range(num_cols):
                cell = grid[r][c]
                if not cell.get('original_cell', False):
                    continue
                    
                text = cell.get('text', '').strip()
                if not text:
                    continue
                    
                total_text_cells += 1
                
                # Form-like patterns that suggest this isn't tabular data
                if (text.endswith(':') or 
                    any(form_word in text.lower() for form_word in 
                        ['name', 'address', 'phone', 'email', 'contact', 'registration', 'account', 'code']) or
                    '@' in text or  # Email addresses
                    text.startswith(('(', '+')) and ')' in text):  # Phone numbers
                    form_indicators += 1
        
        # Apply penalty if many cells look like form content
        if total_text_cells > 0:
            form_ratio = form_indicators / total_text_cells
            if form_ratio > 0.4:  # If >40% of cells look like form content
                score -= 0.3  # Significant penalty

        # CORE DATA TABLE PATTERN: Multiple rows of similar structured data
        data_rows = 0
        header_rows = 0
        
        for r in range(num_rows):
            row = grid[r]
            th_count = sum(1 for cell in row if cell.get('type') == 'th')
            td_count = sum(1 for cell in row if cell.get('type') == 'td' and cell.get('text', '').strip())
            
            if td_count >= num_cols * 0.6 and th_count <= num_cols * 0.3:
                data_rows += 1
            elif th_count >= num_cols * 0.4:
                header_rows += 1
        
        if data_rows >= 3:
            score += 0.4
        elif data_rows >= 2:
            score += 0.2
        
        if header_rows >= 1 and data_rows >= 2:
            score += 0.3
        
        # Size and structure indicators
        if num_rows >= 5 and num_cols >= 3:
            score += 0.1
        if num_rows >= 10:
            score += 0.1
        
        if table_element.find('thead') and table_element.find('tbody'):
            score += 0.2
        
        return max(0.0, min(1.0, score))
    
    def _score_form_table(self, table_element, grid: List[List[Dict]], num_rows: int, num_cols: int) -> float:
        """
        Score likelihood that this is a form table using universal structural patterns.
        No hardcoded field names - uses structural heuristics only.
        """
        score = 0.0
        
        # Core pattern: Count rows with clear label-value structure
        label_value_rows = 0
        entity_rows = 0
        
        for r in range(min(8, num_rows)):  # Scan first 8 rows
            # Get original cells in this row
            original_cells = []
            for c in range(num_cols):
                cell = grid[r][c]
                if cell.get('original_cell', False):
                    text = cell.get('text', '').strip()
                    colspan = cell.get('original_colspan', 1)
                    if text:
                        original_cells.append((text, colspan))
            
            if len(original_cells) < 2:
                continue
                
            # Entity row detection: first cell spans wide
            first_text, first_span = original_cells[0]
            if first_span >= num_cols:
                entity_rows += 1
                continue
            
            # Label-value pair detection
            pairs_found = 0
            i = 0
            while i + 1 < len(original_cells):
                label_text = original_cells[i][0]
                value_text = original_cells[i + 1][0]
                
                # Universal heuristic: reasonable label followed by different content
                is_label_value = (
                    label_text.endswith(':') or  # Explicit label marker
                    (len(label_text.split()) <= 4 and  # Reasonable label length
                    value_text and  # Has actual value
                    label_text != value_text and  # Different content
                    not value_text.endswith(':'))  # Value isn't another label
                )
                
                if is_label_value:
                    pairs_found += 1
                i += 2
            
            if pairs_found >= 1:
                label_value_rows += 1
        
        # Strong scoring for form patterns
        if label_value_rows >= 2:
            score += 0.5  # Multiple rows with label-value pairs
        if entity_rows >= 1:
            score += 0.3  # Has section headers or titles
        
        # Additional form indicators
        inputs = table_element.find_all(['input', 'select', 'textarea', 'button'])
        if inputs:
            score += min(0.2, len(inputs) / 10)
        
        return min(1.0, score)
    
    def _score_layout_table(self, table_element, grid: List[List[Dict]], num_rows: int, num_cols: int) -> float:
        """
        Score likelihood that this is a layout table used for positioning elements.
        Layout tables don't encode knowledge, just arrange content spatially.
        """
        score = 0.0
        
        # Check for role="presentation" attribute (explicit layout indicator)
        if table_element.get('role') == 'presentation':
            score += 0.4
        
        # CSS class analysis for layout patterns
        table_classes = table_element.get('class', [])
        layout_class_indicators = ['layout', 'wrapper', 'container', 'grid', 'sidebar', 'nav']
        if any(indicator in ' '.join(table_classes).lower() for indicator in layout_class_indicators):
            score += 0.2
        
        # Navigation content detection
        nav_elements = table_element.find_all(['nav', 'a'])
        if nav_elements:
            nav_density = len(nav_elements) / (num_rows * num_cols)
            score += min(0.3, nav_density * 3)
        
        # Empty cell ratio analysis (spacer detection)
        empty_cells = sum(1 for row in grid for cell in row if not cell.get('text', '').strip())
        total_cells = num_rows * num_cols
        if total_cells > 0:
            empty_ratio = empty_cells / total_cells
            if empty_ratio > 0.6:  # Lots of empty cells suggest layout usage
                score += 0.25
        
        # Single row/column pattern recognition
        if num_rows == 1 or num_cols == 1:
            score += 0.2  # Linear layouts are often for positioning
        
        # Check for minimal semantic structure
        th_count = sum(1 for row in grid for cell in row if cell.get('type') == 'th')
        if th_count == 0:  # No headers suggests layout usage
            score += 0.1
        
        # Look for layout-specific content patterns
        layout_content_indicators = 0
        for row in grid:
            for cell in row:
                text = cell.get('text', '').strip().lower()
                if any(word in text for word in ['menu', 'home', 'about', 'contact', 'footer', 'header']):
                    layout_content_indicators += 1
        
        if layout_content_indicators > 0:
            score += min(0.15, layout_content_indicators / 10)
        
        return min(1.0, score)