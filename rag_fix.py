#!/usr/bin/env python3
"""
rag_fix.py - RAG-oriented cleanup layer for table rules.

This module takes the ProcessingResult emitted by table processors
and applies business-focused cleanups so the rules are better suited
for retrieval-augmented generation (RAG).

Key functions:
- Normalize placeholders (TBD, None, dashes)
- Remove legend/footer metadata
- Deduplicate exact duplicates only
- Filter non-data explanatory content
"""

from typing import List, Set, Tuple
import re
import logging
from models import LogicRule, ProcessingResult

logger = logging.getLogger(__name__)


# --- Configuration ---

# None-like placeholder tokens (normalized to "None")
NONE_LIKE_TOKENS = {
    "", "-", "—", "–", "n/a", "na", "nil", "none", "null", "..."
}

# TBD-like placeholder tokens (normalized to "TBD")
TBD_LIKE_TOKENS = {
    "tbd", "tba", "pending", "to be decided", "to be determined"
}

# Keywords indicating legend/footer explanatory text (not data)
LEGEND_KEYWORDS = [
    "months indicate", "legend:", "copyright",
    "©", "all rights reserved", "disclaimer",
    "terms and conditions", "note:", "notes:"
]


# --- Normalization Functions ---

def _normalise_placeholder(text: str) -> str:
    """
    Unify placeholder tokens into consistent values for better RAG matching.
    
    Normalization rules:
    - Empty / dash / none-like → "None"
    - TBD / TBA / Pending → "TBD"
    - Everything else → unchanged
    
    Args:
        text: Raw cell text
        
    Returns:
        Normalized text with consistent placeholder values
        
    Examples:
        "" → "None"
        "—" → "None"
        "n/a" → "None"
        "TBD" → "TBD"
        "pending" → "TBD"
        "John Smith" → "John Smith" (unchanged)
    """
    if not text:
        return "None"

    t = text.strip().lower()

    # Check if this is a none-like placeholder
    if t in NONE_LIKE_TOKENS:
        return "None"

    # Check if this is a TBD-like placeholder
    if t in TBD_LIKE_TOKENS:
        return "TBD"

    # Pure dash sequences (---, ——, etc.)
    if re.fullmatch(r"[—–\-]+", t):
        return "None"

    # Return original text if not a placeholder
    return text.strip()


def _is_legend_or_footer(text: str) -> bool:
    """
    Detect explanatory metadata that isn't actual business data.
    
    Legend/footer content typically explains table structure or provides
    legal disclaimers, and should be filtered from RAG rules.
    
    Args:
        text: Cell text to check
        
    Returns:
        True if text appears to be legend/footer content
        
    Examples:
        "Legend: * indicates preliminary data" → True
        "© 2025 Company Name" → True
        "John Smith" → False
        "3.2M revenue" → False
    """
    if not text:
        return False
    t = text.strip().lower()
    return any(keyword in t for keyword in LEGEND_KEYWORDS)


# --- Core RAG Fix Function ---

def apply_rag_fixes(result: ProcessingResult) -> ProcessingResult:
    """
    Apply RAG cleanup transformations to improve retrieval quality.
    
    Transformations applied:
    1. Normalize placeholders (TBD, None, dashes) for consistency
    2. Filter out legend/footer explanatory text
    3. Deduplicate EXACT duplicates only (same context + outcome)
    4. Preserve meaningful duplicates (e.g., shared resource assignments)
    
    Strategy: We only remove TRUE duplicates (identical context AND outcome).
    We DO NOT collapse different contexts with same placeholder values,
    because "Track A at 09:00 = TBD" and "Track B at 09:00 = TBD" are
    two different facts.
    
    Args:
        result: ProcessingResult from table processor
        
    Returns:
        New ProcessingResult with cleaned rules
        
    Example:
        Input: 50 rules with 5 exact duplicates, 3 legend rows
        Output: 42 rules (cleaned, deduplicated)
    """
    if not result or not result.rules:
        return result

    cleaned: List[LogicRule] = []
    seen_exact: Set[Tuple[Tuple[str, ...], str]] = set()

    for rule in result.rules:
        # Step 1: Normalize placeholder values
        outcome = _normalise_placeholder(rule.outcome)

        # Step 2: Filter legend/footer explanatory text
        if _is_legend_or_footer(outcome):
            logger.debug(f"Filtered legend/footer: '{outcome[:50]}...'")
            continue

        # Step 3: Check for exact duplicates (same context + outcome)
        conditions_tuple = tuple(rule.conditions)
        exact_key = (conditions_tuple, outcome)
        
        if exact_key in seen_exact:
            logger.debug(f"Filtered exact duplicate: {conditions_tuple} → {outcome}")
            continue
            
        seen_exact.add(exact_key)
        
        # Step 4: Keep this cleaned rule
        cleaned.append(
            LogicRule(
                conditions=rule.conditions,
                outcome=outcome,
                position=rule.position,
                is_summary=rule.is_summary,
            )
        )

    logger.info(
        "RAG fix applied: %d → %d rules (dedup + filter)",
        len(result.rules), len(cleaned)
    )

    return ProcessingResult(
        rules=cleaned,
        confidence=result.confidence,
        metadata={**result.metadata, "rag_fix_applied": True},
        processor_type=result.processor_type,
    )