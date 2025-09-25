#!/usr/bin/env python3
"""
Table Processor System - Clean separation of table type processing
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import logging
import re
from models import LogicRule

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result from processing a table"""
    rules: List[LogicRule]  # Now we can use the proper type
    confidence: float
    metadata: Dict[str, Any]
    processor_type: str


class TableProcessor(ABC):
    """Base class for all table processors"""
    
    @abstractmethod
    def can_process(self, grid: List[List[Dict]], table_element) -> float:
        """Return confidence score 0-1 for processing this table type"""
        pass
    
    @abstractmethod  
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Process the table and return rules"""
        pass


class DataTableProcessor(TableProcessor):
    """Processes data tables with hierarchical structure"""
    
    def can_process(self, grid: List[List[Dict]], table_element) -> float:
        """Detect data tables using clean, focused logic"""
        if not grid or not grid[0]:
            return 0.0
        
        num_rows = len(grid)
        num_cols = len(grid[0])
        
        score = 0.0
        
        # Core data table pattern: Multiple rows of structured data
        data_rows = 0
        header_rows = 0
        
        for r in range(num_rows):
            row = grid[r]
            th_count = sum(1 for cell in row if cell.get('type') == 'th')
            td_count = sum(1 for cell in row if cell.get('type') == 'td' and cell.get('text', '').strip())
            
            # Data row: mostly td elements with content
            if td_count >= num_cols * 0.5 and th_count <= num_cols * 0.3:
                data_rows += 1
            # Header row: significant th elements
            elif th_count >= num_cols * 0.3:
                header_rows += 1
        
        # Strong signal: Multiple data rows
        if data_rows >= 3:
            score += 0.5
        elif data_rows >= 2:
            score += 0.3
        
        # Header structure supports data table hypothesis
        if header_rows >= 1 and data_rows >= 2:
            score += 0.3
        
        # Size indicates tabular data
        if num_rows >= 5 and num_cols >= 3:
            score += 0.2
        
        # HTML semantic structure
        if table_element.find('thead') or table_element.find('tbody'):
            score += 0.2
        
        return min(1.0, score)
    
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Process data table using hierarchical logic"""
        
        
        # Build context maps
        row_context_map = self._build_row_context_map(grid)
        col_context_map = self._build_column_context_map(grid)
        
        # Extract rules
        rules = self._extract_data_rules(grid, row_context_map, col_context_map)
        
        metadata = {
            "rules_extracted": len(rules),
            "grid_size": f"{len(grid)}x{len(grid[0]) if grid else 0}"
        }
        
        return ProcessingResult(
            rules=rules,
            confidence=0.8,
            metadata=metadata,
            processor_type="data_table"
        )
    
    def _build_row_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Simplified row context: first column contains row identifiers"""
        context_map = {}
        
        if not grid or not grid[0]:
            return context_map
        
        num_rows = len(grid)
        
        # Simple approach: scan first column for any text in original cells
        for row_idx in range(num_rows):
            # Safety check for row existence
            if row_idx >= len(grid) or not grid[row_idx]:
                continue
                
            # Safety check for first column existence
            if len(grid[row_idx]) == 0:
                continue
                
            cell = grid[row_idx][0]  # First column
            
            # Only process original cells (not span-filled cells)
            if cell.get('original_cell', False):
                text = cell.get('text', '').strip()
                if text:
                    # Apply this identifier to all rows this cell spans
                    rowspan = cell.get('original_rowspan', 1)
                    for span_row in range(row_idx, min(row_idx + rowspan, num_rows)):
                        if span_row not in context_map:
                            context_map[span_row] = []
                        context_map[span_row].append(text)
        
        return context_map
    
    def _build_column_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Simplified column context with proper spanning support"""
        context_map = {}
        
        if not grid or not grid[0]:
            return context_map
        
        num_rows = len(grid)
        num_cols = len(grid[0])
        
        # Simple approach: scan first 3 rows for th elements
        header_rows = min(3, num_rows)
        
        # Build spanning map first - track which columns are covered by spanning headers
        spanning_headers = {}  # {col_index: header_text}
        
        for row_idx in range(header_rows):
            if row_idx >= len(grid) or not grid[row_idx]:
                continue
                
            for col_idx in range(num_cols):
                if col_idx >= len(grid[row_idx]):
                    continue
                    
                cell = grid[row_idx][col_idx]
                
                if cell.get('original_cell', False) and cell.get('type') == 'th':
                    text = cell.get('text', '').strip()
                    if text:
                        colspan = cell.get('original_colspan', 1)
                        
                        # Skip title-spanning headers (span most/all columns)
                        if colspan >= num_cols * 0.8:
                            continue
                        
                        # Apply this header to all columns it spans
                        for span_col in range(col_idx, min(col_idx + colspan, num_cols)):
                            if span_col not in spanning_headers:
                                spanning_headers[span_col] = []
                            spanning_headers[span_col].append(text)
        
        # Now collect all headers for each column
        for col_idx in range(num_cols):
            col_headers = []
            
            # Add spanning headers first
            if col_idx in spanning_headers:
                col_headers.extend(spanning_headers[col_idx])
            
            # Add direct headers (non-spanning or single-column)
            for row_idx in range(header_rows):
                if row_idx >= len(grid) or not grid[row_idx]:
                    continue
                if col_idx >= len(grid[row_idx]):
                    continue
                    
                cell = grid[row_idx][col_idx]
                
                if cell.get('original_cell', False) and cell.get('type') == 'th':
                    text = cell.get('text', '').strip()
                    if text:
                        colspan = cell.get('original_colspan', 1)
                        # Only add single-column headers here (spanning already handled)
                        if colspan == 1 and text not in col_headers:
                            col_headers.append(text)
            
            # Store headers for this column
            if col_headers:
                context_map[col_idx] = col_headers
        
        return context_map
    
    def _is_title_content(self, text: str, row_idx: int, colspan: int, num_cols: int) -> bool:
        """Detect table titles that should be excluded"""
        if not text or row_idx > 2:
            return False
        
        if colspan < num_cols * 0.8:
            return False
        
        text_lower = text.lower().strip()
        title_indicators = [
            len(text.split()) >= 3,
            any(word in text_lower for word in ['schedule', 'report', 'summary', 'overview']),
            text.isupper() and len(text.split()) >= 2
        ]
        
        return any(title_indicators)
    
    def _extract_data_rules(self, grid: List[List[Dict]], row_context_map: Dict[int, List[str]], 
                   col_context_map: Dict[int, List[str]]) -> List[LogicRule]:
        """Extract rules with simplified, predictable context assembly - FOOTER ENABLED"""
        
        
        rules = []
        
        # Safety checks first
        if not grid:
            return rules
        
        num_rows = len(grid)
        if num_rows == 0:
            return rules
            
        # More robust column counting
        num_cols = 0
        for row in grid:
            if row and len(row) > num_cols:
                num_cols = len(row)
        
        if num_cols == 0:
            return rules
        
        # CRITICAL FIX: Process ALL rows including footer, not just data region
        data_start_row = self._find_data_start_row(grid)
        data_start_col = self._find_data_start_col(grid)
        
        # Process all rows from data start to end (including footer)
        for r in range(data_start_row, num_rows):
            # Safety check for row
            if r >= len(grid) or not grid[r]:
                continue
                
            for c in range(data_start_col, min(num_cols, len(grid[r]))):
                cell = grid[r][c]
                
                # Only process original cells
                if not cell.get('original_cell', False):
                    continue
                
                outcome_text = cell.get('text', '').strip()
                if not outcome_text:
                    continue
                
                # Universal filtering - but keep footer business data
                if self._is_placeholder_content(outcome_text):
                    continue
                
                # REMOVE footer filtering - let all business data through
                # Footer totals are valuable for RAG systems
                
                # Simple, predictable context assembly
                conditions = []
                
                # Always add row context first
                row_context = row_context_map.get(r, [])
                conditions.extend(row_context)
                
                # Always add column context second  
                col_context = col_context_map.get(c, [])
                conditions.extend(col_context)
                
                # Remove duplicates while preserving order
                unique_conditions = list(dict.fromkeys(conditions))
                
                # Filter out outcome from conditions (avoid circular logic)
                unique_conditions = [cond for cond in unique_conditions if cond != outcome_text]
                
                # Generate rule if valid
                if self._is_valid_rule(unique_conditions, outcome_text):
                    rule = LogicRule(
                        conditions=unique_conditions,
                        outcome=outcome_text,
                        position=(r, c),
                        is_summary=False
                    )
                    rules.append(rule)
        
        return rules
    
    def _is_valid_rule(self, conditions: List[str], outcome: str) -> bool:
        """Simple validation for rule generation"""
        # Must have at least one condition
        if not conditions:
            return False
        
        # Outcome must not be empty or just whitespace
        if not outcome or not outcome.strip():
            return False
        
        # Outcome must not be a placeholder (already checked, but double-check)
        if self._is_placeholder_content(outcome):
            return False
        
        # Very basic sanity check: outcome shouldn't be identical to all conditions
        if len(conditions) == 1 and conditions[0] == outcome:
            return False
        
        return True
    
    def _find_data_start_row(self, grid: List[List[Dict]]) -> int:
        """Simple data region detection: skip likely header rows"""
        # Universal approach: data typically starts after row 2
        # This works for most data tables regardless of structure
        num_rows = len(grid)
        return min(3, max(1, num_rows - 1))

    def _find_data_start_col(self, grid: List[List[Dict]]) -> int:
        """Simple data region detection: skip likely row label column"""
        # Universal approach: data typically starts after column 0
        # First column usually contains row identifiers/labels
        return 1
    
    def _is_placeholder_content(self, text: str) -> bool:
        """RAG-optimized placeholder detection - preserve useful metadata"""
        if not text:
            return True
        
        text = text.strip()
        
        # Empty or whitespace-only
        if not text or text.isspace():
            return True
        
        # Single character placeholders (clearly no semantic value)
        if len(text) == 1 and text in '—–-•':
            return True
        
        text_lower = text.lower().strip()
        
        # Only filter true placeholders with no semantic value
        clear_placeholders = {'tbd', 'tba', 'n/a', 'na', '—', '–', '...'}
        if text_lower in clear_placeholders:
            return True
        
        # Keep longer content even if it looks like notes - has RAG value
        if len(text) > 10:
            return False
        
        return False
    
    def _is_footer_content(self, cell: Dict, row_idx: int, num_rows: int, num_cols: int) -> bool:
        """RAG-optimized footer detection - only filter true metadata"""
        # HTML footer sections (legends, copyright, etc.)
        if cell.get('is_footer', False):
            return True
        
        # Only filter wide-spanning cells in the very bottom with generic metadata
        if row_idx >= num_rows - 1:  # Only last row
            colspan = cell.get('original_colspan', 1)
            if colspan >= num_cols * 0.8:  # Spans most columns
                text_lower = cell.get('text', '').lower()
                if any(word in text_lower for word in ['legend:', 'copyright', '©', 'all rights']):
                    return True
        
        # Keep session notes and requirements - they have RAG value
        return False


class FormTableProcessor(TableProcessor):
    """Processes form tables with label-value pairs"""
    
    def can_process(self, grid: List[List[Dict]], table_element) -> float:
        """Detect form tables using structural patterns"""
        if not grid or not grid[0]:
            return 0.0
        
        num_rows = len(grid)
        score = 0.0
        label_value_rows = 0
        
        # Look for label-value pair structure
        for r in range(min(8, num_rows)):
            original_cells = self._get_original_cells_in_row(grid, r)
            
            if len(original_cells) >= 2:
                pairs_found = 0
                i = 0
                while i + 1 < len(original_cells):
                    label_text = original_cells[i]
                    value_text = original_cells[i + 1]
                    
                    if self._looks_like_label_value_pair(label_text, value_text):
                        pairs_found += 1
                    i += 2
                
                if pairs_found >= 1:
                    label_value_rows += 1
        
        # Score based on form patterns
        if label_value_rows >= 3:
            score += 0.6
        elif label_value_rows >= 2:
            score += 0.4
        
        # Input elements boost score
        inputs = table_element.find_all(['input', 'select', 'textarea', 'button'])
        if inputs:
            score += min(0.3, len(inputs) / 10)
        
        return min(1.0, score)
    
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Process form table"""
        
        
        rules = []
        current_section = None
        num_rows = len(grid)
        num_cols = len(grid[0]) if grid else 0
        
        for r in range(num_rows):
            original_cells = self._get_original_cells_with_info(grid, r, num_cols)
            
            if not original_cells:
                continue
            
            # Check for section headers
            if len(original_cells) == 1 and original_cells[0][2] >= num_cols:
                current_section = original_cells[0][0]
                rule = LogicRule(
                    conditions=['form_section'],
                    outcome=original_cells[0][0],
                    position=(r, original_cells[0][1])
                )
                rules.append(rule)
                continue
            
            # Process label-value pairs
            i = 0
            while i + 1 < len(original_cells):
                label_text, label_col, _ = original_cells[i]
                value_text, _, _ = original_cells[i + 1]
                
                if not self._is_placeholder_value(value_text):
                    clean_label = label_text.rstrip(':').strip()
                    field_output = self._format_form_field(clean_label, value_text, current_section)
                    rule = LogicRule(
                        conditions=['form_field'],
                        outcome=field_output,
                        position=(r, label_col)
                    )
                    rules.append(rule)
                
                i += 2
        
        return ProcessingResult(
            rules=rules,
            confidence=0.7,
            metadata={"form_fields": len(rules)},
            processor_type="form_table"
        )
    
    def _get_original_cells_in_row(self, grid: List[List[Dict]], row_idx: int) -> List[str]:
        """Get original cell texts in a row"""
        if row_idx >= len(grid):
            return []
        cells = []
        num_cols = len(grid[0]) if grid else 0
        
        for c in range(num_cols):
            cell = grid[row_idx][c]
            if cell.get('original_cell', False):
                text = cell.get('text', '').strip()
                if text:
                    cells.append(text)
        
        return cells
    
    def _get_original_cells_with_info(self, grid: List[List[Dict]], row_idx: int, num_cols: int) -> List[Tuple[str, int, int]]:
        """Get original cells with position and span info"""
        cells = []
        for c in range(num_cols):
            cell = grid[row_idx][c]
            if cell.get('original_cell', False):
                text = cell.get('text', '').strip()
                if text:
                    colspan = cell.get('original_colspan', 1)
                    cells.append((text, c, colspan))
        
        return cells
    
    def _looks_like_label_value_pair(self, label_text: str, value_text: str) -> bool:
        """Check if two texts look like a label-value pair"""
        return (label_text.endswith(':') or 
                (len(label_text.split()) <= 4 and 
                 value_text != label_text and
                 not value_text.endswith(':')))
    
    def _is_placeholder_value(self, value: str) -> bool:
        """Check if value is a placeholder"""
        if not value:
            return True
        value_clean = value.strip().lower()
        placeholders = {'n/a', 'na', 'none', 'null', 'tbd', 'tba', 'pending', 'unknown'}
        return value_clean in placeholders
    
    def _format_form_field(self, label: str, value: str, section: str = None) -> str:
        """Format form field for output"""
        if section:
            return f"{section} | {label}: {value}"
        else:
            return f"{label}: {value}"


class LayoutTableProcessor(TableProcessor):
    """Processes layout tables used for positioning"""
    
    def can_process(self, grid: List[List[Dict]], table_element) -> float:
        """Detect layout tables"""
        if not grid or not grid[0]:
            return 0.0
        
        score = 0.0
        
        # Check for explicit layout indicators
        if table_element.get('role') == 'presentation':
            score += 0.5
        
        # Navigation content suggests layout
        nav_elements = table_element.find_all(['nav', 'a'])
        if nav_elements:
            score += 0.4
        
        # High empty cell ratio
        empty_ratio = self._calculate_empty_ratio(grid)
        if empty_ratio > 0.5:
            score += 0.3
        
        # Linear layouts
        num_rows = len(grid)
        num_cols = len(grid[0]) if grid else 0
        if num_rows == 1 or num_cols == 1:
            score += 0.3
        
        # Lack of semantic structure
        th_count = sum(1 for row in grid for cell in row if cell.get('type') == 'th')
        if th_count == 0:
            score += 0.2
        
        return min(1.0, score)
    
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Process layout table"""
        
        rules = []
        content_items = self._collect_content_items(grid)
        
        # Create rules for each content item
        for item in content_items:
            content_type = self._classify_content_type(item['text'])
            rule = LogicRule(
                conditions=[content_type],
                outcome=item['text'],
                position=item['position']
            )
            rules.append(rule)
        
        return ProcessingResult(
            rules=rules,
            confidence=0.6,
            metadata={"content_items": len(rules)},
            processor_type="layout_table"
        )
    
    def _calculate_empty_ratio(self, grid: List[List[Dict]]) -> float:
        """Calculate ratio of empty cells"""
        empty = 0
        total = 0
        
        for row in grid:
            for cell in row:
                if cell.get('original_cell', False):
                    total += 1
                    if not cell.get('text', '').strip():
                        empty += 1
        
        return empty / total if total > 0 else 0.0
    
    def _collect_content_items(self, grid: List[List[Dict]]) -> List[Dict]:
        """Collect content items from layout table"""
        items = []
        
        for r in range(len(grid)):
            for c in range(len(grid[0]) if grid else 0):
                cell = grid[r][c]
                if cell.get('original_cell', False):
                    text = cell.get('text', '').strip()
                    if text and len(text) > 1:
                        items.append({
                            'text': text,
                            'position': (r, c)
                        })
        
        return items
    
    def _classify_content_type(self, text: str) -> str:
        """Classify content type for layout tables"""
        if len(text) > 100:
            return 'layout_main_content'
        elif len(text.split()) <= 3:
            return 'layout_label'
        else:
            return 'layout_content'

class HierarchicalRowTableProcessor(TableProcessor):
    """Processes tables with hierarchical row headers that span multiple data rows"""
    
    def can_process(self, grid: List[List[Dict]], table_element) -> float:
        """Detect hierarchical row structure using structural patterns only"""
        if not grid or not grid[0]:
            return 0.0
        
        score = 0.0
        num_rows = len(grid)
        
        # Pattern 1: Multiple elements with rowspan > 1 (hierarchical structure)
        spanning_headers = 0
        for r in range(min(10, num_rows)):
            if r >= len(grid) or not grid[r]:
                continue
                
            for c in range(min(3, len(grid[r]))):
                cell = grid[r][c]
                
                if (cell.get('original_cell', False) and 
                    cell.get('original_rowspan', 1) > 1 and
                    self._looks_like_structural_header(cell, c)):
                    spanning_headers += 1

        if spanning_headers >= 2:
            score += 0.5
        elif spanning_headers >= 1:
            score += 0.3
        
        # Pattern 2: HTML semantic structure with row scope
        th_elements = table_element.find_all('th')
        row_scoped_headers = sum(1 for th in th_elements if th.get('scope') == 'row')
        
        if row_scoped_headers >= 3:
            score += 0.4
        elif row_scoped_headers >= 2:
            score += 0.2
        
        # Pattern 3: Mixed th/td structure suggesting hierarchy
        mixed_structure_rows = 0
        for r in range(min(8, num_rows)):
            if r >= len(grid) or not grid[r]:
                continue
            th_count = sum(1 for cell in grid[r] if cell.get('type') == 'th')
            td_count = sum(1 for cell in grid[r] if cell.get('type') == 'td')
            if th_count >= 1 and td_count >= 1:
                mixed_structure_rows += 1
        
        if mixed_structure_rows >= 4:
            score += 0.3
        elif mixed_structure_rows >= 2:
            score += 0.2
        
        return min(1.0, score)
    
    def _looks_like_structural_header(self, cell: Dict, col_idx: int) -> bool:
        """Detect structural headers regardless of th/td type"""
        text = cell.get('text', '').strip()
        
        # Empty cells are not structural
        if not text:
            return False
        
        # Short identifiers in first few columns (A, B, Section, etc.)
        if col_idx <= 2 and len(text.split()) <= 3:
            return True
        
        # th elements are always structural
        if cell.get('type') == 'th':
            return True
        
        return False
    
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        """Process hierarchical row table using structural awareness"""
        
        
        # Build context maps using universal patterns
        row_context_map = self._build_row_context_map(grid)
        column_context_map = self._build_column_context_map(grid)
        
        # Extract rules
        rules = self._extract_rules(grid, row_context_map, column_context_map)
        
        return ProcessingResult(
            rules=rules,
            confidence=0.85,
            metadata={
                "hierarchical_rules": len(rules),
                "structure_type": "hierarchical_rows"
            },
            processor_type="hierarchical_row_table"
        )
    
    def _build_row_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Build hierarchical row context using only HTML semantics"""
        context_map = {}
        
        if not grid:
            return context_map
        
        num_rows = len(grid)
        
        # Universal: Only th elements are structural headers per HTML standards
        for row_idx in range(num_rows):
            if row_idx >= len(grid) or not grid[row_idx]:
                continue
            
            for col_idx in range(len(grid[row_idx])):
                cell = grid[row_idx][col_idx]
                
                if not cell.get('original_cell', False):
                    continue
                
                # Universal HTML rule: only th elements are headers
                if cell.get('type') == 'th':
                    text = cell.get('text', '').strip()
                    if text:
                        if row_idx not in context_map:
                            context_map[row_idx] = []
                        if text not in context_map[row_idx]:
                            context_map[row_idx].append(text)
        
        return context_map

    def _is_row_identifier(self, text: str, col_idx: int) -> bool:
        """Universal detection of row identifiers including time slots"""
        # Time patterns: 09:00, 14:30, 9:00 AM, etc.
        time_patterns = [
            r'^\d{1,2}:\d{2}(\s*[AP]M)?$',  # 09:00, 9:00 AM
            r'^\d{1,2}[AP]M$',              # 9AM, 10PM
            r'^(Morning|Afternoon|Evening)$'  # Time words
        ]
        
        for pattern in time_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        
        # First column identifiers (traditional row headers)
        if col_idx == 0:
            return True
        
        # Short identifiers in early columns (track codes, room names)
        if col_idx <= 2 and len(text.split()) <= 3:
            return True
        
        return False
    
    def _build_column_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Build column context with post-repair grid structure"""
        context_map = {}
        
        if not grid:
            return context_map
        
        num_rows = len(grid)
        num_cols = len(grid[0]) if grid else 0
        header_rows = min(4, num_rows)
        
        # Process each column to build complete context
        for col_idx in range(num_cols):
            col_headers = []
            
            # Collect all headers that apply to this column
            for row_idx in range(header_rows):
                if row_idx >= len(grid) or col_idx >= len(grid[row_idx]):
                    continue
                
                cell = grid[row_idx][col_idx]
                
                # Only process original header cells
                if (cell.get('original_cell', False) and 
                    cell.get('type') == 'th' and 
                    cell.get('text', '').strip()):
                    
                    text = cell.get('text', '').strip()
                    
                    # Skip title-spanning headers
                    original_colspan = cell.get('original_colspan', 1)
                    if original_colspan >= num_cols * 0.8:
                        continue
                    
                    # Add this header
                    if text not in col_headers:
                        col_headers.append(text)
            
            # Store headers for this column
            if col_headers:
                context_map[col_idx] = col_headers
        
        return context_map
    
    def _extract_rules(self, grid: List[List[Dict]], row_context_map: Dict[int, List[str]], 
              column_context_map: Dict[int, List[str]]) -> List[LogicRule]:
        """Extract rules using universal content detection"""
        rules = []
        
        if not grid:
            return rules
        
        num_rows = len(grid)
        num_cols = max(len(row) for row in grid if row) if grid else 0
        
        # Find content region using universal heuristics
        content_start_row = self._find_content_start_row(grid)
        content_start_col = self._find_content_start_col(grid)
        
        for r in range(content_start_row, num_rows):
            if r >= len(grid) or not grid[r]:
                continue
            
            for c in range(content_start_col, min(num_cols, len(grid[r]))):
                cell = grid[r][c]
                
                # Only process original content cells (td, not th)
                if (not cell.get('original_cell', False) or 
                    cell.get('type') == 'th' or 
                    not cell.get('text', '').strip()):
                    continue
                
                outcome_text = cell.get('text', '').strip()
                
                # Universal placeholder filtering
                if self._is_placeholder_content(outcome_text):
                    continue

                # Skip footer content
                if self._is_footer_content(cell, r, num_rows):
                    continue
                
                # Build complete context
                conditions = []
                
                # Add row context (hierarchical)
                row_context = row_context_map.get(r, [])
                conditions.extend(row_context)
                
                # Add column context
                column_context = column_context_map.get(c, [])
                conditions.extend(column_context)
                
                # Remove duplicates and circular references
                unique_conditions = list(dict.fromkeys(conditions))
                unique_conditions = [cond for cond in unique_conditions if cond != outcome_text]
                
                if unique_conditions:
                    rule = LogicRule(
                        conditions=unique_conditions,
                        outcome=outcome_text,
                        position=(r, c),
                        is_summary=False
                    )
                    rules.append(rule)
        
        return rules
    
    def _find_content_start_row(self, grid: List[List[Dict]]) -> int:
        """Universal content detection - find first row with td elements"""
        num_rows = len(grid)
        for row_idx in range(min(6, num_rows)):
            if row_idx >= len(grid) or not grid[row_idx]:
                continue
            td_count = sum(1 for cell in grid[row_idx] if cell.get('type') == 'td')
            if td_count > 0:
                return row_idx
        return min(3, num_rows)
    
    def _find_content_start_col(self, grid: List[List[Dict]]) -> int:
        """Universal content detection - skip row header columns"""
        if not grid or not grid[0]:
            return 0
        
        # For hierarchical tables, content typically starts after the first column
        # First column contains row identifiers/headers like "AI", "Data", "Track"
        return 1
    
    def _is_footer_content(self, cell: Dict, row_idx: int, num_rows: int) -> bool:
        """RAG-optimized footer detection - preserve valuable summary data"""
        text = cell.get('text', '').strip().lower()
        
        # Only filter true table metadata - preserve all business data
        metadata_keywords = [
            'legend:',      # Legend explanations
            'copyright',    # Copyright notices  
            '©',           # Copyright symbol
            'all rights reserved',
            'disclaimer',
            'terms and conditions'
        ]
        
        # Only filter if it's clearly table metadata, not business data
        if any(keyword in text for keyword in metadata_keywords):
            return True
        
        # Keep ALL business content including totals, subtotals, summary data
        # Even if it's in footer sections - RAG systems need this data
        return False
    
    def _is_placeholder_content(self, text: str) -> bool:
        """RAG-optimized placeholder detection - only filter truly meaningless content"""
        if not text or not text.strip():
            return True
        
        text_clean = text.strip().lower()
        
        # ONLY filter completely meaningless placeholders
        # Keep TBD, —, etc. as they represent valid session states
        meaningless_placeholders = {
            '',           # Empty
            ' ',          # Whitespace only
            'null',       # Database null
            'none',       # Explicit none
            '...',        # Continuation dots only
        }
        
        # Very short meaningless content
        if len(text_clean) <= 1 and text_clean in ['', ' ', '.']:
            return True
        
        return text_clean in meaningless_placeholders
    
    