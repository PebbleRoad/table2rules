#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from typing import List

from table2rules import process_tables_to_text


HEADERS = ["A", "B", "C", "D", "E", "F"]
WORDS = ["alpha", "beta", "gamma", "delta", "north", "south", "total", "subtotal"]


def _rand_word(rng: random.Random) -> str:
    return rng.choice(WORDS)


def _header_row(cols: int) -> str:
    cells = "".join(f"<th>{HEADERS[i % len(HEADERS)]}</th>" for i in range(cols))
    return f"<tr>{cells}</tr>"


def _body_row(cols: int, r: int, rng: random.Random) -> str:
    cells: List[str] = []
    for c in range(cols):
        text = f"{_rand_word(rng)}-{r}-{c}"
        if c == 0 and rng.random() < 0.4:
            cells.append(f"<th>{text}</th>")
        else:
            cells.append(f"<td>{text}</td>")
    return f"<tr>{''.join(cells)}</tr>"


def _maybe_corrupt(html: str, rng: random.Random, corruption_rate: float) -> str:
    if rng.random() > corruption_rate:
        return html

    corruptions = [
        ("</td>", "</th>"),
        ("</th>", "</td>"),
        ("<tbody>", ""),
        ("</tbody>", ""),
        ("<thead>", ""),
        ("</thead>", ""),
    ]
    src, dst = rng.choice(corruptions)
    return html.replace(src, dst, 1)


def gen_table(rng: random.Random) -> str:
    cols = rng.randint(2, 6)
    rows = rng.randint(2, 8)
    with_thead = rng.random() < 0.7

    parts = ["<table>"]
    if with_thead:
        parts.append("<thead>")
        parts.append(_header_row(cols))
        parts.append("</thead>")

    parts.append("<tbody>")
    for r in range(rows):
        parts.append(_body_row(cols, r, rng))
    parts.append("</tbody>")
    parts.append("</table>")

    html = "".join(parts)
    return _maybe_corrupt(html, rng, corruption_rate=0.30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuzz hostile table inputs against parser.")
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    failures = 0

    for i in range(args.cases):
        html = gen_table(rng)
        try:
            _ = process_tables_to_text(html)
        except Exception as exc:
            failures += 1
            print(f"[FAIL] case={i} exception={type(exc).__name__}: {exc}")

    passed = args.cases - failures
    print(f"Fuzz complete: passed={passed} failed={failures} cases={args.cases}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
