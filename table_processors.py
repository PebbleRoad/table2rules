#!/usr/bin/env python3
"""
Table Processor System - Final, Unified Version
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from models import LogicRule, ProcessingResult

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
        if not text: return True
        return text.strip().lower() in {'', '-', '—', '–', 'n/a', 'na', 'tbd'}

class UniversalProcessor(TableProcessor):
    def can_process(self, grid: List[List[Dict]], table_element) -> float: return 1.0

    def _build_row_context_map(self, grid: List[List[Dict]]) -> Dict[int, List[str]]:
        """Simple rule: only spanning headers propagate (th OR td)"""
        context_map: Dict[int, List[str]] = {}
        if not grid: return context_map
        
        header_cols = [0, 1]
        active_contexts = ['', '']
        
        for r in range(len(grid)):
            row_contexts = []
            
            for i, c in enumerate(header_cols):
                if c >= len(grid[r]): continue
                
                cell = grid[r][c]
                cell_text = cell.get('text', '').strip()
                
                # Check for headers in EITHER th OR td cells
                if (cell_text and cell.get('original_cell', False)):
                    
                    # Only propagate if this cell originally spanned multiple rows
                    if cell.get('original_rowspan', 1) > 1:
                        active_contexts[i] = cell_text
                        row_contexts.append(active_contexts[i])
                    elif cell.get('type') == 'th':
                        # Non-spanning th cells still count as headers
                        row_contexts.append(cell_text)
                else:
                    # Inherit spanning context
                    if active_contexts[i]:
                        row_contexts.append(active_contexts[i])
            
            context_map[r] = row_contexts
        
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
        
        row_map, col_map = self._build_row_context_map(grid), self._build_column_context_map(grid)
        header_band_width = infer_row_header_band_width(grid)
        
        print(f"\nDEBUG: Processing grid with {len(grid)} rows, header_band_width = {header_band_width}")
        print(f"Row context map: {row_map}")
        print(f"Column context map: {col_map}")
        
        for r_idx, row in enumerate(grid):
            if any(cell.get('is_footer', False) for cell in row): continue
            
            print(f"\n--- Processing row {r_idx} ---")
            for c_idx, cell in enumerate(row):
                cell_text = cell.get('text', '').strip()
                cell_type = cell.get('type')
                is_original = cell.get('original_cell', False)
                
                print(f"  Cell[{c_idx}]: '{cell_text}' (type={cell_type}, original={is_original})")
                
                if cell.get('type') != 'td' or not cell.get('original_cell', False): 
                    print(f"    -> Skipped (not original td)")
                    continue
                
                outcome = cell.get('text','').strip()
                if self._is_placeholder(outcome): 
                    print(f"    -> Skipped (placeholder)")
                    continue
                
                row_ctx = row_map.get(r_idx, [])
                col_ctx = col_map.get(c_idx, [])
                all_context = row_ctx + col_ctx
                
                print(f"    -> Row context: {row_ctx}")
                print(f"    -> Col context: {col_ctx}")
                print(f"    -> Combined: {all_context}")
                
                # Only skip if this cell is purely redundant 
                if outcome in all_context and len(all_context) > 1:
                    print(f"    -> Skipped (redundant: '{outcome}' in context)")
                    continue
                
                rule = LogicRule(conditions=all_context, outcome=outcome, position=(r_idx, c_idx))
                rules.append(rule)
                print(f"    -> RULE CREATED: {' / '.join(all_context)} = {outcome}")
        
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