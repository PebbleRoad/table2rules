"""table2rules — convert HTML tables to flat, LLM-friendly rules."""

from .models import LogicRule
from ._core import process_table, process_tables_to_text
from .exporters import (
    Exporter,
    RulesExporter,
    available_exporters,
    register_exporter,
)

__all__ = [
    "LogicRule",
    "process_table",
    "process_tables_to_text",
    "Exporter",
    "RulesExporter",
    "available_exporters",
    "register_exporter",
]
