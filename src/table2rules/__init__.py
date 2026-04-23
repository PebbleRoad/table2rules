"""table2rules — convert HTML tables to flat, LLM-friendly rules."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from ._core import process_table, process_tables_to_text, process_tables_with_stats
from .errors import Table2RulesError, TableTooLargeError
from .exporters import (
    Exporter,
    RulesExporter,
    available_exporters,
    register_exporter,
)
from .models import LogicRule
from .report import (
    REASONS,
    REASONS_BY_SEVERITY,
    RENDER_MODE_FLAT,
    RENDER_MODE_PASSTHROUGH,
    RENDER_MODE_RULES,
    RENDER_MODE_SKIPPED,
    RenderReport,
    TableReport,
)

try:
    __version__ = _pkg_version("table2rules")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "LogicRule",
    "process_table",
    "process_tables_to_text",
    "process_tables_with_stats",
    "RenderReport",
    "TableReport",
    "REASONS",
    "REASONS_BY_SEVERITY",
    "RENDER_MODE_RULES",
    "RENDER_MODE_FLAT",
    "RENDER_MODE_PASSTHROUGH",
    "RENDER_MODE_SKIPPED",
    "Table2RulesError",
    "TableTooLargeError",
    "Exporter",
    "RulesExporter",
    "available_exporters",
    "register_exporter",
]
