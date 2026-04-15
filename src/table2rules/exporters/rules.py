"""Rules exporter — the native table2rules format.

One self-contained rule per line:

    <row-path> | <col-path>: <value>

Where row-path and col-path join nested header levels with ' > '.
Full header ancestry on every line so an LLM never loses column
context across rows. Informed by TIDE (ICLR 2025) and ASTRA (2025).
"""

from __future__ import annotations

from typing import List

from ..models import LogicRule

PATH_SEP = " > "
ROW_COL_SEP = " | "


class RulesExporter:
    name = "rules"

    def export_rules(self, rules: List[LogicRule]) -> List[str]:
        # Sort by (row, col) so output follows reading order.
        #
        # Dedup is *origin-aware*: a single source cell expanded across
        # multiple positions via rowspan/colspan can produce identical
        # lines, which we collapse. But two different source cells that
        # happen to render identically (e.g. two rows each with Qty: 1)
        # are kept — dropping either would silently lose data.
        ordered = sorted(rules, key=lambda r: r.position)
        lines: List[str] = []
        seen_by_origin: dict = {}
        for rule in ordered:
            line = self._format_rule(rule)
            if not line:
                continue
            origin = rule.origin
            if origin is not None and seen_by_origin.get(origin) == line:
                continue
            if origin is not None:
                seen_by_origin[origin] = line
            lines.append(line)
        return lines

    def export_flat(self, cell_rows: List[List[str]]) -> List[str]:
        # No header info available on gate failure — fall back to pipe join.
        return [" | ".join(row) for row in cell_rows if any(row)]

    @staticmethod
    def _format_rule(rule: LogicRule) -> str:
        value = rule.outcome.strip()
        if not value:
            return ""
        row_path = PATH_SEP.join(h.strip() for h in rule.row_headers if h.strip())
        col_path = PATH_SEP.join(h.strip() for h in rule.col_headers if h.strip())

        if row_path and col_path:
            return f"{row_path}{ROW_COL_SEP}{col_path}: {value}"
        if col_path:
            return f"{col_path}: {value}"
        if row_path:
            return f"{row_path}: {value}"
        return value
