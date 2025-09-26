#!/usr/bin/env python3
"""
Data models for table2rules system
"""

import re
from typing import Any, Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class LogicRule:
    conditions: List[str]
    outcome: str
    position: Tuple[int, int]
    is_summary: bool = False
    
    def to_rule_string(self) -> str:
        """Original structured format"""
        if not self.conditions:
            return f"FACT: The value is '{self.outcome}'"
        
        condition_parts = [f'"{c}"' for c in self.conditions]
        conditions_str = " AND ".join(condition_parts)
        
        if self.is_summary:
            return f"SUMMARY: IF {conditions_str} THEN the value is '{self.outcome}'"
        else:
            return f"IF {conditions_str} THEN the value is '{self.outcome}'"
    
    def to_natural_formats(self) -> Dict[str, str]:
        """Generate two core formats"""
        return {
            'descriptive': self._to_descriptive(),
            'structured': self.to_rule_string()
        }

        # Build complete context string
        all_context = " ".join(self.conditions)
        return f"{all_context}, the content is {self.outcome}"
    
    def _to_descriptive(self) -> str:
        """Rich semantic description that preserves all context."""
        if not self.conditions:
            return f"The value is {self.outcome}"
        
        # Build complete context string
        all_context = " ".join(self.conditions)
        return f"{all_context}, the content is {self.outcome}"
    
    def _extract_categories(self) -> Dict[str, str]:
        categories = {}
        for condition in self.conditions:
            clean = condition.lower()
            if 'day' in clean:
                categories['day'] = condition
            elif re.search(r'\d{1,2}:\d{2}', clean):
                categories['time'] = condition
            elif any(word in clean for word in ['hall', 'room', 'track']):
                categories['location'] = condition
        return categories

@dataclass
class ProcessingResult:
    """
    Container for the outcome of a table processor run.

    - `rules`: the emitted LogicRule objects (may be empty on low-confidence or structural failure).
    - `confidence`: processor's confidence score in [0, 1].
    - `processor_type`: the processor's type/name (e.g., "HierarchicalRowTableProcessor").
    - `metadata`: arbitrary diagnostics (routing scores, timing, reasons for fallback, flags like is_subtotal, etc.)
    """
    rules: List['LogicRule']
    confidence: float = 1.0
    processor_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_meta(self, **kwargs) -> 'ProcessingResult':
        """Fluent helper to append metadata and return self."""
        self.metadata.update(kwargs)
        return self
