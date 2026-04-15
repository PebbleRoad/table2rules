"""Pluggable output exporters for table2rules.

Built-in:
    - "rules" (default): one rule per line, full header paths — the native
      table2rules format.

Third parties can register custom exporters:

    from table2rules.exporters import Exporter, register_exporter

    class MyExporter:
        name = "mine"
        def export_rules(self, rules): ...
        def export_flat(self, cell_rows): ...

    register_exporter(MyExporter())
"""

from .base import Exporter, available_exporters, get_exporter, register_exporter
from .rules import RulesExporter

register_exporter(RulesExporter())

DEFAULT_FORMAT = "rules"

__all__ = [
    "Exporter",
    "RulesExporter",
    "DEFAULT_FORMAT",
    "available_exporters",
    "get_exporter",
    "register_exporter",
]
