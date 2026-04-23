"""FinTabNet fixture generator.

Streams the `apoidea/fintabnet-html` dataset (CDLA-Permissive-1.0,
MIT-compatible) from HuggingFace. For each table, emits:

  tests/realworld/fintabnet/<id>.md          — the table's HTML
  tests/realworld/fintabnet/<id>.oracle.json — (row_path, col_path, value)
                                              triples computed independently
                                              from the HTML structure

Structural contrast with PubTabNet:
  - FinTabNet tables use no <thead> and no <th>. Every cell is a bare <td>.
  - The header boundary has to be inferred from the shape of the grid:
    leading rows whose first cell is empty are treated as header rows
    (the near-universal convention in 10-K financial tables).
  - The oracle marks those rows as in_thead=True before walking the grid,
    so the PubTabNet merge-aware walker logic is reused verbatim.

The oracle is extracted from the HTML with our own BS4-based merge-aware
grid walker — it must NOT call table2rules, otherwise the test becomes
circular.

Run:
    python scripts/build_fintabnet_fixtures.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.request
from html import escape
from pathlib import Path
from typing import Iterator

import pyarrow.parquet as pq
from bs4 import BeautifulSoup, NavigableString, Tag

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "tests" / "realworld" / "fintabnet"

TARGET_N = int(os.environ.get("N_FINTABNET", "200"))
SCAN_LIMIT = int(os.environ.get("SCAN_LIMIT", "8000"))

HF_BASE = "https://huggingface.co/datasets/apoidea/fintabnet-html/resolve/main/en"
SHARD_COUNT = 18
SHARD_CACHE = Path(os.environ.get("FINTABNET_CACHE", "/tmp/fintabnet_shards"))


# ------------------------------------------------------------------ extraction


_WS = re.compile(r"\s+")
_NUMERIC = re.compile(r"^[\(\-]?[\$£€]?[\d,]+\.?\d*[\)%]?$")
_ALPHA_WORD = re.compile(r"[A-Za-z]{3,}")


def _text_of(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return _WS.sub(" ", str(node)).strip()
    return _WS.sub(" ", node.get_text()).strip()


def _is_numeric_cell(text: str) -> bool:
    """Cells like '$1,098,987', '(2,128)', '43.3%', '2018' — data, not header."""
    if not text:
        return False
    return bool(_NUMERIC.match(text.replace(" ", "")))


def _extract_table(html_doc: str) -> Tag | None:
    soup = BeautifulSoup(html_doc, "html.parser")
    return soup.find("table")


def _infer_thead_rows(rows: list[Tag]) -> int:
    """Count leading rows whose first cell is empty.

    FinTabNet's convention: header rows leave col 0 blank; the first row
    with text in col 0 is the first data row. If no row has col 0 empty,
    there is no clear header boundary and the caller should filter the
    table out.
    """
    count = 0
    for row in rows:
        cells = [c for c in row.find_all(["td", "th"]) if c.find_parent("tr") is row]
        if not cells:
            continue
        first_text = _text_of(cells[0])
        if first_text:
            break
        count += 1
    return count


def _build_grid(
    table: Tag, thead_rows_override: int
) -> tuple[list[list[dict]], int]:
    """Return (grid, thead_rows_count).

    Each grid cell: {"text": str, "origin": (r, c), "rowspan": int,
    "colspan": int, "in_thead": bool}. Span children point back to
    origin for merge-aware walking.
    """
    rows = [
        r for r in table.find_all("tr")
        if r.find_parent("table") is table
    ]
    thead_count = thead_rows_override

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

    for r_idx, row in enumerate(rows):
        in_thead = r_idx < thead_count
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
                        # Rowspan may extend a header cell into body rows;
                        # keep in_thead true for the origin row only.
                        cell_in_thead = in_thead and dr == 0
                        grid[tr][tc] = {
                            "text": text,
                            "origin": (r_idx, col),
                            "rowspan": rs,
                            "colspan": cs,
                            "in_thead": cell_in_thead,
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
    out: list[str] = []
    for t in path:
        if out and out[-1] == t:
            continue
        out.append(t)
    return out


def _row_path_for(grid: list[list[dict]], r: int, c: int, stub_cols: int) -> list[str]:
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
    out: list[str] = []
    for t in path:
        if out and out[-1] == t:
            continue
        out.append(t)
    return out


def _looks_like_stub_col(grid: list[list[dict]], thead_rows: int, col: int) -> bool:
    """Detect col 0 as a row-stub — same criterion as the PubTabNet script.

    Requires thead_rows>=2 PLUS a rowspan>1 dimensional marker in body col
    0 OR a full-depth header at (0, 0). This aligns the oracle with the
    parser's stub-promotion rule (see PubTabNet generator).
    """
    if col != 0:
        return False
    if thead_rows < 2:
        return False
    has_body_rowspan = False
    for r in range(thead_rows, len(grid)):
        cell = grid[r][col]
        if cell.get("origin") == (r, col) and cell.get("rowspan", 1) > 1:
            has_body_rowspan = True
            break
    header_full_depth = False
    if grid and grid[0]:
        h0 = grid[0][0]
        if h0.get("origin") == (0, 0) and h0.get("rowspan", 1) == thead_rows:
            header_full_depth = True
    return has_body_rowspan or header_full_depth


def _header_rows_have_labels(grid: list[list[dict]], thead_rows: int) -> bool:
    """A row counts as a real header row only if it contains at least one
    cell with a 3+ letter alphabetic word. Pure-numeric 'headers' are a
    sign the table has no header at all (e.g., lease-schedule tables of
    year/amount pairs with no header row)."""
    if thead_rows == 0:
        return False
    for r in range(thead_rows):
        for c in range(len(grid[r])):
            cell = grid[r][c]
            if cell.get("origin") != (r, c):
                continue
            text = cell["text"].strip()
            if text and _ALPHA_WORD.search(text):
                return True
    return False


def html_to_oracle(table_html: str) -> tuple[str, dict] | None:
    """Return (html, oracle_dict) or None if the table is unsuitable."""
    table = _extract_table(table_html)
    if table is None:
        return None

    rows = [
        r for r in table.find_all("tr") if r.find_parent("table") is table
    ]
    if len(rows) < 3:
        return None

    thead_rows_inferred = _infer_thead_rows(rows)
    if thead_rows_inferred == 0:
        return None  # no clear header boundary

    grid, thead_rows = _build_grid(table, thead_rows_inferred)
    if not grid or not grid[0]:
        return None
    n_rows = len(grid)
    n_cols = len(grid[0])

    if thead_rows == 0 or thead_rows >= n_rows:
        return None

    if not _header_rows_have_labels(grid, thead_rows):
        return None

    stub_cols = 1 if _looks_like_stub_col(grid, thead_rows, 0) else 0

    triples: list[dict] = []
    source_tokens: set[str] = set()

    for r in range(n_rows):
        for c in range(n_cols):
            t = grid[r][c]["text"].strip()
            if t:
                source_tokens.add(t)

    for r in range(thead_rows, n_rows):
        for c in range(stub_cols, n_cols):
            cell = grid[r][c]
            if cell.get("origin") != (r, c):
                continue  # span child, already emitted at origin
            value = cell["text"].strip()
            if not value:
                continue
            col_path = _col_path_for(grid, r, c, thead_rows)
            row_path = _row_path_for(grid, r, c, stub_cols)
            triples.append({"row": row_path, "col": col_path, "value": value})

    if not triples:
        return None
    with_col = sum(1 for t in triples if t["col"])
    if with_col < max(1, len(triples) // 2):
        return None

    oracle = {
        "source_url": "https://huggingface.co/datasets/apoidea/fintabnet-html",
        "source_license": "CDLA-Permissive-1.0",
        "source_tokens": sorted(source_tokens),
        "triples": triples,
    }
    return str(table), oracle


# ------------------------------------------------------------------ selection


def _complexity_score(html: str, oracle: dict) -> int:
    """Favor structurally-complex tables for red-teaming."""
    score = 0
    table = BeautifulSoup(html, "html.parser").find("table")
    if table:
        rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
        # Bonus for multi-row header (inferred by col 0 empty)
        header_rows = _infer_thead_rows(rows)
        score += header_rows * 10
        # Merges
        for cell in table.find_all(["td", "th"]):
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            if rs > 1 or cs > 1:
                score += 3
        # Parenthesized negatives — a FinTabNet signature
        txt = table.get_text()
        if re.search(r"\(\d", txt):
            score += 5
        # Footnote markers
        if table.find("sup"):
            score += 3
    score += min(50, len(oracle["triples"]))
    if len(oracle["triples"]) < 6:
        score -= 50
    return score


def _size_acceptable(html: str) -> bool:
    table = BeautifulSoup(html, "html.parser").find("table")
    if table is None:
        return False
    rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
    if not (4 <= len(rows) <= 20):
        return False
    first_row_cells = rows[0].find_all(["td", "th"]) if rows else []
    if not (3 <= len(first_row_cells) <= 10):
        return False
    return True


# ------------------------------------------------------------------ I/O


def _download_shard(shard_idx: int) -> Path:
    SHARD_CACHE.mkdir(parents=True, exist_ok=True)
    fname = f"train-{shard_idx:05d}-of-{SHARD_COUNT:05d}.parquet"
    path = SHARD_CACHE / fname
    if path.exists() and path.stat().st_size > 0:
        return path
    url = f"{HF_BASE}/{fname}"
    print(f"  downloading {fname} ...")
    with tempfile.NamedTemporaryFile(dir=SHARD_CACHE, delete=False) as tmp:
        with urllib.request.urlopen(url) as r:
            shutil.copyfileobj(r, tmp)
        Path(tmp.name).rename(path)
    return path


def _iter_fintabnet() -> Iterator[tuple[int, int, str]]:
    """Yield (shard_idx, row_idx_in_shard, html_table) tuples."""
    for shard_idx in range(SHARD_COUNT):
        path = _download_shard(shard_idx)
        pf = pq.ParquetFile(path)
        # Read only html_table to skip image bytes.
        base_row = 0
        for rg in range(pf.metadata.num_row_groups):
            tbl = pf.read_row_group(rg, columns=["html_table"])
            for i in range(tbl.num_rows):
                yield shard_idx, base_row + i, tbl["html_table"][i].as_py()
            base_row += tbl.num_rows


# ------------------------------------------------------------------ main


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in list(OUT_DIR.glob("*.md")) + list(OUT_DIR.glob("*.oracle.json")):
        f.unlink()

    picks: list[tuple[int, str, str, dict]] = []
    scanned = 0

    for shard_idx, row_idx, html in _iter_fintabnet():
        scanned += 1
        if scanned > SCAN_LIMIT:
            break
        if not html:
            continue
        if not _size_acceptable(html):
            continue
        result = html_to_oracle(html)
        if result is None:
            continue
        clean_html, oracle = result
        score = _complexity_score(clean_html, oracle)
        if score <= 0:
            continue
        slug_id = f"s{shard_idx}-r{row_idx}"
        picks.append((score, slug_id, clean_html, oracle))
        if scanned % 500 == 0:
            print(f"  scanned {scanned}, kept {len(picks)}")
        if len(picks) >= TARGET_N * 4:
            break

    print(f"Scanned {scanned} examples, kept {len(picks)} candidates")
    picks.sort(key=lambda x: -x[0])
    picks = picks[:TARGET_N]

    for score, slug_id, html, oracle in picks:
        slug = f"fintabnet-{slug_id}"
        header = (
            f"<!-- source: FinTabNet {slug_id} "
            f"(https://huggingface.co/datasets/apoidea/fintabnet-html, "
            f"CDLA-Permissive-1.0) -->\n"
        )
        (OUT_DIR / f"{slug}.md").write_text(header + html + "\n", encoding="utf-8")
        (OUT_DIR / f"{slug}.oracle.json").write_text(
            json.dumps(oracle, indent=2), encoding="utf-8"
        )

    print(f"Wrote {len(picks)} FinTabNet fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()
