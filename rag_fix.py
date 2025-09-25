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
    Apply RAG cleanups to a ProcessingResult:
    1. Smart deduplicate - preserve context-establishing duplicates
    2. Collapse placeholder-like outcomes across multiple columns.
    3. Normalise placeholders (N/A).
    4. Filter legend/footer rules.
    """
    if not result or not result.rules:
        return result

    cleaned: List[LogicRule] = []
    seen: Set[Tuple[Tuple[str, ...], str, Tuple[int, int]]] = set()  # Include position
    placeholder_seen: Dict[Tuple[str, ...], str] = {}

    for rule in result.rules:
        outcome = _normalise_placeholder(rule.outcome)

        # Filter legend/footer explanatory lines
        if _is_legend_or_footer(outcome):
            continue

        conditions_tuple = tuple(rule.conditions)

        # Collapse repeated placeholders: only keep one per row-context
        if _is_placeholder_like(outcome):
            row_ctx = tuple(rule.conditions[:1]) if rule.conditions else ()
            if row_ctx in placeholder_seen:
                continue
            placeholder_seen[row_ctx] = outcome

        # Smart deduplication: Include position to preserve meaningful duplicates
        # This allows "Track = AI" to appear multiple times for different sessions
        key = (conditions_tuple, outcome, rule.position)
        if key in seen:
            continue
        seen.add(key)

        # However, we still want to deduplicate EXACT same rules at same position
        # Check for true duplicates (same content, same position)
        exact_key = (conditions_tuple, outcome, rule.position)
        duplicate_found = False
        for existing_rule in cleaned:
            existing_key = (tuple(existing_rule.conditions), existing_rule.outcome, existing_rule.position)
            if existing_key == exact_key:
                duplicate_found = True
                break
        
        if duplicate_found:
            continue

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
