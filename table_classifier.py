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
        
        # Determine classification based on highest score
        max_score = max(scores.values())
        if max_score < self.medium_confidence_threshold:
            classification = TableType.UNKNOWN
            confidence = max_score
            reasoning = f"All scores below threshold (max: {max_score:.2f})"
        else:
            # Find the type with highest score
            best_type = max(scores.keys(), key=lambda k: scores[k])
            classification = TableType(best_type)
            confidence = max_score
            reasoning = f"Highest score: {best_type} ({max_score:.2f})"
        
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
        """
        score = 0.0
        
        # Header structure detection (strong indicator)
        th_count = sum(1 for row in grid for cell in row if cell.get('type') == 'th')
        total_cells = num_rows * num_cols
        
        if th_count > 0:
            header_ratio = th_count / total_cells
            if header_ratio > 0.1:  # Reasonable header presence
                score += 0.3
            else:
                score += 0.15  # Some headers present
        
        # Check for thead/tbody structure
        if table_element.find('thead') or table_element.find('tbody'):
            score += 0.2
        
        # Regular structure validation - data tables tend to be rectangular
        row_lengths = [len([c for c in row if c.get('text', '').strip()]) for row in grid]
        if row_lengths:
            length_variance = max(row_lengths) - min(row_lengths)
            if length_variance <= 2:  # Consistent row lengths
                score += 0.2
        
        # Repeated data pattern recognition
        numeric_cells = 0
        text_cells = 0
        for row in grid:
            for cell in row:
                text = cell.get('text', '').strip()
                if text:
                    if re.search(r'\d', text) or '$' in text or '%' in text:
                        numeric_cells += 1
                    else:
                        text_cells += 1
        
        if numeric_cells > 0:
            data_ratio = numeric_cells / (numeric_cells + text_cells) if (numeric_cells + text_cells) > 0 else 0
            score += min(0.3, data_ratio)  # Up to 0.3 for good data content
        
        # Size-based scoring - data tables tend to be substantial
        if num_rows >= 3 and num_cols >= 3:
            score += 0.1
        if num_rows >= 5 and num_cols >= 4:
            score += 0.1
        
        return min(1.0, score)
    
    def _score_form_table(self, table_element, grid: List[List[Dict]], num_rows: int, num_cols: int) -> float:
        """
        Score likelihood that this is a form table with input fields and labels.
        Form tables are used for data entry and have irregular structure.
        """
        score = 0.0
        
        # Form input detection - strongest indicator
        inputs = table_element.find_all(['input', 'select', 'textarea', 'button'])
        if inputs:
            input_density = len(inputs) / (num_rows * num_cols)
            score += min(0.5, input_density * 2)  # Heavy weight for form elements
        
        # Label-input pair recognition
        labels = table_element.find_all('label')
        if labels:
            score += min(0.2, len(labels) / 10)
        
        # Check for form-related CSS classes
        table_classes = table_element.get('class', [])
        form_class_indicators = ['form', 'input', 'field', 'entry']
        if any(indicator in ' '.join(table_classes).lower() for indicator in form_class_indicators):
            score += 0.15
        
        # Irregular structure detection (common in forms)
        empty_cells = sum(1 for row in grid for cell in row if not cell.get('text', '').strip())
        total_cells = num_rows * num_cols
        if total_cells > 0:
            empty_ratio = empty_cells / total_cells
            if 0.2 < empty_ratio < 0.6:  # Forms often have strategic empty cells
                score += 0.15
        
        # Compact size scoring (forms tend to be smaller)
        if 2 <= num_rows <= 8 and 2 <= num_cols <= 4:
            score += 0.1
        
        # Mixed content type detection
        cell_types = set()
        for row in grid:
            for cell in row:
                text = cell.get('text', '').strip()
                if text:
                    if re.search(r'\d+', text):
                        cell_types.add('numeric')
                    elif len(text.split()) == 1:
                        cell_types.add('short_text')
                    else:
                        cell_types.add('long_text')
        
        if len(cell_types) >= 2:  # Mixed content suggests form structure
            score += 0.1
        
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