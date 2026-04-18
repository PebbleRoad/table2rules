"""PubTabNet fixture generator.

Streams the `apoidea/pubtabnet-html` dataset (CDLA-Permissive-1.0,
MIT-compatible) from HuggingFace. For each table, emits:

  tests/realworld/pubtabnet/<id>.md          — the table's HTML
  tests/realworld/pubtabnet/<id>.oracle.json — (row_path, col_path, value)
                                              triples computed independently
                                              from the HTML structure

The oracle is extracted from the HTML with our own BS4-based merge-aware
grid walker — it must NOT call table2rules, otherwise the test becomes
circular.

Run:
    python scripts/build_pubtabnet_fixtures.py
"""

from __future__ import annotations

import json
import os
import re
from html import escape
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup, NavigableString, Tag

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "tests" / "realworld" / "pubtabnet"

TARGET_N = int(os.environ.get("N_PUBTABNET", "200"))
SCAN_LIMIT = int(os.environ.get("SCAN_LIMIT", "5000"))  # examples to stream


# ------------------------------------------------------------------ extraction


_WS = re.compile(r"\s+")


def _text_of(node: Tag | NavigableString) -> str:
    """Normalize whitespace inside a cell."""
    if isinstance(node, NavigableString):
        return _WS.sub(" ", str(node)).strip()
    return _WS.sub(" ", node.get_text()).strip()


def _extract_table(html_doc: str) -> Tag | None:
    soup = BeautifulSoup(html_doc, "html.parser")
    return soup.find("table")


def _build_grid(table: Tag) -> tuple[list[list[dict]], int]:
    """Return (grid, thead_rows_count).

    Each grid cell: {"text": str, "origin": (r, c), "rowspan": int,
    "colspan": int, "in_thead": bool}. Span children point back to
    origin for merge-aware walking.
    """
    rows = [
        r for r in table.find_all("tr")
        if r.find_parent("table") is table
    ]

    # Compute thead row count — PubTabNet always has explicit <thead>.
    thead = table.find("thead")
    thead_rows: list[Tag] = []
    if thead is not None:
        thead_rows = [
            r for r in thead.find_all("tr")
            if r.find_parent("thead") is thead
        ]
    thead_count = len(thead_rows)

    # Compute dimensions via occupancy map.
    occupied: dict[tuple[int, int], bool] = {}
    max_cols = 0
    for r_idx, row in enumerate(rows):
        cells = [
            c for c in row.find_all(["td", "th"])
            if c.find_parent("tr") is row
        ]
        col = 0
        for cell in cells:
            while (r_idx, col) in occupied:
                col += 1
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(r_idx + dr, col + dc)] = True
            col += cs
        max_cols = max(max_cols, col)

    n_rows = len(rows)
    grid: list[list[dict]] = [
        [{"text": "", "origin": (r, c), "rowspan": 1, "colspan": 1, "in_thead": False}
         for c in range(max_cols)] for r in range(n_rows)
    ]

    # Fill cells.
    for r_idx, row in enumerate(rows):
        in_thead = row.find_parent("thead") is not None
        cells = [
            c for c in row.find_all(["td", "th"])
            if c.find_parent("tr") is row
        ]
        col = 0
        for cell in cells:
            while col < max_cols and grid[r_idx][col].get("_filled"):
                col += 1
            if col >= max_cols:
                break
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            text = _text_of(cell)
            for dr in range(rs):
                for dc in range(cs):
                    tr, tc = r_idx + dr, col + dc
                    if tr < n_rows and tc < max_cols:
                        grid[tr][tc] = {
                            "text": text,
                            "origin": (r_idx, col),
                            "rowspan": rs,
                            "colspan": cs,
                            "in_thead": in_thead,
                            "_filled": True,
                        }
            col += cs

    return grid, thead_count


def _col_path_for(grid: list[list[dict]], r: int, c: int, thead_rows: int) -> list[str]:
    """Walk UP from (r, c) through thead rows, collecting header texts with
    merge origin dedup."""
    path: list[str] = []
    seen: set[tuple[int, int]] = set()
    for rr in range(min(r, thead_rows) - 1, -1, -1):
        cell = grid[rr][c]
        if not cell.get("in_thead"):
            continue
        origin = cell["origin"]
        if origin in seen:
            continue
        seen.add(origin)
        text = cell["text"].strip()
        if text:
            path.append(text)
    path.reverse()
    # Dedupe consecutive duplicates
    out: list[str] = []
    for t in path:
        if out and out[-1] == t:
            continue
        out.append(t)
    return out


def _row_path_for(grid: list[list[dict]], r: int, c: int, stub_cols: int) -> list[str]:
    """Collect row-stub text (first `stub_cols` columns) with merge dedup."""
    path: list[str] = []
    seen: set[tuple[int, int]] = set()
    for cc in range(min(c, stub_cols)):
        cell = grid[r][cc]
        origin = cell["origin"]
        if origin in seen:
            continue
        seen.add(origin)
        text = cell["text"].strip()
        if text:
            path.append(text)
    # Dedupe consecutive
    out: list[str] = []
    for t in path:
        if out and out[-1] == t:
            continue
        out.append(t)
    return out


def _looks_like_stub_col(grid: list[list[dict]], thead_rows: int, col: int) -> bool:
    """Detect col 0 as a row-stub, matching table2rules' structural criteria.

    The parser only promotes leading body columns to row headers when the
    thead is multi-row (>=2 rows) — that's the signal of a dimensional
    table. For single-row-thead tables, col 0 is just data (e.g., a 'K'
    parameter column), and values there should be emitted as data, not as
    row stubs. We align the oracle with the parser's behavior.

    Additionally require a rowspan>1 dimensional marker in body col 0 OR
    a full-depth th spanning the whole thead at col 0 — both signals the
    parser uses before promoting.
    """
    if col != 0:
        return False
    if thead_rows < 2:
        return False
    # Check for rowspan>1 in body col 0
    has_body_rowspan = False
    for r in range(thead_rows, len(grid)):
        cell = grid[r][col]
        if cell.get("origin") == (r, col) and cell.get("rowspan", 1) > 1:
            has_body_rowspan = True
            break
    # Check for full-depth header at (0, 0) — a <th rowspan="thead_rows">
    header_full_depth = False
    if grid and grid[0]:
        h0 = grid[0][0]
        if h0.get("origin") == (0, 0) and h0.get("rowspan", 1) == thead_rows:
            header_full_depth = True
    return has_body_rowspan or header_full_depth


def html_to_oracle(table_html: str) -> tuple[str, dict] | None:
    """Return (html, oracle_dict) or None if the table is unsuitable."""
    table = _extract_table(table_html)
    if table is None:
        return None

    grid, thead_rows = _build_grid(table)
    if not grid or not grid[0]:
        return None
    n_rows = len(grid)
    n_cols = len(grid[0])

    if thead_rows == 0 or thead_rows >= n_rows:
        return None  # no tbody data rows

    # Detect left-header columns (stubs).
    stub_cols = 1 if _looks_like_stub_col(grid, thead_rows, 0) else 0

    triples: list[dict] = []
    source_tokens: set[str] = set()

    for r in range(n_rows):
        for c in range(n_cols):
            t = grid[r][c]["text"].strip()
            if t:
                source_tokens.add(t)

    # Data cells are in tbody, beyond stub cols.
    for r in range(thead_rows, n_rows):
        for c in range(stub_cols, n_cols):
            value = grid[r][c]["text"].strip()
            if not value:
                continue
            col_path = _col_path_for(grid, r, c, thead_rows)
            row_path = _row_path_for(grid, r, c, stub_cols)
            triples.append({"row": row_path, "col": col_path, "value": value})

    # Minimal quality gate: need at least some rules, at least some col path.
    if not triples:
        return None
    with_col = sum(1 for t in triples if t["col"])
    if with_col < max(1, len(triples) // 3):
        return None

    oracle = {
        "source_url": "https://huggingface.co/datasets/apoidea/pubtabnet-html",
        "source_license": "CDLA-Permissive-1.0",
        "source_tokens": sorted(source_tokens),
        "triples": triples,
    }
    return str(table), oracle


# ------------------------------------------------------------------ selection


def _complexity_score(html: str, oracle: dict) -> int:
    """Favor structurally-complex tables for red-teaming."""
    score = 0
    # Multi-row thead (hierarchical headers)
    table = BeautifulSoup(html, "html.parser").find("table")
    if table:
        thead = table.find("thead")
        if thead:
            thead_row_count = len(thead.find_all("tr", recursive=False))
            score += thead_row_count * 10
        # Merges
        for cell in table.find_all(["td", "th"]):
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            if rs > 1 or cs > 1:
                score += 3
    # Triple variety
    score += min(50, len(oracle["triples"]))
    # Avoid trivially tiny tables
    if len(oracle["triples"]) < 6:
        score -= 50
    return score


def _size_acceptable(html: str) -> bool:
    """Exclude tables that are too big (review pain) or too small (trivial)."""
    table = BeautifulSoup(html, "html.parser").find("table")
    if table is None:
        return False
    rows = table.find_all("tr")
    if not (4 <= len(rows) <= 20):
        return False
    first_row_cells = rows[0].find_all(["td", "th"]) if rows else []
    if not (3 <= len(first_row_cells) <= 10):
        return False
    return True


def _sanitize_html(html: str) -> str:
    """Strip the surrounding <html>/<head>/<body> wrapping; keep only <table>.

    PubTabNet's 'html_table' field wraps the table in a full HTML document
    with a <style> block. We only need the <table> element as a fixture.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return html
    return str(table)


# ------------------------------------------------------------------ main


def _iter_pubtabnet() -> Iterator[dict]:
    from datasets import load_dataset

    ds = load_dataset(
        "apoidea/pubtabnet-html", split="train", streaming=True
    )
    # Skip image column to speed up streaming.
    ds = ds.remove_columns(["image"])
    for rec in ds:
        yield rec


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clear previous PubTabNet fixtures.
    for f in list(OUT_DIR.glob("*.md")) + list(OUT_DIR.glob("*.oracle.json")):
        f.unlink()

    picks: list[tuple[int, str, str, dict]] = []
    scanned = 0

    for rec in _iter_pubtabnet():
        scanned += 1
        if scanned > SCAN_LIMIT:
            break
        html = rec.get("html_table") or ""
        if not html:
            continue
        clean_html = _sanitize_html(html)
        if not _size_acceptable(clean_html):
            continue
        result = html_to_oracle(clean_html)
        if result is None:
            continue
        _, oracle = result
        score = _complexity_score(clean_html, oracle)
        if score <= 0:
            continue
        imgid = str(rec.get("imgid", scanned))
        picks.append((score, imgid, clean_html, oracle))
        if scanned % 500 == 0:
            print(f"  scanned {scanned}, kept {len(picks)}")
        # Early stop heuristic: once we have plenty of good candidates.
        if len(picks) >= TARGET_N * 4:
            break

    print(f"Scanned {scanned} examples, kept {len(picks)} candidates")
    picks.sort(key=lambda x: -x[0])
    picks = picks[:TARGET_N]

    for score, imgid, html, oracle in picks:
        slug = f"pubtabnet-{imgid}"
        header = (
            f"<!-- source: PubTabNet imgid={imgid} "
            f"(https://huggingface.co/datasets/apoidea/pubtabnet-html, "
            f"CDLA-Permissive-1.0) -->\n"
        )
        (OUT_DIR / f"{slug}.md").write_text(header + html + "\n", encoding="utf-8")
        (OUT_DIR / f"{slug}.oracle.json").write_text(
            json.dumps(oracle, indent=2), encoding="utf-8"
        )

    print(f"Wrote {len(picks)} PubTabNet fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()
