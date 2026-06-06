from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class LogicRule:
    outcome: str
    position: Tuple[int, int]
    row_headers: Tuple[str, ...] = ()
    col_headers: Tuple[str, ...] = ()
    origin: Optional[Tuple[int, int]] = None
    is_footer: bool = False
    # A label-preservation rule: the row carried a label but no independent
    # value (empty value column, or a value that merely echoes the column
    # header). The label is preserved verbatim as the outcome with no header
    # relationship. The confidence gate treats these as pass-through, not a
    # parser-confidence signal.
    is_label: bool = False

    def to_string(self) -> str:
        """Descriptive format for Graph-RAG: '<rows> → <cols>: <value>'."""
        parts = []
        if self.row_headers:
            parts.append(" | ".join(self.row_headers))
        if self.col_headers:
            parts.append(" | ".join(self.col_headers))
        if not parts:
            return f"value: {self.outcome}"
        context = parts[0] if len(parts) == 1 else f"{parts[0]} → {parts[1]}"
        return f"{context}: {self.outcome}"
