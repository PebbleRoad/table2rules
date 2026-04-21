"""Per-table observability types returned by ``process_tables_with_stats``.

Downstream integrators use these to answer "did this table convert cleanly,
and if not, why?" without having to re-parse the output or sample by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import chain
from typing import Dict, Iterable, Literal, Optional, Tuple


# The four values ``render_mode`` can take. Order = descending output quality.
#
#   rules       — gate passed; exporter-native output (one rule per line).
#   flat        — gate failed; header-free pipe-joined cell rows.
#   passthrough — neither rules nor flat produced anything; raw HTML emitted.
#   skipped     — input was refused (too large, or raised under strict=False).
#
# Adding new values is a minor-version bump; renaming/removing is breaking.
RenderMode = Literal["rules", "flat", "passthrough", "skipped"]


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
    "low_header_attachment": "Fewer than 25% of rules carry any header context.",
    "high_self_echo": "More than 50% of rules repeat a column header as their value.",
    "high_duplicate_positions": "More than 40% of rules share a position with another rule.",
    "high_position_conflict": "More than 15% of positions carry conflicting outcomes.",
    "numeric_column_headers": "More than 30% of rules have all-numeric column headers — likely a data row misread as a header.",
    "placeholder_column_headers": "More than 30% of rules have placeholder-only column headers (underscores, dashes).",
    # --- Report-level signals ---
    "input_too_large": "Expanded grid exceeded the safety cap; the table was skipped.",
    "processing_error": "The parser raised an exception and ``strict=False`` swallowed it; see ``TableReport.error``.",
}


@dataclass(frozen=True)
class TableReport:
    """Observability record for a single top-level table in the input HTML."""

    table_index: int
    render_mode: RenderMode
    gate_ok: bool
    gate_score: float
    reasons: Tuple[str, ...]
    error: Optional[str] = None


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
