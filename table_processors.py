#!/usr/bin/env python3
"""
Table Processor System - Final, Unified Version with Geometric Partitioning
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from models import LogicRule, ProcessingResult
import re

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
    def can_process(self, grid: List[List[Dict]], table_element) -> float: return 1.0

    def _analyze_table_geometry(self, grid: List[List[Dict]]) -> Dict[str, Any]:
        """
        Mathematical analysis of table structure using geometric partitioning.
        Returns regions: header, row_context, column_context, data
        """
        if not grid or not grid[0]:
            return {'header_end_row': 0, 'context_end_col': 1, 'data_region': (0, 1, 0, 0)}
        
        num_rows, num_cols = len(grid), len(grid[0])
        
        # Step 1: Find header boundary (top rows with mostly th elements)
        header_end_row = self._find_header_boundary(grid)
        
        # Step 2: Find context boundary (left columns with categorical content)  
        context_end_col = self._find_context_boundary(grid, header_end_row)
        
        print(f"DEBUG GEOMETRY: {num_rows}x{num_cols} table")
        print(f"  Header region: rows 0-{header_end_row}")  
        print(f"  Context region: cols 0-{context_end_col}")
        print(f"  Data region: rows {header_end_row}+ cols {context_end_col}+")
        
        return {
            'header_end_row': header_end_row,
            'context_end_col': context_end_col,
            'data_region': (header_end_row, context_end_col, num_rows, num_cols)
        }

    def _find_header_boundary(self, grid: List[List[Dict]]) -> int:
        """Find where header section ends and data begins"""
        max_scan_rows = min(len(grid), 5)  # Don't scan too deep
        
        for r_idx in range(max_scan_rows):
            row = grid[r_idx]
            
            # Count th vs td elements with content
            th_count = sum(1 for cell in row if cell.get('type') == 'th' and cell.get('text', '').strip())
            td_count = sum(1 for cell in row if cell.get('type') == 'td' and cell.get('text', '').strip())
            total_content = th_count + td_count
            
            print(f"DEBUG HEADER: Row {r_idx} - {th_count} th, {td_count} td")
            
            # If this row has mostly data cells, header section has ended
            if total_content > 0 and td_count > th_count:
                return r_idx
        
        # Default: assume first row or two are headers
        return min(2, len(grid))

    def _find_context_boundary(self, grid: List[List[Dict]], header_end_row: int) -> int:
        """Find where row context ends and data values begin"""
        if header_end_row >= len(grid):
            return 1
        
        num_cols = len(grid[0])
        max_scan_cols = min(num_cols, 3)  # Typically context is in first few columns
        
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
                continue
                
            # Test: Is this column quantitative (data) or categorical (context)?
            quantitative_ratio = self._calculate_quantitative_ratio(column_cells)
            print(f"DEBUG CONTEXT: Col {c_idx} - {len(column_cells)} cells, {quantitative_ratio:.2f} quantitative")
            
            # If more than half the cells are quantitative, this is data region
            if quantitative_ratio > 0.5:
                return c_idx
        
        # Default: assume first column is context
        return 1

    def _calculate_quantitative_ratio(self, texts: List[str]) -> float:
        """Calculate what fraction of texts are quantitative (numbers, measurements)"""
        if not texts:
            return 0.0
        
        quantitative_count = 0
        for text in texts:
            if self._is_quantitative_content(text):
                quantitative_count += 1
        
        return quantitative_count / len(texts)

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
                        
                        # Clean up if this is the last row of the span
                        if r_idx == end_row:
                            del active_contexts[c_idx]
                        
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
                        print(f"DEBUG: Setting up span context - '{cell_text}' from row {r_idx} to {end_row}")
                    
                    elif cell.get('type') == 'th':
                        # Regular header cell (non-spanning)
                        row_contexts.append(cell_text)
            
            context_map[r_idx] = row_contexts
            print(f"DEBUG: Row {r_idx} context: {row_contexts}")
        
        return context_map

    def _build_column_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Build proper multi-level column context with full hierarchy preservation"""
        context_map: Dict[int, List[str]] = {}
        if not grid or not grid[0]: 
            return context_map
        
        num_cols = len(grid[0])
        
        # Better header detection: look for transition from mostly-th to mostly-td rows
        header_end_row = 0
        for r_idx, row in enumerate(grid):
            if r_idx >= 8: break  # Safety limit
            
            # Count non-empty th cells vs non-empty td cells
            th_count = sum(1 for c in row if c.get('type') == 'th' and c.get('text', '').strip())
            td_count = sum(1 for c in row if c.get('type') == 'td' and c.get('text', '').strip())
            total_content = th_count + td_count
            
            print(f"DEBUG: Row {r_idx}: {th_count} th, {td_count} td, total content: {total_content}")
            
            # If this row has substantial content and it's mostly headers, include it
            if total_content > 0 and th_count >= td_count:
                header_end_row = r_idx + 1
            elif total_content > 0:
                # This row has more data than headers, we've reached body
                break
        
        print(f"DEBUG: Header section ends at row {header_end_row}")
        
        # Build shadow grid that expands all spans
        shadow_grid = [['' for _ in range(num_cols)] for _ in range(header_end_row)]
        
        for r in range(header_end_row):
            current_col = 0
            for cell in grid[r]:
                if not cell.get('original_cell', False):
                    continue
                    
                # Skip positions already filled by previous spans
                while (current_col < num_cols and 
                    shadow_grid[r][current_col] != ''):
                    current_col += 1
                
                text = cell.get('text', '').strip()
                if not text:
                    current_col += 1
                    continue
                    
                # Get span dimensions
                rowspan = cell.get('original_rowspan', 1)
                colspan = cell.get('original_colspan', 1)
                
                # Fill shadow grid
                for row_offset in range(rowspan):
                    for col_offset in range(colspan):
                        if (r + row_offset < header_end_row and 
                            current_col + col_offset < num_cols):
                            shadow_grid[r + row_offset][current_col + col_offset] = text
                
                current_col += colspan
        
        # Build column contexts from shadow grid
        for c in range(num_cols):
            stack = []
            for r in range(header_end_row):
                text = shadow_grid[r][c]
                if text and text not in stack:  # Avoid duplicates in hierarchy
                    stack.append(text)
            
            if stack:
                context_map[c] = stack
                print(f"DEBUG: Column {c} context: {stack}")
        
        return context_map

    def process(self, grid: List[List[Dict]], table_element) -> ProcessingResult:
        rules: List[LogicRule] = []
        if not grid: return ProcessingResult(rules=rules)
        
        # NEW: Geometric analysis first
        geometry = self._analyze_table_geometry(grid)
        
        # Existing context building (unchanged)
        row_map, col_map = self._build_row_context_map(grid), self._build_column_context_map(grid)
        
        print(f"\nDEBUG: Processing grid with geometric partitioning")
        print(f"Row context map: {row_map}")
        print(f"Column context map: {col_map}")
        print(f"Geometry: {geometry}")
        
        # NEW: Process only the data region using geometric boundaries
        data_start_row = geometry['header_end_row']
        context_end_col = geometry['context_end_col'] 
        
        for r_idx in range(data_start_row, len(grid)):
            row = grid[r_idx]
            if any(cell.get('is_footer', False) for cell in row): 
                continue
            
            print(f"\n--- Processing data row {r_idx} ---")
            
            # Extract row context from context columns (0 to context_end_col-1)
            row_context = []
            for c_idx in range(min(context_end_col, len(row))):
                cell = row[c_idx]
                text = cell.get('text', '').strip()
                if text and not self._is_placeholder(text):
                    row_context.append(text)
            
            # If no explicit row context found, use row_map
            if not row_context:
                row_context = row_map.get(r_idx, [])
            
            print(f"  Row context: {row_context}")
            
            # Process data cells (from context_end_col onwards)
            for c_idx in range(context_end_col, len(row)):
                cell = row[c_idx]
                cell_text = cell.get('text', '').strip()
                
                print(f"  Cell[{c_idx}]: '{cell_text}'")
                
                # Only process cells with meaningful content
                if not cell_text or self._is_placeholder(cell_text):
                    print(f"    -> Skipped (empty/placeholder)")
                    continue
                
                # Build complete context: row + column
                col_context = col_map.get(c_idx, [])
                complete_context = row_context + col_context
                
                print(f"    -> Complete context: {complete_context}")
                
                # Avoid redundant rules (if outcome already in context)
                if cell_text in complete_context and len(complete_context) > 1:
                    print(f"    -> Skipped (redundant)")
                    continue
                
                # Create semantic rule
                rule = LogicRule(
                    conditions=complete_context, 
                    outcome=cell_text, 
                    position=(r_idx, c_idx)
                )
                rules.append(rule)
                print(f"    -> RULE: {' / '.join(complete_context)} = {cell_text}")
        
        print(f"\nTotal rules generated: {len(rules)}")
        return ProcessingResult(rules=rules, confidence=1.0, processor_type="UniversalProcessor")

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