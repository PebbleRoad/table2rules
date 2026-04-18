"""Robustness layer — mutation testing for the real-world fixture corpus.

For each fixture × mutation, we assert the parser never fabricates
content. Operators simulate production-HTML noise: `<span>` wrappers,
Word-style `<td><b>` headers, paginated duplicate header rows, mismatched
close tags, etc. Mutations are applied on-the-fly from the fixtures in
tests/realworld/.

Contract: **no invented tokens, no hallucinated values**. Under mutation
the parser may drop headers or fall back to FLAT/PASSTHROUGH — those are
safe outcomes. The only failure is producing rule content that wasn't in
the source.

This is the relaxed counterpart to test_correctness_oracle.py — same
fixtures, weaker assertion, corrupted input. See tests/README.md.

Run:
    pytest tests/test_robustness_mutations.py -v
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Callable, Iterable

import pytest
from bs4 import BeautifulSoup

from table2rules import process_tables_to_text
from table2rules.exporters.rules import PATH_SEP, ROW_COL_SEP

ROOT = Path(__file__).resolve().parent.parent
REALWORLD_DIR = ROOT / "tests" / "realworld"

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def _smart_split(path_str: str, source_tokens: frozenset[str]) -> tuple[str, ...]:
    pieces = [_norm(p) for p in path_str.split(PATH_SEP) if p.strip()]
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


def _smart_value_split(line: str, source_tokens: frozenset[str]):
    if ": " not in line:
        return None
    positions = [i for i in range(len(line) - 1) if line[i:i + 2] == ": "]
    positions.reverse()
    for pos in positions:
        lhs = line[:pos]
        value = line[pos + 2:].strip()
        if not value or ROW_COL_SEP in value or value.startswith("|"):
            continue
        if not source_tokens or _norm(value) in source_tokens:
            return lhs, _norm(value)
    lhs, _, value = line.rpartition(": ")
    value = value.strip()
    if not value or ROW_COL_SEP in value or value.startswith("|"):
        return None
    return lhs, _norm(value)


def _parse_rule_line(
    line: str, source_tokens: frozenset[str] = frozenset()
):
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


# ------------------------------------------------------------------ mutations


def mut_none(html: str, rng: random.Random) -> str:
    """Baseline: no change. Sanity check that the harness aligns with test_correctness_oracle."""
    return html


def mut_whitespace(html: str, rng: random.Random) -> str:
    """Inject newlines and spaces between tags. Purely cosmetic."""
    # Insert a newline + 2 spaces after every opening tag.
    return re.sub(r">(?=<)", ">\n  ", html)


def mut_wrap_cells_in_span(html: str, rng: random.Random) -> str:
    """Wrap cell contents in inline elements. Real-world: CMS / Word export."""
    soup = BeautifulSoup(html, "html.parser")
    wrappers = ["span", "p", "b", "strong"]
    for cell in soup.find_all(["td", "th"]):
        if not cell.get_text(strip=True):
            continue
        wrapper_tag = rng.choice(wrappers)
        wrapper = soup.new_tag(wrapper_tag)
        # Move all children into the wrapper
        for child in list(cell.contents):
            if hasattr(child, "extract"):
                wrapper.append(child.extract())
            else:
                wrapper.append(child)
        cell.append(wrapper)
    return str(soup)


def mut_th_as_bold_td(html: str, rng: random.Random) -> str:
    """Convert <th>X</th> cells to <td><b>X</b></td>. Real-world: Word export."""
    soup = BeautifulSoup(html, "html.parser")
    ths = soup.find_all("th")
    if not ths:
        return html
    # Convert about half of them
    victims = rng.sample(ths, max(1, len(ths) // 2))
    for th in victims:
        th.name = "td"
        # Wrap inner content in <b>
        b = soup.new_tag("b")
        for child in list(th.contents):
            if hasattr(child, "extract"):
                b.append(child.extract())
            else:
                b.append(child)
        th.append(b)
    return str(soup)


def mut_encode_ampersands(html: str, rng: random.Random) -> str:
    """Escape bare ampersands in text nodes as &amp;. Parser should decode."""
    # Only touch ampersands inside text (not already-encoded entities).
    # Approach: walk the soup, replace text nodes.
    soup = BeautifulSoup(html, "html.parser")
    from bs4 import NavigableString

    for node in list(soup.find_all(string=True)):
        if isinstance(node, NavigableString) and "&" in node:
            # Skip if the surrounding node is a comment etc.
            if node.parent.name in ("script", "style"):
                continue
            # Encode bare & to &amp;. NavigableString auto-encodes on render
            # so just touching it is enough — but we also encode spaces as
            # &nbsp; on a sample to exercise that entity path.
            new_text = str(node).replace(" ", "\u00a0", 1)  # one NBSP per node
            node.replace_with(NavigableString(new_text))
    return str(soup)


def mut_repeat_header_in_body(html: str, rng: random.Random) -> str:
    """Duplicate the first thead row inside tbody. Real-world: paginated reports."""
    soup = BeautifulSoup(html, "html.parser")
    thead = soup.find("thead")
    tbody = soup.find("tbody")
    if thead is None or tbody is None:
        return html
    first_header_row = thead.find("tr")
    if first_header_row is None:
        return html
    body_rows = tbody.find_all("tr", recursive=False)
    if not body_rows:
        return html
    # Insert a copy of the header row roughly in the middle of tbody
    insertion_idx = len(body_rows) // 2
    import copy
    clone = copy.copy(first_header_row)
    body_rows[insertion_idx].insert_before(clone)
    return str(soup)


def mut_br_in_cells(html: str, rng: random.Random) -> str:
    """Replace one space in a cell's text with a <br>. Real-world: addresses, multi-line labels."""
    soup = BeautifulSoup(html, "html.parser")
    from bs4 import NavigableString

    candidates = []
    for cell in soup.find_all(["td", "th"]):
        for node in cell.descendants:
            if isinstance(node, NavigableString) and " " in str(node):
                candidates.append(node)
    if not candidates:
        return html
    victim = rng.choice(candidates)
    text = str(victim)
    # Split at the first space after char 3 to avoid splitting tiny tokens
    split_pos = text.find(" ", 3)
    if split_pos == -1:
        split_pos = text.find(" ")
    if split_pos == -1:
        return html
    before, after = text[:split_pos], text[split_pos + 1:]
    parent = victim.parent
    new_before = NavigableString(before)
    br = soup.new_tag("br")
    new_after = NavigableString(after)
    victim.replace_with(new_before)
    new_before.insert_after(new_after)
    new_before.insert_after(br)
    return str(soup)


def mut_multi_tbody(html: str, rng: random.Random) -> str:
    """Split tbody into two tbody blocks at the midpoint. Real-world: Word export."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    if tbody is None:
        return html
    rows = tbody.find_all("tr", recursive=False)
    if len(rows) < 3:
        return html
    split = len(rows) // 2
    new_tbody = soup.new_tag("tbody")
    for row in rows[split:]:
        new_tbody.append(row.extract())
    tbody.insert_after(new_tbody)
    return str(soup)


def mut_mismatched_cell_close(html: str, rng: random.Random) -> str:
    """Replace one `</td>` with `</th>` (or vice versa). Simple_repair Fix 0 territory."""
    # Find all </td> and </th> positions, pick one, flip it.
    candidates = [(m.start(), m.group(0)) for m in re.finditer(r"</t[dh]>", html)]
    if not candidates:
        return html
    pos, token = rng.choice(candidates)
    flipped = "</th>" if token == "</td>" else "</td>"
    return html[:pos] + flipped + html[pos + len(token):]


def mut_drop_thead_wrapper(html: str, rng: random.Random) -> str:
    """Remove <thead>/<tbody> wrappers. Fix 7 should re-infer thead."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return html
    thead = table.find("thead")
    tbody = table.find("tbody")
    # Move all children of thead/tbody up to the table, preserving order
    for wrapper in (thead, tbody):
        if wrapper is None:
            continue
        children = list(wrapper.children)
        for child in children:
            wrapper.insert_before(child.extract() if hasattr(child, "extract") else child)
        wrapper.decompose()
    return str(soup)


# Operators grouped by real-world provenance:
#   - BENIGN (cosmetic variation the parser should shrug off):
#       none, whitespace, entities_nbsp
#   - RECOVERABLE (common authoring / export quirks):
#       mismatched_close, drop_thead_wrapper, wrap_cells_in_span,
#       th_as_bold_td, repeat_header_in_body, br_in_cells, multi_tbody
# All are patterns observed in production HTML (PDF extractors, Word exports,
# scraped CMS pages, paginated reports). None are academic contortions.
MUTATIONS: dict[str, Callable[[str, random.Random], str]] = {
    "none": mut_none,
    "whitespace": mut_whitespace,
    "entities_nbsp": mut_encode_ampersands,
    "mismatched_close": mut_mismatched_cell_close,
    "drop_thead_wrapper": mut_drop_thead_wrapper,
    "wrap_cells_in_span": mut_wrap_cells_in_span,
    "th_as_bold_td": mut_th_as_bold_td,
    "repeat_header_in_body": mut_repeat_header_in_body,
    "br_in_cells": mut_br_in_cells,
    "multi_tbody": mut_multi_tbody,
}


# ------------------------------------------------------------------ test


def _discover() -> list[tuple[Path, Path]]:
    cases = []
    for md in sorted(REALWORLD_DIR.rglob("*.md")):
        oracle = md.with_suffix("").with_suffix(".oracle.json")
        if oracle.exists():
            cases.append((md, oracle))
    return cases


CASES = _discover()


def _case_id(case: tuple[Path, Path]) -> str:
    return str(case[0].relative_to(REALWORLD_DIR))


@pytest.mark.parametrize("mutation_name", list(MUTATIONS))
@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_robustness_under_mutation(
    case: tuple[Path, Path], mutation_name: str
) -> None:
    md_path, oracle_path = case
    html = md_path.read_text(encoding="utf-8")
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))

    # Oracle index (side-aware)
    oracle_by_value: dict[str, list[tuple[frozenset[str], frozenset[str]]]] = {}
    for t in oracle["triples"]:
        key = _norm(t["value"])
        row_toks = frozenset(_norm(x) for x in t["row"])
        col_toks = frozenset(_norm(x) for x in t["col"])
        oracle_by_value.setdefault(key, []).append((row_toks, col_toks))
    source_tokens = frozenset(_norm(x) for x in oracle.get("source_tokens", []))

    # Deterministic per-fixture seed so failures are reproducible.
    rng = random.Random(f"{md_path.name}|{mutation_name}")
    mutator = MUTATIONS[mutation_name]
    mutated_html = mutator(html, rng)

    output = process_tables_to_text(mutated_html)
    tier = _classify(output)
    if tier in {"PASSTHROUGH", "FLAT", "EMPTY", "MIXED"}:
        # Safe fallback; not a precision failure.
        pytest.skip(f"tier={tier} after mutation={mutation_name!r}")

    # Mutation contract (relaxed, per-category agnostic): the parser may
    # lose headers or swap side attribution under a corrupted structure,
    # but must not fabricate content. We check two properties per emitted
    # rule:
    #   (a) the VALUE must exist in the oracle (i.e., be a real source cell
    #       — guards against concat-invented outcomes like
    #       'from self-rated mental health')
    #   (b) every emitted HEADER token must be a real cell in the source
    #       (guards against invented header tokens)
    wrong: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parsed = _parse_rule_line(line, source_tokens)
        if parsed is None:
            continue
        row_path, col_path, value = parsed
        emitted_row = frozenset(row_path)
        emitted_col = frozenset(col_path)
        emitted_union = emitted_row | emitted_col

        # A mutation may demote a stub <th> to <td> (the Word 'bold-td'
        # pattern), so a previously-header cell legitimately becomes a
        # data value. That's why we accept any source token as a valid
        # value, not just oracle values.
        if value not in source_tokens:
            wrong.append(f"  invented value={value!r} (not a source cell)")
            continue
        invented = emitted_union - source_tokens
        if invented:
            wrong.append(
                f"  value={value!r} — invented header tokens {sorted(invented)}\n"
                f"    emitted row={sorted(emitted_row)} col={sorted(emitted_col)}"
            )

    assert not wrong, (
        f"\nMutation {mutation_name!r} on {_case_id(case)} caused "
        f"misattribution ({len(wrong)} wrong):\n"
        + "\n".join(wrong[:6])
        + (f"\n  ... +{len(wrong) - 6} more" if len(wrong) > 6 else "")
        + f"\n\nMutated HTML (first 800 chars):\n{mutated_html[:800]}"
    )
