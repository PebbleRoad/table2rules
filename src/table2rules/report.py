"""Per-table observability types returned by ``process_tables_with_stats``.

Downstream integrators use these to answer "did this table convert cleanly,
and if not, why?" without having to re-parse the output or sample by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import chain
from typing import Dict, FrozenSet, Iterable, Literal, Optional, Tuple

# The four values ``render_mode`` can take. Order = descending output quality.
#
#   rules       — gate passed; exporter-native output (one rule per line).
#   flat        — gate failed; header-free pipe-joined cell rows.
#   passthrough — neither rules nor flat produced anything; raw HTML emitted.
#   skipped     — input was refused before fallback output (currently too large).
#
# Adding new values is a minor-version bump; renaming/removing is breaking.
RenderMode = Literal["rules", "flat", "passthrough", "skipped"]

# Symbolic constants for integrators who'd rather not sprinkle magic strings
# through policy code. ``t.render_mode == RENDER_MODE_RULES`` is equivalent to
# ``t.render_mode == "rules"``; use whichever reads better at the call site.
RENDER_MODE_RULES: RenderMode = "rules"
RENDER_MODE_FLAT: RenderMode = "flat"
RENDER_MODE_PASSTHROUGH: RenderMode = "passthrough"
RENDER_MODE_SKIPPED: RenderMode = "skipped"


# Stable catalogue of every ``reasons`` string a ``TableReport`` may contain.
# This is part of the semver contract: additions are minor-version bumps;
# renames or removals are breaking. Integrators who switch on ``reasons`` can
# lint against ``REASONS.keys()`` to catch typos.
REASONS: Dict[str, str] = {
    # --- Gate invariants (structural) ---
    "empty_grid": "Parsed grid was empty or zero-dimensional.",
    "position_out_of_bounds": "A generated rule's position fell outside the grid bounds.",
    "non_td_rule_cell": "A rule was generated from a non-<td> cell.",
    "header_cell_emitted": "A rule was generated from a cell flagged as a header.",
    "empty_rule_outcome": "A rule's outcome text was empty.",
    "empty_header_text": "A rule had at least one header with empty text.",
    # --- Gate confidence (statistical) ---
    "no_candidate_data_cells": "The table had no non-empty data cells.",
    "low_coverage": "Fewer than 60% of data cells produced a rule.",
    "low_header_attachment": "At least one rule lacked any header context; rules mode requires every rule to carry at least one header.",
    "high_self_echo": "More than 50% of rules repeat a column header as their value.",
    "high_duplicate_positions": "At least one logical grid position produced multiple rules.",
    "high_position_conflict": "At least one logical grid position carried conflicting outcomes.",
    "numeric_column_headers": "More than 30% of rules have all-numeric column headers — likely a data row misread as a header.",
    "placeholder_column_headers": "More than 30% of rules have placeholder-only column headers (underscores, dashes).",
    "partial_column_coverage": "The table has column headers for some rules but not for others — the header rows do not fully cover all data columns. Common cause: a multi-level header that does not reserve a column for the row-label, shifting all column labels one position to the right.",
    # --- Report-level signals ---
    "input_too_large": "Expanded grid exceeded the safety cap; the table was skipped.",
    "processing_error": "The parser raised an exception and ``strict=False`` swallowed it; see ``TableReport.error``.",
}


# Operational severity grouping for the codes in ``REASONS``.
#
#   defensive  — structural invariants on the library's own output. Should
#                never fire in production; if you see one, file an issue.
#   confidence — soft gate signals for low-quality parses. Expected on
#                real-world input; tune alerting against these.
#   input      — signals that the caller handed table2rules bad data. The
#                fix is upstream, not in this library.
#
# Exposing this grouping lets integrators auto-populate metrics dashboards
# and switch statements without hardcoding the buckets from the docs. Every
# key in ``REASONS`` appears in exactly one bucket — enforced by tests.
REASONS_BY_SEVERITY: Dict[str, FrozenSet[str]] = {
    "defensive": frozenset(
        {
            "empty_grid",
            "position_out_of_bounds",
            "non_td_rule_cell",
            "header_cell_emitted",
            "empty_rule_outcome",
            "empty_header_text",
        }
    ),
    "confidence": frozenset(
        {
            "no_candidate_data_cells",
            "low_coverage",
            "low_header_attachment",
            "high_self_echo",
            "high_duplicate_positions",
            "high_position_conflict",
            "numeric_column_headers",
            "placeholder_column_headers",
            "partial_column_coverage",
        }
    ),
    "input": frozenset(
        {
            "input_too_large",
            "processing_error",
        }
    ),
}


@dataclass(frozen=True)
class TableReport:
    """Observability record for a single top-level table in the input HTML.

    ``text`` carries the rendered output for *this* table only — the same lines
    that contributed to the concatenated string returned alongside the report.
    Callers passing whole-document HTML in can read ``report.tables[i].text``
    to keep per-table provenance instead of having to split the flat blob.

    ``caption`` is the text of the table's ``<caption>`` element when present,
    otherwise ``None``. Only direct ``<caption>`` children are read; the HTML
    ``id`` attribute, surrounding headings, and other content-derived names
    are intentionally ignored — ``table_index`` remains the only stable
    positional identifier.
    """

    table_index: int
    render_mode: RenderMode
    gate_ok: bool
    gate_score: float
    reasons: Tuple[str, ...]
    error: Optional[str] = None
    caption: Optional[str] = None
    text: str = ""


@dataclass(frozen=True)
class RenderReport:
    """Aggregate of per-table reports for a single ``process_tables_*`` call."""

    tables: Tuple[TableReport, ...] = ()

    @property
    def tables_rendered(self) -> int:
        """Count of tables whose output reached the final string in any mode."""
        return sum(1 for t in self.tables if t.render_mode != "skipped")

    @property
    def tables_flagged(self) -> int:
        """Count of tables that did NOT produce clean rules output."""
        return sum(1 for t in self.tables if t.render_mode != "rules")

    @classmethod
    def merge(cls, reports: Iterable["RenderReport"]) -> "RenderReport":
        """Concatenate multiple reports (e.g. from a batch of documents).

        Per-report ``table_index`` values are preserved as-is — they refer to
        positions within each original call. If you need cross-call identity,
        track it alongside the reports yourself.
        """
        return cls(tables=tuple(chain.from_iterable(r.tables for r in reports)))
