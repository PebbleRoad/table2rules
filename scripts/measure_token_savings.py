"""Measure token impact: original HTML vs table2rules output.

Runs against the real-world PubTabNet fixtures under
`tests/realworld/pubtabnet/` so the numbers reflect genuine
scientific-paper tables, not a cherry-picked demo.

Output: distribution of token savings (negative = rules grew larger).

Usage:
    pip install tiktoken
    python scripts/measure_token_savings.py
"""

from __future__ import annotations

import statistics
from pathlib import Path

import tiktoken

from table2rules import process_tables_to_text

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "realworld" / "pubtabnet"

enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(s: str) -> int:
    return len(enc.encode(s))


def measure(md_path: Path) -> dict | None:
    html = md_path.read_text(encoding="utf-8")
    # Strip the fixture's leading HTML comment so we compare apples to apples.
    stripped = "\n".join(l for l in html.splitlines() if not l.startswith("<!--"))
    rules = process_tables_to_text(stripped)
    if not rules.strip():
        return None
    # Exclude PASSTHROUGH cases — the parser emitted raw HTML so the
    # "savings" would be zero by definition.
    if "<table" in rules:
        return None
    html_tok = count_tokens(stripped)
    rules_tok = count_tokens(rules)
    if rules_tok == 0:
        return None
    return {
        "fixture": md_path.name,
        "html_tok": html_tok,
        "rules_tok": rules_tok,
        "savings_pct": round((1 - rules_tok / html_tok) * 100, 1),
    }


def main() -> None:
    all_fixtures = sorted(FIXTURES.glob("*.md"))
    results = [r for md in all_fixtures if (r := measure(md)) is not None]

    if not results:
        print("no results — have you generated PubTabNet fixtures?")
        return

    savings = [r["savings_pct"] for r in results]
    html_toks = [r["html_tok"] for r in results]
    rules_toks = [r["rules_tok"] for r in results]

    print(
        f"Measured {len(results)} of {len(all_fixtures)} fixtures "
        f"(others fell to FLAT/PASSTHROUGH)"
    )
    print(f"Median HTML tokens:   {statistics.median(html_toks):.0f}")
    print(f"Median rules tokens:  {statistics.median(rules_toks):.0f}")
    print()
    q = statistics.quantiles(savings, n=4)
    print("Token savings  (1 - rules/html):")
    print(f"  min    {min(savings):>6.1f}%   (rules LARGER than HTML)")
    print(f"  p25    {q[0]:>6.1f}%")
    print(f"  median {statistics.median(savings):>6.1f}%")
    print(f"  mean   {statistics.mean(savings):>6.1f}%")
    print(f"  p75    {q[2]:>6.1f}%")
    print(f"  max    {max(savings):>6.1f}%")
    print()
    grew = sum(1 for s in savings if s < 0)
    print(
        f"Rules grew larger than HTML on {grew}/{len(results)} fixtures "
        f"({grew * 100 // len(results)}%) — dense tables with long header "
        "paths repeated on every cell."
    )


if __name__ == "__main__":
    main()
