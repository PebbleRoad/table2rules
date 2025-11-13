#!/usr/bin/env python3
"""
Data models for table2rules system
"""

import re
from typing import Any, Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class LogicRule:
    """
    Represents a single rule extracted from a table.
    
    A rule consists of:
    - conditions: list of context strings from row/column headers
    - outcome: the data cell value
    - position: (row, col) tuple for debugging
    - is_summary: flag for subtotal/summary rows
    """
    conditions: List[str]
    outcome: str
    position: Tuple[int, int]
    is_summary: bool = False
    
    def to_rule_string(self) -> str:
        """
        Generate structured IF-THEN format.
        
        Examples:
            IF "Americas" AND "Alpha" AND "Quarter Q1" THEN the value is '3.2'
            FACT: The value is '3.2' (when no conditions)
        """
        if not self.conditions:
            return f"FACT: The value is '{self.outcome}'"
        
        condition_parts = [f'"{c}"' for c in self.conditions]
        conditions_str = " AND ".join(condition_parts)
        
        if self.is_summary:
            return f"SUMMARY: IF {conditions_str} THEN the value is '{self.outcome}'"
        else:
            return f"IF {conditions_str} THEN the value is '{self.outcome}'"
    
    def to_natural_formats(self) -> Dict[str, str]:
        """
        Generate two core output formats for different use cases.
        
        Returns:
            dict with 'descriptive' and 'structured' keys
        """
        return {
            'descriptive': self._to_descriptive(),
            'structured': self.to_rule_string()
        }
    
    def _to_descriptive(self) -> str:
        """
        Rich semantic description optimized for RAG embeddings.
        
        Preserves all context in natural language format.
        
        Examples:
            "Americas Alpha Quarter Q1, the content is 3.2"
            "The value is 3.2" (when no conditions)
        """
        if not self.conditions:
            return f"The value is {self.outcome}"
        
        # Build complete context string
        all_context = " ".join(self.conditions)
        return f"{all_context}, the content is {self.outcome}"


@dataclass
class ProcessingResult:
    """
    Container for the outcome of a table processor run.
    
    Attributes:
        rules: List of LogicRule objects extracted from the table
        confidence: Processor's confidence score in [0, 1]
        processor_type: Name of the processor that generated these rules
        metadata: Arbitrary diagnostics (routing scores, timing, flags, etc.)
    """
    rules: List['LogicRule']
    confidence: float = 1.0
    processor_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_meta(self, **kwargs) -> 'ProcessingResult':
        """
        Fluent helper to append metadata and return self.
        
        Usage:
            result.add_meta(timing=0.5, source="universal_processor")
        """
        self.metadata.update(kwargs)
        return self