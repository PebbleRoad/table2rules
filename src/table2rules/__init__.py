"""table2rules — convert HTML tables to flat, LLM-friendly rules."""

from .models import LogicRule
from ._core import process_table, process_tables_to_text, group_rules_by_row

__all__ = [
    "LogicRule",
    "process_table",
    "process_tables_to_text",
    "group_rules_by_row",
]
