#!/usr/bin/env python3
"""
Table Processor System - Professional Logging Implementation
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from models import LogicRule, ProcessingResult
import re
import logging

# Set up module-level logger
logger = logging.getLogger(__name__)

def _is_meaningful_text(s: Optional[str]) -> bool:
    return s is not None and bool(str(s).strip())

def infer_row_header_band_width(grid: List[List[Dict]]) -> int:
    if not grid or not grid[0]: return 1
    scan_rows, max_k = min(len(grid), 10), min(4, len(grid[0]))
    candidate_k = 0
    for k in range(1, max_k + 1):
        th_cells, total_cells, is_definitive = 0, 0, False
        if k == 1 and any(grid[r][0].get("type") == "td" and grid[r][0].get("original_rowspan", 1) > 1 for r in range(scan_rows)):
            is_definitive = True
        for r in range(scan_rows):
            if all(c.get("type") == "th" for c in grid[r]): continue
            for c in range(k):
                if c < len(grid[r]):
                    if grid[r][c].get("type") == "th": th_cells += 1
                    total_cells += 1
        density = (th_cells / total_cells) if total_cells > 0 else 0
        if density > 0.3 or is_definitive: candidate_k = k
        else: break
    return max(1, candidate_k)

class TableProcessor(ABC):
    @abstractmethod
    def can_process(self, grid: List[List[Dict]], table_element) -> float: pass
    @abstractmethod  
    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult: pass
    
    def _is_placeholder(self, text: str) -> bool:
        """
        Determine if a cell contains only placeholder content that should be skipped.
        
        IMPORTANT: This should only skip truly empty cells. Let RAG fix handle 
        normalization of meaningful placeholders like "—", "TBD", "N/A" etc.
        
        The goal is to capture all meaningful content (including placeholders) 
        as rules, then let the RAG layer normalize them appropriately.
        """
        if not text:
            return True
        
        # Only skip completely empty or whitespace-only cells
        stripped = text.strip()
        if not stripped:
            return True
        
        # Don't skip meaningful placeholders - let them become rules
        # The RAG fix layer will normalize these to "None" or "TBD" appropriately
        return False

class UniversalProcessor(TableProcessor):
    def can_process(self, grid: List[List[Dict]], table_element) -> float: 
        return 1.0

    def _analyze_table_geometry(self, grid: List[List[Dict]]) -> Dict[str, Any]:
        """
        Mathematical analysis of table structure using geometric partitioning.
        Returns regions: header, row_context, column_context, data
        """
        if not grid or not grid[0]:
            logger.debug("Empty grid provided to geometry analysis")
            return {'header_end_row': 0, 'context_end_col': 1, 'data_region': (0, 1, 0, 0)}
        
        num_rows, num_cols = len(grid), len(grid[0])
        logger.debug(f"Analyzing geometry of {num_rows}x{num_cols} table")
        
        # Step 1: Find header boundary (top rows with mostly th elements)
        header_end_row = self._find_header_boundary(grid)
        
        # Step 2: Find context boundary (left columns with categorical content)  
        context_end_col = self._find_context_boundary(grid, header_end_row)
        
        logger.info(f"Geometric analysis complete: header_rows={header_end_row}, context_cols={context_end_col}")
        logger.debug(f"Data region starts at row {header_end_row}, column {context_end_col}")
        
        return {
            'header_end_row': header_end_row,
            'context_end_col': context_end_col,
            'data_region': (header_end_row, context_end_col, num_rows, num_cols)
        }

    def _find_header_boundary(self, grid: List[List[Dict]]) -> int:
        """Find where header section ends and data begins"""
        max_scan_rows = min(len(grid), 5)  # Don't scan too deep
        logger.debug(f"Scanning first {max_scan_rows} rows for header boundary")
        
        for r_idx in range(max_scan_rows):
            row = grid[r_idx]
            
            # Count th vs td elements with content
            th_count = sum(1 for cell in row if cell.get('type') == 'th' and cell.get('text', '').strip())
            td_count = sum(1 for cell in row if cell.get('type') == 'td' and cell.get('text', '').strip())
            total_content = th_count + td_count
            
            logger.debug(f"Row {r_idx}: {th_count} th cells, {td_count} td cells")
            
            # If this row has mostly data cells, header section has ended
            if total_content > 0 and td_count > th_count:
                logger.debug(f"Header boundary found at row {r_idx} (more td than th)")
                return r_idx
        
        # Default: assume first row or two are headers
        default_boundary = min(2, len(grid))
        logger.debug(f"Using default header boundary: {default_boundary}")
        return default_boundary

    def _find_context_boundary(self, grid: List[List[Dict]], header_end_row: int) -> int:
        """Find where row context ends and data values begin"""
        if header_end_row >= len(grid):
            logger.debug("Header extends beyond table, using default context boundary")
            return 1
        
        num_cols = len(grid[0])
        max_scan_cols = min(num_cols, 3)  # Typically context is in first few columns
        logger.debug(f"Scanning first {max_scan_cols} columns for context boundary")
        
        for c_idx in range(max_scan_cols):
            # Sample data cells from this column (skip header rows)
            column_cells = []
            for r_idx in range(header_end_row, len(grid)):
                if c_idx < len(grid[r_idx]):
                    cell = grid[r_idx][c_idx]
                    text = cell.get('text', '').strip()
                    if text and not self._is_placeholder(text):
                        column_cells.append(text)
            
            if not column_cells:
                logger.debug(f"Column {c_idx}: no content found")
                continue
                
            # Test: Is this column quantitative (data) or categorical (context)?
            quantitative_ratio = self._calculate_quantitative_ratio(column_cells)
            logger.debug(f"Column {c_idx}: {len(column_cells)} cells, {quantitative_ratio:.2f} quantitative ratio")
            
            # If more than half the cells are quantitative, this is data region
            if quantitative_ratio > 0.5:
                logger.debug(f"Context boundary found at column {c_idx} (quantitative content)")
                return c_idx
        
        # Default: assume first column is context
        logger.debug("Using default context boundary: column 1")
        return 1

    def _calculate_quantitative_ratio(self, texts: List[str]) -> float:
        """Calculate what fraction of texts are quantitative (numbers, measurements)"""
        if not texts:
            return 0.0
        
        quantitative_count = sum(1 for text in texts if self._is_quantitative_content(text))
        ratio = quantitative_count / len(texts)
        
        logger.debug(f"Quantitative analysis: {quantitative_count}/{len(texts)} = {ratio:.3f}")
        return ratio

    def _is_quantitative_content(self, text: str) -> bool:
        """Determine if text represents quantitative data"""
        if not text:
            return False
        
        text = text.strip()
        
        # Pattern 1: Pure numbers (with optional formatting)
        number_patterns = [
            r'^\d+$',                           # 123
            r'^\d+\.\d+$',                      # 123.45  
            r'^\$\d+(?:,\d{3})*(?:\.\d{2})?$',  # $1,234.56
            r'^\d+(?:,\d{3})*$',                # 1,234
            r'^\d+%$',                          # 25%
            r'^-?\d+(?:\.\d+)?$'                # -123.45
        ]
        
        for pattern in number_patterns:
            if re.match(pattern, text):
                return True
        
        # Pattern 2: Measurements with units
        if re.search(r'\d+\s*(?:GB|MB|KB|°C|°F|cm|mm|kg|lbs|hrs?|mins?|days?|%)', text):
            return True
            
        # Pattern 3: Ranges and comparisons  
        if re.search(r'\d+\s*[-–—]\s*\d+', text) or 'vs' in text.lower():
            return True
        
        return False

    def _build_row_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Mathematical span-based context propagation"""
        logger.debug("Building row context map with span-aware propagation")
        context_map: Dict[int, List[str]] = {}
        if not grid: 
            return context_map
        
        # Track active contexts by column position
        active_contexts: Dict[int, Tuple[str, int]] = {}  # col_idx -> (text, end_row_inclusive)
        
        for r_idx in range(len(grid)):
            row_contexts = []
            
            # Check first few columns for row headers (typically columns 0, 1)
            for c_idx in [0, 1]:
                if c_idx >= len(grid[r_idx]):
                    continue
                    
                cell = grid[r_idx][c_idx]
                cell_text = cell.get('text', '').strip()
                
                # First, check if there's an active span context for this column
                if c_idx in active_contexts:
                    context_text, end_row = active_contexts[c_idx]
                    
                    if r_idx <= end_row:
                        # We're still within the active span
                        row_contexts.append(context_text)
                        logger.debug(f"Row {r_idx}, col {c_idx}: inherited span context '{context_text}'")
                        
                        # Clean up if this is the last row of the span
                        if r_idx == end_row:
                            del active_contexts[c_idx]
                            logger.debug(f"Span context '{context_text}' completed at row {r_idx}")
                        
                        continue  # Don't process the current cell, use inherited context
                    else:
                        # Span has ended, remove it
                        del active_contexts[c_idx]
                
                # Process current cell if it has content and is original
                if cell_text and cell.get('original_cell', False):
                    rowspan = cell.get('original_rowspan', 1)
                    
                    if rowspan > 1:
                        # This cell spans multiple rows - set up active context
                        end_row = r_idx + rowspan - 1
                        active_contexts[c_idx] = (cell_text, end_row)
                        row_contexts.append(cell_text)
                        logger.debug(f"New span context: '{cell_text}' from row {r_idx} to {end_row}")
                    
                    elif cell.get('type') == 'th':
                        # Regular header cell (non-spanning)
                        row_contexts.append(cell_text)
                        logger.debug(f"Row {r_idx}, col {c_idx}: regular header '{cell_text}'")
            
            context_map[r_idx] = row_contexts
            if row_contexts:
                logger.debug(f"Row {r_idx} context: {row_contexts}")
        
        logger.info(f"Row context map built: {len([r for r, c in context_map.items() if c])} rows with context")
        return context_map

    def _build_column_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """
        Build column context hierarchy from logical grid.
        
        Strategy:
        1. Identify header rows (rows with mostly th cells)
        2. For each column, read down through header rows collecting unique text
        3. Build hierarchical context from parent to child headers
        """
        logger.debug("Building column context map from logical grid")
        context_map: Dict[int, List[str]] = {}
        
        if not grid or not grid[0]:
            return context_map
        
        num_rows = len(grid)
        num_cols = len(grid[0])
        
        # Step 1: Identify which rows are headers
        # A header row has more th cells with content than td cells with content
        header_rows = []
        
        for r_idx in range(min(num_rows, 8)):  # Don't scan too deep
            row = grid[r_idx]
            
            # Count cells with actual content by type
            th_with_content = sum(
                1 for cell in row 
                if cell.get('type') == 'th' and cell.get('text', '').strip()
            )
            td_with_content = sum(
                1 for cell in row 
                if cell.get('type') == 'td' and cell.get('text', '').strip()
            )
            
            total_content = th_with_content + td_with_content
            
            logger.debug(f"Row {r_idx}: {th_with_content} th, {td_with_content} td (total: {total_content})")
            
            # If this row has content and more headers than data, it's a header row
            if total_content > 0 and th_with_content >= td_with_content:
                header_rows.append(r_idx)
                logger.debug(f"Row {r_idx} identified as header row")
            elif th_with_content > 0:
                # Even if td > th, if there are SOME headers, might be a mixed header row
                # Include it if we already have header rows (it's a continuation)
                if header_rows:
                    header_rows.append(r_idx)
                    logger.debug(f"Row {r_idx} identified as continuation header row")
            elif total_content > 0:
                # This row has content but it's mostly data - we've left the header region
                break
        
        if not header_rows:
            logger.warning("No header rows identified")
            return context_map
        
        logger.info(f"Identified {len(header_rows)} header rows: {header_rows}")
        
        # Step 2: For each column, build context hierarchy from header rows
        for c_idx in range(num_cols):
            context_stack = []
            
            for r_idx in header_rows:
                if c_idx >= len(grid[r_idx]):
                    continue
                
                cell = grid[r_idx][c_idx]
                text = cell.get('text', '').strip()
                
                # Add to hierarchy if:
                # 1. Text is not empty
                # 2. Text is not already in the stack (avoid duplicates from spans)
                if text and text not in context_stack:
                    context_stack.append(text)
                    logger.debug(f"Column {c_idx}, row {r_idx}: added '{text}' to hierarchy")
            
            if context_stack:
                context_map[c_idx] = context_stack
                logger.debug(f"Column {c_idx} context: {' > '.join(context_stack)}")
        
        logger.info(f"Column context map built for {len(context_map)} columns")
        return context_map

    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        logger.info("Starting UniversalProcessor processing")
        rules: List[LogicRule] = []
        if not grid: 
            logger.warning("Empty grid provided")
            return ProcessingResult(rules=rules)
        
        # Geometric analysis first
        geometry = self._analyze_table_geometry(grid)
        
        # Build context maps
        logger.debug("Building context maps")
        row_map = self._build_row_context_map(grid)
        col_map = self._build_column_context_map(grid)
        
        # Process only the data region using geometric boundaries
        data_start_row = geometry['header_end_row']
        context_end_col = geometry['context_end_col'] 
        
        logger.info(f"Processing data region: rows {data_start_row}+ cols {context_end_col}+")
        
        # Track active sub-context from spanning header rows within data region
        active_subcontext = []
        
        rules_created = 0
        for r_idx in range(data_start_row, len(grid)):
            row = grid[r_idx]
            if any(cell.get('is_footer', False) for cell in row): 
                logger.debug(f"Skipping footer row {r_idx}")
                continue
            
            # CHECK #1: Is this a context modifier row? (Do this FIRST)
            is_context_row = self._is_context_modifier_row(row, context_end_col)
            
            if is_context_row:
                new_context = self._extract_context_from_row(row, context_end_col)
                if new_context:
                    active_subcontext = [new_context]
                    logger.info(f"Row {r_idx} is context modifier: '{new_context}'")
                continue  # Don't process as data row
            
            # Now extract row context (only if not a context modifier row)
            current_row_context = []
            for c_idx in range(min(context_end_col, len(row))):
                cell = row[c_idx]
                text = cell.get('text', '').strip()
                if text and not self._is_placeholder(text):
                    current_row_context.append(text)
            
            # If no explicit row context, use row_map
            if not current_row_context:
                current_row_context = row_map.get(r_idx, [])
            
            # If the first element of row context changed, clear subcontext
            # (this means we moved to a new major group like A->B or B->C)
            if (current_row_context and 
                hasattr(self, '_last_major_context') and 
                self._last_major_context and
                current_row_context[0] != self._last_major_context[0]):
                active_subcontext = []
                logger.debug(f"Major context changed, clearing subcontext")
            
            self._last_major_context = current_row_context
            
            # Process data cells (from context_end_col onwards)
            for c_idx in range(context_end_col, len(row)):
                cell = row[c_idx]
                cell_text = cell.get('text', '').strip()
                
                # Only process cells with meaningful content
                if not cell_text or self._is_placeholder(cell_text):
                    continue
                
                # Build complete context: row + active_subcontext + column
                col_context = col_map.get(c_idx, [])
                complete_context = current_row_context + active_subcontext + col_context
                
                # Avoid redundant rules (if outcome already in context)
                if cell_text in complete_context and len(complete_context) > 1:
                    logger.debug(f"Skipping redundant rule at ({r_idx},{c_idx}): '{cell_text}'")
                    continue
                
                # Create semantic rule
                rule = LogicRule(
                    conditions=complete_context, 
                    outcome=cell_text, 
                    position=(r_idx, c_idx)
                )
                rules.append(rule)
                rules_created += 1
                
                if rules_created <= 10:  # Only log first 10 for brevity
                    logger.debug(f"Rule {rules_created}: {' / '.join(complete_context)} = {cell_text}")
        
        logger.info(f"UniversalProcessor completed: {len(rules)} rules generated")
        return ProcessingResult(rules=rules, confidence=1.0, processor_type="UniversalProcessor")
    
    def _is_context_modifier_row(self, row: List[Dict], context_end_col: int) -> bool:
        """
        Detect if a row is a context modifier rather than a data row.
        
        Context modifier characteristics:
        - Contains a cell (th OR td) with colspan > 1 in the data region
        - That cell contains non-numeric descriptive text
        """
        # Look at cells in the data region (from context_end_col onwards)
        for c_idx in range(context_end_col, len(row)):
            cell = row[c_idx]
            
            # Check if this is an original cell (not a span reference)
            if not cell.get('original_cell', False):
                continue
            
            text = cell.get('text', '').strip()
            colspan = cell.get('original_colspan', 1)
            
            # Debug: Log all cells we're checking
            logger.debug(f"  Checking cell at col {c_idx}: text='{text[:50]}', "
                        f"colspan={colspan}, original_cell={cell.get('original_cell')}")
            
            # Must have colspan > 1
            if colspan <= 1:
                continue
            
            if not text:
                continue
            
            # Check if text is descriptive (not purely numeric)
            is_descriptive = not self._is_quantitative_content(text)
            
            if is_descriptive:
                logger.info(f"Detected context modifier cell: '{text}' "
                        f"(type={cell.get('type')}, colspan={colspan})")
                return True
        
        return False

    def _extract_context_from_row(self, row: List[Dict], context_end_col: int) -> str:
        """
        Extract the context text from a context modifier row.
        Returns the text from the spanning cell (th or td).
        """
        for c_idx in range(context_end_col, len(row)):
            cell = row[c_idx]
            
            if not cell.get('original_cell', False):
                continue
            
            # Look for any spanning cell with descriptive content (not just th)
            if cell.get('original_colspan', 1) > 1:
                text = cell.get('text', '').strip()
                if text and not self._is_quantitative_content(text):
                    return text
        
        return ""

# --- All other processors are now just placeholders ---
class DataTableProcessor(TableProcessor):
    def can_process(self, grid, e): return 0.1
    def process(self, grid, e): return ProcessingResult(rules=[])

class HierarchicalRowTableProcessor(TableProcessor):
    def can_process(self, grid, e): return 0.1
    def process(self, grid, e): return ProcessingResult(rules=[])

class FormTableProcessor(TableProcessor):
    def can_process(self, grid, e): return 0.0
    def process(self, grid, e): return ProcessingResult(rules=[])

class LayoutTableProcessor(TableProcessor):
    def can_process(self, grid, e): return 0.0
    def process(self, grid, e): return ProcessingResult(rules=[])