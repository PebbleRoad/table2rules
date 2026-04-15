from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class LogicRule:
    conditions: List[str]          # Kept for backward compatibility
    outcome: str
    position: Tuple[int, int]      # Expanded grid position (post-span)
    is_footer: bool = False
    row_headers: List[str] = None  # Entity/subject dimension
    col_headers: List[str] = None  # Attribute/measurement dimension
    origin: Tuple[int, int] = None # Source cell position (pre-span); used to
                                   # collapse span-expanded duplicates without
                                   # eating legitimate cross-row duplicates
    
    def __post_init__(self):
        # Initialize as empty lists if None
        if self.row_headers is None:
            self.row_headers = []
        if self.col_headers is None:
            self.col_headers = []
    
    def to_string(self) -> str:
        """Default descriptive format for Graph-RAG"""
        # Use separated row/col headers if available, otherwise fall back to conditions
        if self.row_headers or self.col_headers:
            parts = []
            if self.row_headers:
                parts.append(" | ".join(self.row_headers))
            if self.col_headers:
                parts.append(" | ".join(self.col_headers))
            
            if len(parts) == 2:
                context = f"{parts[0]} → {parts[1]}"
            elif len(parts) == 1:
                context = parts[0]
            else:
                return f"value: {self.outcome}"
            
            return f"{context}: {self.outcome}"
        
        # Fallback to old format
        if not self.conditions:
            return f"value: {self.outcome}"
        
        context = " | ".join(self.conditions)
        return f"{context}: {self.outcome}"