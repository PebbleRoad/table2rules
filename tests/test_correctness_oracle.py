"""Correctness layer — structural-accuracy check against external oracles.

For every real-world fixture under tests/realworld/<dataset>/ that has a
paired `.oracle.json`:
  1. Run `process_tables_to_text` on the HTML.
  2. Classify the output tier:
       - RULES:  every non-empty line is a rule-shaped line ('... : value')
       - FLAT:   pipe-joined cell rows with no ': '  (gate failed)
       - PASSTHROUGH: contains '<table' (parser bailed entirely)
  3. If RULES: parse each line back into a (row_path, col_path, value)
     triple and compare to the oracle set using value-aware header
     subset matching.

Pass criterion (strict correctness): for every emitted rule, the header
tokens emitted must be a superset of the oracle's required tokens for
that value, with any extras limited to real source cells. An emitted rule
that contradicts the oracle = a misattribution bug in table2rules.

FLAT and PASSTHROUGH cases are recorded as skips — those are safe
fallbacks, not correctness failures. See tests/README.md for how this
layer relates to the regression-gold and mutation-robustness tests.

Run:    pytest tests/test_correctness_oracle.py -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pytest

from table2rules import process_tables_to_text
from table2rules.exporters.rules import PATH_SEP, ROW_COL_SEP

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


ROOT = Path(__file__).resolve().parent.parent
REALWORLD_DIR = ROOT / "tests" / "realworld"


def _discover() -> list[tuple[Path, Path]]:
    cases = []
    for md in sorted(REALWORLD_DIR.rglob("*.md")):
        oracle = md.with_suffix("").with_suffix(".oracle.json")
        # md files have suffix .md — with_suffix("").with_suffix(".oracle.json")
        # collapses "foo.md" -> "foo" -> "foo.oracle.json"
        if oracle.exists():
            cases.append((md, oracle))
    return cases


def _case_id(case: tuple[Path, Path]) -> str:
    return str(case[0].relative_to(REALWORLD_DIR))


def _smart_split(path_str: str, source_tokens: frozenset[str]) -> tuple[str, ...]:
    """Split on PATH_SEP but rejoin adjacent pieces whose join is a real source
    token. Handles the case where a cell's own text contains ' > '.
    """
    pieces = [_norm(p) for p in path_str.split(PATH_SEP) if p.strip()]
    if not pieces:
        return ()
    # Greedy rejoin: scan left-to-right and merge adjacent pairs whose
    # ' > '-joined form is a source token.
    merged: list[str] = []
    i = 0
    while i < len(pieces):
        if i + 1 < len(pieces):
            joined = pieces[i] + PATH_SEP + pieces[i + 1]
            if joined in source_tokens and pieces[i] not in source_tokens:
                merged.append(joined)
                i += 2
                continue
        merged.append(pieces[i])
        i += 1
    return tuple(merged)


def _smart_value_split(line: str, source_tokens: frozenset[str]) -> tuple[str, str] | None:
    """Split 'lhs: value' where the cell content itself may contain ': '.

    Prefer the leftmost ': ' whose value-side is a known source token —
    that yields the longest matching value, which is the correct choice
    when the cell text itself contains ': ' (e.g., a composite datum like
    "u: 2,853a: 690d: 231m: 14s: 167"). Picking the rightmost match first
    would silently shorten such values to the last colon-delimited
    fragment (e.g., just "167"), misattributing the rest of the cell text
    to the header path.

    Fall back to the rightmost ': ' if no left-to-right split produces a
    source-token value — that preserves behaviour for normal rules.
    """
    if ": " not in line:
        return None
    positions = [i for i in range(len(line) - 1) if line[i : i + 2] == ": "]
    # Leftmost-first: the first source-token match yields the longest value.
    for pos in positions:
        lhs = line[:pos]
        value = line[pos + 2 :].strip()
        if not value:
            continue
        if ROW_COL_SEP in value or value.startswith("|"):
            continue
        value_n = _norm(value)
        if source_tokens and value_n in source_tokens:
            return lhs, value_n
    # No left-to-right match — fall back to rightmost ': '.
    lhs, _, value = line.rpartition(": ")
    value = value.strip()
    if not value or ROW_COL_SEP in value or value.startswith("|"):
        return None
    return lhs, _norm(value)


def _parse_rule_line(
    line: str, source_tokens: frozenset[str] = frozenset()
) -> tuple[tuple[str, ...], tuple[str, ...], str] | None:
    """Return (row_path, col_path, value) or None if the line isn't a rule."""
    split = _smart_value_split(line, source_tokens)
    if split is None:
        return None
    lhs, value = split
    if ROW_COL_SEP in lhs:
        row_str, _, col_str = lhs.partition(ROW_COL_SEP)
        row_path = _smart_split(row_str, source_tokens)
        col_path = _smart_split(col_str, source_tokens)
    else:
        row_path = _smart_split(lhs, source_tokens)
        col_path = ()
    return row_path, col_path, value


def _classify(output: str) -> str:
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines:
        return "EMPTY"
    if any("<table" in l for l in lines):
        return "PASSTHROUGH"
    rule_shaped = sum(1 for l in lines if _parse_rule_line(l) is not None)
    if rule_shaped == len(lines):
        return "RULES"
    if rule_shaped == 0:
        return "FLAT"
    return "MIXED"


def _tokens(paths: Iterable[Iterable[str]]) -> frozenset[str]:
    return frozenset(t for path in paths for t in path)


@pytest.mark.parametrize("case", _discover(), ids=[_case_id(c) for c in _discover()])
def test_correctness_oracle(case: tuple[Path, Path]) -> None:
    md_path, oracle_path = case
    html = md_path.read_text(encoding="utf-8")
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))

    # Side-aware oracle: keep row-tokens and col-tokens separate so that
    # "parser put a column header into row_path" is caught.
    oracle_by_value: dict[str, list[tuple[frozenset[str], frozenset[str]]]] = {}
    for t in oracle["triples"]:
        key = _norm(t["value"])
        row_toks = frozenset(_norm(x) for x in t["row"])
        col_toks = frozenset(_norm(x) for x in t["col"])
        oracle_by_value.setdefault(key, []).append((row_toks, col_toks))

    # Source corpus: the set of tokens that actually appear in the source
    # table (header cells + data cells). Parser is allowed to include tokens
    # that aren't in the strict oracle path, as long as they genuinely came
    # from the source — this tolerates legitimate context propagation
    # (e.g., a non-stub identifier column being pulled into row_path)
    # without tolerating invented or concatenated tokens.
    source_tokens = frozenset(_norm(x) for x in oracle.get("source_tokens", []))

    output = process_tables_to_text(html)
    tier = _classify(output)
    if tier in {"PASSTHROUGH", "FLAT", "EMPTY", "MIXED"}:
        pytest.skip(f"tier={tier} — parser did not emit pure rules")

    wrong: list[str] = []
    matched = 0
    emitted_lines = [l for l in output.splitlines() if l.strip()]
    for line in emitted_lines:
        parsed = _parse_rule_line(line, source_tokens)
        if parsed is None:
            continue
        row_path, col_path, value = parsed
        emitted_row = frozenset(row_path)
        emitted_col = frozenset(col_path)
        candidates = oracle_by_value.get(value, [])

        # A match: some oracle candidate's row tokens are all in emitted row,
        # AND col tokens are all in emitted col (side-aware), AND every extra
        # emitted token genuinely comes from the source table.
        # Exception: when the emitted line has no '|' separator (single-path
        # output), side assignment is ambiguous — the exporter collapses
        # 'row | col: value' to 'path: value' whenever one side is empty.
        # In that case fall back to union matching.
        ambiguous_side = not emitted_col  # single-path shape stuffs into row
        emitted_union = emitted_row | emitted_col

        def is_match(cand: tuple[frozenset[str], frozenset[str]]) -> bool:
            o_row, o_col = cand
            o_union = o_row | o_col
            if ambiguous_side:
                if not o_union.issubset(emitted_union):
                    return False
                extras = emitted_union - o_union
            else:
                if not o_row.issubset(emitted_row):
                    return False
                if not o_col.issubset(emitted_col):
                    return False
                extras = emitted_union - o_union
            return extras.issubset(source_tokens)

        if any(is_match(c) for c in candidates):
            matched += 1
        else:
            # Diagnostic: find closest candidate to explain the miss
            if candidates:
                o_row, o_col = min(
                    candidates,
                    key=lambda c: len(emitted_row ^ c[0]) + len(emitted_col ^ c[1]),
                )
                row_missing = sorted(o_row - emitted_row)
                col_missing = sorted(o_col - emitted_col)
                extras = (emitted_row | emitted_col) - (o_row | o_col)
                invented = sorted(extras - source_tokens)
                wrong.append(
                    f"  value={value!r}\n"
                    f"    emitted row={sorted(emitted_row)} col={sorted(emitted_col)}\n"
                    f"    oracle  row={sorted(o_row)} col={sorted(o_col)}\n"
                    f"    row_missing={row_missing} col_missing={col_missing} invented={invented}"
                )
            else:
                wrong.append(
                    f"  value={value!r} — value not in oracle\n"
                    f"    emitted row={sorted(emitted_row)} col={sorted(emitted_col)}"
                )

    assert not wrong, (
        f"\nMisattribution in {_case_id(case)} "
        f"({matched} matched, {len(wrong)} wrong of {len(emitted_lines)} emitted):\n"
        + "\n".join(wrong[:8])
        + (f"\n  ... +{len(wrong) - 8} more" if len(wrong) > 8 else "")
    )
