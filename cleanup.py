from typing import List
from models import LogicRule


def clean_rules(rules: List[LogicRule]) -> List[LogicRule]:
    """
    Post-processing cleanup.
    
    Fixes:
    1. Remove duplicate headers
    2. Filter footer/legend content *only*
    """
    cleaned = []
    
    for rule in rules:
        
        # NEW: Only apply content-based filtering to footer cells
        if rule.is_footer:
            text = rule.outcome.lower()
            
            # Be specific: only filter if it starts with these keywords or contains "legend:"
            if text.startswith('note:') or text.startswith('footnote') or 'legend:' in text or 'months indicate' in text:
                continue
            
            # Also filter numbered footnotes (e.g., "1 Workshop requires... 2 Panel includes...")
            # These typically have multiple numbered items
            import re
            if re.search(r'^\d+\s+\w+.*\d+\s+\w+', text):  # Starts with "1 Word... 2 Word..."
                continue

        # This part now runs for ALL rules, including data-footers
        cleaned_conditions = deduplicate_headers(rule.conditions)
        
        cleaned.append(LogicRule(
            conditions=cleaned_conditions,
            outcome=rule.outcome,
            position=rule.position
        ))
    
    return cleaned


def deduplicate_headers(headers: List[str]) -> List[str]:
    """
    Remove exact duplicates and substring duplicates.
    
    Rules:
    - If "APAC" appears twice, keep one
    - If "APAC" and "APAC Subtotal" both appear, keep only "APAC Subtotal"
    """
    # Remove exact duplicates while preserving order
    seen = set()
    unique = []
    for h in headers:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    
    # Remove substrings: if header A is fully contained in header B, remove A
    filtered = []
    for i, header in enumerate(unique):
        is_substring = False
        for j, other in enumerate(unique):
            if i != j and header in other and header != other:
                is_substring = True
                break
        
        if not is_substring:
            filtered.append(header)
    
    return filtered