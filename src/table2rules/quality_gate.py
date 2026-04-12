from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import LogicRule


@dataclass
class GateResult:
    ok: bool
    score: float
    reasons: List[str]


def _candidate_data_positions(grid: List[List[Dict]]) -> List[Tuple[int, int]]:
    positions: List[Tuple[int, int]] = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if not cell:
                continue
            if cell.get("type") != "td":
                continue
            if cell.get("is_thead", False) or cell.get("is_header_row", False):
                continue
            if not str(cell.get("text", "")).strip():
                continue
            positions.append((r, c))
    return positions


def check_invariants(grid: List[List[Dict]], rules: List[LogicRule]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if not grid or not grid[0]:
        reasons.append("empty_grid")
        return False, reasons

    rows = len(grid)
    cols = len(grid[0])

    for rule in rules:
        r, c = rule.position
        if not (0 <= r < rows and 0 <= c < cols):
            reasons.append("position_out_of_bounds")
            continue

        cell = grid[r][c]
        if cell.get("type") != "td":
            reasons.append("non_td_rule_cell")
        if cell.get("is_thead", False) or cell.get("is_header_row", False):
            reasons.append("header_cell_emitted")

        rule_outcome = (rule.outcome or "").strip()
        if not rule_outcome:
            reasons.append("empty_rule_outcome")

        if any(not h.strip() for h in (rule.row_headers + rule.col_headers)):
            reasons.append("empty_header_text")

    return len(reasons) == 0, sorted(set(reasons))


def assess_confidence(grid: List[List[Dict]], rules: List[LogicRule]) -> GateResult:
    """
    Conservative fail-open gate:
    - Hard-fail on invariant violations.
    - Soft score combines data coverage and header attachment.
    """
    ok, inv_reasons = check_invariants(grid, rules)
    if not ok:
        return GateResult(ok=False, score=0.0, reasons=inv_reasons)

    candidates = _candidate_data_positions(grid)
    if not candidates:
        return GateResult(ok=False, score=0.0, reasons=["no_candidate_data_cells"])

    rule_positions = {rule.position for rule in rules}
    coverage = len(rule_positions) / max(1, len(candidates))

    with_headers = sum(1 for rule in rules if rule.row_headers or rule.col_headers)
    header_ratio = with_headers / max(1, len(rules))

    # Penalize duplicate positions and conflicting outcomes at the same position.
    pos_outcomes: Dict[Tuple[int, int], set] = {}
    for rule in rules:
        pos_outcomes.setdefault(rule.position, set()).add(rule.outcome.strip())
    unique_positions = len(pos_outcomes)
    duplicate_ratio = (len(rules) - unique_positions) / max(1, len(rules))
    conflicting_positions = sum(1 for values in pos_outcomes.values() if len(values) > 1)
    conflict_ratio = conflicting_positions / max(1, unique_positions)

    # Penalize noisy self-echo headers (header identical to value)
    self_echo = 0
    for rule in rules:
        outcome = rule.outcome.strip().lower()
        headers = [h.strip().lower() for h in (rule.row_headers + rule.col_headers)]
        if outcome and outcome in headers:
            self_echo += 1
    echo_ratio = self_echo / max(1, len(rules))

    score = (
        (0.45 * coverage)
        + (0.30 * header_ratio)
        + (0.10 * (1.0 - echo_ratio))
        + (0.10 * (1.0 - duplicate_ratio))
        + (0.05 * (1.0 - conflict_ratio))
    )

    reasons: List[str] = []
    if coverage < 0.60:
        reasons.append("low_coverage")
    if len(rules) >= 4 and header_ratio < 0.25:
        reasons.append("low_header_attachment")
    if echo_ratio > 0.50:
        reasons.append("high_self_echo")
    if duplicate_ratio > 0.40:
        reasons.append("high_duplicate_positions")
    if conflict_ratio > 0.15:
        reasons.append("high_position_conflict")

    # Keep threshold modest so we only fail on clearly weak parses.
    gate_ok = score >= 0.45 and not reasons
    return GateResult(ok=gate_ok, score=score, reasons=reasons)
