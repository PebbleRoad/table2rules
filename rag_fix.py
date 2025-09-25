#!/usr/bin/env python3
"""
rag_fix.py - RAG-oriented cleanup layer for table rules.

This module takes the ProcessingResult emitted by table processors
and applies business-focused cleanups so the rules are better suited
for retrieval-augmented generation (RAG).
"""

from typing import List, Dict, Set, Tuple
import re
import logging
from models import LogicRule, ProcessingResult

logger = logging.getLogger(__name__)


# --- Utilities ---

PLACEHOLDER_NORMALS = {
    "-", "—", "–", "n/a", "na", "nil", "none", ""
}

LEGEND_KEYWORDS = [
    "months indicate", "legend:", "copyright",
    "©", "all rights reserved", "disclaimer",
    "terms and conditions"
]


def _normalise_placeholder(text: str) -> str:
    """
    Unify placeholder tokens into consistent values.
    - Empty / dash / none-like → "None"
    - TBD / TBA / Pending / To be decided → "TBD"
    """
    if not text:
        return "None"

    t = text.strip().lower()

    # None-like placeholders
    none_like = {"", "-", "—", "–", "n/a", "na", "nil", "none", "null", "..."}
    if t in none_like:
        return "None"

    # TBD-like placeholders
    tbd_like = {"tbd", "tba", "pending", "to be decided", "to be determined"}
    if t in tbd_like:
        return "TBD"

    # Pure dash sequences (---, ——, etc.)
    if re.fullmatch(r"[–—\-]+", t):
        return "None"

    return text.strip()



def _is_legend_or_footer(text: str) -> bool:
    """Detect explanatory metadata (not business data)."""
    if not text:
        return False
    t = text.strip().lower()
    return any(k in t for k in LEGEND_KEYWORDS)


def _is_placeholder_like(text: str) -> bool:
    """
    Detect broad placeholder-only content, not business descriptions.
    Only collapse short, generic placeholders like "TBD" or "None".
    """
    if not text:
        return False
    t = text.strip().lower()

    # Only treat generic markers as placeholders
    generic_placeholders = {
        "tbd", "tba", "pending", "to be decided",
        "to be determined", "none", "n/a", "na", "nil", "-"
    }

    return t in generic_placeholders



# --- Core RAG Fix ---

def apply_rag_fixes(result: ProcessingResult) -> ProcessingResult:
    """
    Apply RAG cleanups with better deduplication logic
    """
    if not result or not result.rules:
        return result

    cleaned: List[LogicRule] = []
    seen_exact: Set[Tuple[Tuple[str, ...], str]] = set()
    
    # REMOVED: placeholder_seen logic - let each unique context keep its placeholder

    for rule in result.rules:
        outcome = _normalise_placeholder(rule.outcome)

        # Filter legend/footer explanatory lines
        if _is_legend_or_footer(outcome):
            continue

        conditions_tuple = tuple(rule.conditions)

        # REMOVED: Placeholder collapse logic - preserve all meaningful placeholders
        # Each unique context should keep its own placeholder value

        # Only deduplicate TRUE duplicates (same context AND outcome)
        exact_key = (conditions_tuple, outcome)
        
        if exact_key in seen_exact:
            continue
            
        seen_exact.add(exact_key)
        
        cleaned.append(
            LogicRule(
                conditions=rule.conditions,
                outcome=outcome,
                position=rule.position,
                is_summary=rule.is_summary,
            )
        )

    logger.info(
        "RAG fix applied: %d → %d rules (dedup + collapse + filter)",
        len(result.rules), len(cleaned)
    )

    return ProcessingResult(
        rules=cleaned,
        confidence=result.confidence,
        metadata={**result.metadata, "rag_fix_applied": True},
        processor_type=result.processor_type,
    )
