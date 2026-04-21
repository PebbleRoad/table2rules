"""table2rules — convert HTML tables to flat, LLM-friendly rules."""

from ._core import process_table, process_tables_to_text, process_tables_with_stats
from .errors import Table2RulesError, TableTooLargeError
from .exporters import (
    Exporter,
    RulesExporter,
    available_exporters,
    register_exporter,
)
from .models import LogicRule
from .report import REASONS, RenderReport, TableReport

__all__ = [
    "LogicRule",
    "process_table",
    "process_tables_to_text",
    "process_tables_with_stats",
    "RenderReport",
    "TableReport",
    "REASONS",
    "Table2RulesError",
    "TableTooLargeError",
    "Exporter",
    "RulesExporter",
    "available_exporters",
    "register_exporter",
]
