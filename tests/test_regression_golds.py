"""Regression layer — byte-for-byte gold matching on hand-authored fixtures.

Each .md file beneath tests/{adversarial,structured,headerless,smoke,
regression}/ is a fixture containing HTML table markup. For every fixture
we run process_tables_to_text and assert the output matches the committed
gold file under benchmarks/gold/<format>/.

This is the strictest of the three test layers — catches any output drift.
See tests/README.md for the relationship to the correctness and robustness
suites.

Refresh gold outputs by running:  python scripts/benchmark.py --update-gold
"""

from __future__ import annotations

from pathlib import Path

import pytest

from table2rules import process_tables_to_text
from table2rules.exporters import DEFAULT_FORMAT

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
GOLD_DIR = ROOT / "benchmarks" / "gold" / DEFAULT_FORMAT


def _discover_cases() -> list[Path]:
    # Real-world fixtures (tests/realworld/) are checked against per-fixture
    # oracle triples, not frozen gold text — see test_correctness_oracle.py.
    # Top-level docs like README.md are not fixtures.
    skip_prefixes = {"realworld"}
    return [
        p
        for p in sorted(TESTS_DIR.rglob("*.md"))
        if not (skip_prefixes & set(p.relative_to(TESTS_DIR).parts))
        and p.parent != TESTS_DIR  # exclude tests/README.md etc.
    ]


def _case_id(path: Path) -> str:
    return str(path.relative_to(TESTS_DIR))


def _gold_path(case_path: Path) -> Path:
    return GOLD_DIR / case_path.relative_to(TESTS_DIR).with_suffix(".out.txt")


CASES = _discover_cases()


@pytest.mark.parametrize("case_path", CASES, ids=[_case_id(c) for c in CASES])
def test_corpus_matches_gold(case_path: Path) -> None:
    gold_path = _gold_path(case_path)
    if not gold_path.exists():
        pytest.fail(
            f"missing gold file: {gold_path}\n"
            "run: python scripts/benchmark.py --update-gold"
        )

    html = case_path.read_text(encoding="utf-8")
    actual = process_tables_to_text(html)
    expected = gold_path.read_text(encoding="utf-8")

    assert actual == expected, f"output drifted for {_case_id(case_path)}"
