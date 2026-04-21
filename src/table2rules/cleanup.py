import re
from dataclasses import replace
from typing import List, Tuple

from .models import LogicRule


def clean_rules(rules: List[LogicRule]) -> List[LogicRule]:
    """
    Post-processing cleanup.

    Fixes:
    1. Remove duplicate headers
    2. Filter footer/legend content
    3. Drop self-echo rules (value == column header)
    """
    cleaned: List[LogicRule] = []

    for rule in rules:

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

        cleaned.append(replace(
            rule,
            row_headers=deduplicate_headers(rule.row_headers),
            col_headers=deduplicate_headers(rule.col_headers),
        ))

    return cleaned


def deduplicate_headers(headers: Tuple[str, ...]) -> Tuple[str, ...]:
    """Remove exact duplicates while preserving order."""
    seen = set()
    unique: List[str] = []
    for h in headers:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return tuple(unique)
