from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class LogicRule:
    conditions: List[str]
    outcome: str
    position: Tuple[int, int]
    is_footer: bool = False
    
    def to_string(self) -> str:
        """Default descriptive format for Graph-RAG"""
        if not self.conditions:
            return f"value: {self.outcome}"
        
        context = " ".join(self.conditions)
        return f"{context}: {self.outcome}"
    
    def to_keyvalue(self) -> str:
        """Compact key-value format: attr1=val1 attr2=val2 ... value=outcome"""
        if not self.conditions:
            return f"value={self.outcome}"
        
        # Create key-value pairs from conditions
        pairs = []
        for i, condition in enumerate(self.conditions):
            # Use generic keys: attr0, attr1, attr2, etc.
            key = f"attr{i}"
            # Clean the value (remove spaces for compactness)
            value = condition.replace(" ", "_")
            pairs.append(f"{key}={value}")
        
        # Add the outcome
        pairs.append(f"value={self.outcome}")
        
        return " ".join(pairs)