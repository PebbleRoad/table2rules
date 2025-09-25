#!/usr/bin/env python3
"""
Universal Table Standardizer - Pure HTML structural repair
Based solely on W3C HTML table standards, content-agnostic
"""

from bs4 import BeautifulSoup, Tag
from typing import List, Dict, Optional, Tuple, NamedTuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class StructuralViolation(Enum):
    """Finite set of HTML table structural violations"""
    DATA_CELL_ROWSPAN = "data_cell_rowspan"      # td[rowspan>1] violates grid semantics
    DATA_CELL_COLSPAN = "data_cell_colspan"      # td[colspan>1] violates grid semantics  
    HEADER_IN_BODY = "header_in_body"            # th element in tbody section
    DATA_IN_HEAD = "data_in_head"                # td element in thead section
    MISSING_SCOPE = "missing_scope"              # th without scope attribute


class Violation(NamedTuple):
    """Detected structural violation"""
    type: StructuralViolation
    element: Tag
    fix_priority: int  # 1=critical, 2=important, 3=semantic


class UniversalTableStandardizer:
    """Content-agnostic HTML table structure repair"""
    
    def __init__(self):
        self.violations_detected = []
        self.repair_stats = {
            'data_spans_removed': 0,
            'grid_cells_added': 0,
            'semantic_fixes': 0
        }
    
    def standardize(self, html_content: str) -> str:
        """Universal standardization based purely on HTML structure"""
        logger.info("Starting universal HTML table standardization...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return html_content
        
        # Step 1: Detect all structural violations
        self.violations_detected = self._detect_structural_violations(table)
        
        if not self.violations_detected:
            logger.info("Table structure already compliant with HTML standards")
            return html_content
        
        # Step 2: Log violations found
        self._log_violation_summary()
        
        # Step 3: Apply structural fixes in dependency order
        self._apply_structural_fixes(soup, table)
        
        # Step 4: Validate structure compliance
        remaining_issues = self._validate_html_compliance(table)
        
        logger.info(f"Standardization complete: {self.repair_stats}")
        if remaining_issues:
            logger.warning(f"Remaining non-compliance: {remaining_issues}")
        
        return str(soup)
    
    def _detect_structural_violations(self, table: Tag) -> List[Violation]:
        """Detect violations of HTML table structural rules"""
        violations = []
        
        # Violation 1: td elements with rowspan > 1 (breaks grid semantics)
        for td in table.find_all('td', {'rowspan': True}):
            if int(td.get('rowspan', 1)) > 1:
                violations.append(Violation(
                    type=StructuralViolation.DATA_CELL_ROWSPAN,
                    element=td,
                    fix_priority=1  # Critical - affects grid parsing
                ))
        
        # Violation 2: td elements with colspan > 1 (breaks grid semantics)
        for td in table.find_all('td', {'colspan': True}):
            if int(td.get('colspan', 1)) > 1:
                violations.append(Violation(
                    type=StructuralViolation.DATA_CELL_COLSPAN,
                    element=td,
                    fix_priority=1  # Critical - affects grid parsing
                ))
        
        # Violation 3: th elements in tbody (semantic violation)
        tbody = table.find('tbody')
        if tbody:
            for th in tbody.find_all('th'):
                # Only flag if it's not a proper row header
                if not self._is_valid_row_header(th):
                    violations.append(Violation(
                        type=StructuralViolation.HEADER_IN_BODY,
                        element=th,
                        fix_priority=3  # Semantic only
                    ))
        
        # Violation 4: td elements in thead (semantic violation)
        thead = table.find('thead')
        if thead:
            for td in thead.find_all('td'):
                violations.append(Violation(
                    type=StructuralViolation.DATA_IN_HEAD,
                    element=td,
                    fix_priority=2  # Important - affects header detection
                ))
        
        # Sort by priority (fix critical issues first)
        violations.sort(key=lambda v: v.fix_priority)
        return violations
    
    def _apply_structural_fixes(self, soup: BeautifulSoup, table: Tag):
        """Apply fixes in order of structural dependency"""
        
        # Phase 1: Fix critical grid violations first
        grid_violations = [v for v in self.violations_detected if v.fix_priority == 1]
        for violation in grid_violations:
            if violation.type == StructuralViolation.DATA_CELL_ROWSPAN:
                self._fix_data_cell_rowspan(soup, violation.element, table)
            elif violation.type == StructuralViolation.DATA_CELL_COLSPAN:
                self._fix_data_cell_colspan(soup, violation.element)
        
        # Phase 2: Fix semantic violations
        semantic_violations = [v for v in self.violations_detected if v.fix_priority > 1]
        for violation in semantic_violations:
            if violation.type == StructuralViolation.DATA_IN_HEAD:
                self._fix_data_in_head(violation.element)
            elif violation.type == StructuralViolation.HEADER_IN_BODY:
                self._fix_header_in_body(violation.element)
    
    def _fix_data_cell_rowspan(self, soup: BeautifulSoup, td_element: Tag, table: Tag):
        """Fix td[rowspan] by duplicating cell into grid positions - WITH DEBUG"""
        rowspan = int(td_element.get('rowspan', 1))
        content = td_element.get_text(strip=True)
        
        print(f"\n=== DEBUGGING SHARED CELL: '{content}' ===")
        print(f"Rowspan: {rowspan}")
        
        # Remove rowspan attribute (violates data cell semantics)
        del td_element['rowspan']
        
        # Calculate grid positions to fill
        current_row = td_element.find_parent('tr')
        all_rows = table.find_all('tr')
        current_row_index = all_rows.index(current_row)
        column_position = self._calculate_column_position(current_row, td_element)
        
        print(f"Original row index: {current_row_index}")
        print(f"Calculated column position: {column_position}")
        
        # Debug: Show the current row structure
        print("Current row cells:")
        for i, cell in enumerate(current_row.find_all(['td', 'th'])):
            cell_text = cell.get_text(strip=True)[:20]
            colspan = cell.get('colspan', '1')
            print(f"  [{i}] '{cell_text}' (colspan={colspan})")
        
        # Add data cells to subsequent rows to maintain grid structure
        for row_offset in range(1, rowspan):
            target_row_index = current_row_index + row_offset
            if target_row_index < len(all_rows):
                target_row = all_rows[target_row_index]
                
                print(f"\nTargeting row {target_row_index} for duplication:")
                print("Target row cells BEFORE insertion:")
                for i, cell in enumerate(target_row.find_all(['td', 'th'])):
                    cell_text = cell.get_text(strip=True)[:20]
                    colspan = cell.get('colspan', '1')
                    print(f"  [{i}] '{cell_text}' (colspan={colspan})")
                
                # Create new data cell with same content
                new_td = soup.new_tag('td')
                new_td.string = content
                
                # Copy all attributes except rowspan
                for attr, value in td_element.attrs.items():
                    if attr != 'rowspan':
                        new_td[attr] = value
                
                print(f"Inserting '{content}' at column position {column_position}")
                
                # Insert at correct grid position
                self._insert_at_column_position(target_row, new_td, column_position)
                
                print("Target row cells AFTER insertion:")
                for i, cell in enumerate(target_row.find_all(['td', 'th'])):
                    cell_text = cell.get_text(strip=True)[:20]
                    colspan = cell.get('colspan', '1')
                    print(f"  [{i}] '{cell_text}' (colspan={colspan})")
                
                self.repair_stats['grid_cells_added'] += 1
        
        print("=== END DEBUG ===\n")
        self.repair_stats['data_spans_removed'] += 1
    
    def _fix_data_cell_colspan(self, soup: BeautifulSoup, td_element: Tag):
        """Fix td[colspan] by duplicating cell content"""
        colspan = int(td_element.get('colspan', 1))
        content = td_element.get_text(strip=True)
        
        logger.info(f"Fixing data cell colspan: {colspan} columns")
        
        # Remove colspan attribute (violates data cell semantics)
        del td_element['colspan']
        
        # Add data cells to fill the column span
        current_cell = td_element
        for col_offset in range(1, colspan):
            # Create new data cell with same content
            new_td = soup.new_tag('td')
            new_td.string = content
            
            # Copy all attributes except colspan
            for attr, value in td_element.attrs.items():
                if attr != 'colspan':
                    new_td[attr] = value
            
            # Insert immediately after current cell
            current_cell.insert_after(new_td)
            current_cell = new_td  # Move reference for next insertion
            self.repair_stats['grid_cells_added'] += 1
        
        self.repair_stats['data_spans_removed'] += 1
    
    def _fix_data_in_head(self, td_element: Tag):
        """Convert td in thead to th (semantic fix)"""
        td_element.name = 'th'
        
        # Add column scope if missing
        if not td_element.get('scope'):
            td_element['scope'] = 'col'
        
        logger.info("Converted thead td to th")
        self.repair_stats['semantic_fixes'] += 1
    
    def _fix_header_in_body(self, th_element: Tag):
        """Convert invalid th in tbody to td"""
        # Only convert if it's not a valid row header
        if not self._is_valid_row_header(th_element):
            th_element.name = 'td'
            
            # Remove header-specific attributes
            if th_element.get('scope'):
                del th_element['scope']
            
            logger.info("Converted tbody th to td")
            self.repair_stats['semantic_fixes'] += 1
    
    def _is_valid_row_header(self, th_element: Tag) -> bool:
        """Check if th element is a valid row header (structural check only)"""
        # Valid if it has row scope or is first cell in row
        if th_element.get('scope') == 'row':
            return True
        
        # Check if it's the first cell in the row (common row header pattern)
        row = th_element.find_parent('tr')
        first_cell = row.find(['td', 'th'])
        return first_cell == th_element
    
    def _calculate_column_position(self, row: Tag, target_cell: Tag) -> int:
        """Calculate column position considering spans (structural only) - WITH DEBUG"""
        position = 0
        print(f"Calculating column position for target cell: '{target_cell.get_text(strip=True)[:20]}'")
        
        for i, cell in enumerate(row.find_all(['td', 'th'])):
            cell_text = cell.get_text(strip=True)[:20]
            cell_colspan = int(cell.get('colspan', 1))
            
            print(f"  Cell[{i}]: '{cell_text}' at position {position}, colspan={cell_colspan}")
            
            if cell == target_cell:
                print(f"  -> Found target cell at position {position}")
                break
            position += cell_colspan
        
        return position
    
    def _insert_at_column_position(self, row: Tag, new_cell: Tag, target_position: int):
        """Insert cell at correct position accounting for missing cells in target row"""
        cells = row.find_all(['td', 'th'])
        
        # Calculate where we actually need to insert based on target row's structure
        # The target row may have fewer cells due to missing spanned cells
        insertion_point = 0
        current_grid_position = 0
        
        # Skip any th elements at the beginning (row headers)
        while (insertion_point < len(cells) and 
            cells[insertion_point].name == 'th'):
            insertion_point += 1
            current_grid_position += int(cells[insertion_point-1].get('colspan', 1))
        
        # Now find the correct position among td elements
        while insertion_point < len(cells):
            if current_grid_position >= target_position:
                # Insert before this cell
                cells[insertion_point].insert_before(new_cell)
                return
            
            current_grid_position += int(cells[insertion_point].get('colspan', 1))
            insertion_point += 1
        
        # If we get here, append to end
        row.append(new_cell)
        
    def _validate_html_compliance(self, table: Tag) -> List[str]:
        """Check remaining structural violations"""
        issues = []
        
        # Check for remaining data cell spans
        remaining_td_rowspan = table.find_all('td', {'rowspan': True})
        remaining_td_colspan = table.find_all('td', {'colspan': True})
        
        if remaining_td_rowspan:
            issues.append(f"Remaining td[rowspan]: {len(remaining_td_rowspan)}")
        if remaining_td_colspan:
            issues.append(f"Remaining td[colspan]: {len(remaining_td_colspan)}")
        
        return issues
        
    def _log_violation_summary(self):
        """Log detected structural violations"""
        logger.info(f"Detected {len(self.violations_detected)} HTML structure violations:")
        
        by_type = {}
        for violation in self.violations_detected:
            type_name = violation.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        for type_name, count in by_type.items():
            logger.info(f"  {type_name}: {count} violations")


# Integration functions
def needs_universal_repair(html_content: str) -> bool:
    """Universal structural violation detection"""
    standardizer = UniversalTableStandardizer()
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table')
    
    if not table:
        return False
    
    violations = standardizer._detect_structural_violations(table)
    return len(violations) > 0


def universal_table_repair(html_content: str) -> str:
    """Universal HTML table structure repair"""
    standardizer = UniversalTableStandardizer()
    return standardizer.standardize(html_content)