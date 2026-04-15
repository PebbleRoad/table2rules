import re
from typing import List
from .models import LogicRule


def clean_rules(rules: List[LogicRule]) -> List[LogicRule]:
    """
    Post-processing cleanup.
    
    Fixes:
    1. Remove duplicate headers
    2. Filter footer/legend content
    """
    cleaned = []
    
    for rule in rules:
        
        # Only apply content-based filtering to footer cells
        if rule.is_footer:
            text = rule.outcome.lower()
            
            if text.startswith('note:') or text.startswith('footnote') or 'legend:' in text or 'months indicate' in text:
                continue
            
            if re.search(r'^\d+\s+\w+.*?\d+\s+\w+', text):
                continue

        # Drop self-echo rules: value identical to its column header.
        # These come from body rows that repeat the header text (OCR artifacts,
        # page-break header repeats).  They carry zero information.
        if rule.col_headers and rule.outcome.strip().lower() in (
            h.strip().lower() for h in rule.col_headers
        ):
            continue

        cleaned_conditions = deduplicate_headers(rule.conditions)
        cleaned_row_headers = deduplicate_headers(rule.row_headers)
        cleaned_col_headers = deduplicate_headers(rule.col_headers)
        
        cleaned.append(LogicRule(
            conditions=cleaned_conditions,
            outcome=rule.outcome,
            position=rule.position,
            is_footer=rule.is_footer,
            row_headers=cleaned_row_headers,
            col_headers=cleaned_col_headers,
            origin=rule.origin,
        ))
    
    return cleaned


def deduplicate_headers(headers: List[str]) -> List[str]:
    """
    Remove exact duplicates while preserving order.
    The dangerous substring logic has been removed.
    """
    # Remove exact duplicates while preserving order
    seen = set()
    unique = []
    for h in headers:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    
    return unique