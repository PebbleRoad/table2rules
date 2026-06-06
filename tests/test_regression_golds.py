"""Regression layer — byte-for-byte gold matching on every fixture.

Each .md file beneath tests/ (except top-level docs) is a fixture containing
HTML table markup. For every fixture we run process_tables_to_text and assert
the output matches the committed gold file under benchmarks/gold/<format>/.

This covers both the hand-authored fixtures AND the real-world corpus
(tests/realworld/). The two suites play complementary roles: the correctness
and robustness layers (test_correctness_oracle / test_robustness_mutations)
assert the output is *right* (no fabricated content, correct attribution,
stable under mutation); this layer asserts the output does not *change* unless
a human regenerates the golds. Together they catch a silent-drop regression —
where the parser quietly stops emitting real content — which neither the
oracle (it only guards against fabrication) nor an un-asserted benchmark gold
could catch on its own. See tests/README.md.

This is the strictest of the three test layers — catches any output drift.

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
    # Every fixture beneath tests/ is byte-checked, including the real-world
    # corpus (tests/realworld/) — frozen gold text is the tripwire that makes
    # any output change visible. Top-level docs like tests/README.md are not
    # fixtures and are excluded.
    return [
        p
        for p in sorted(TESTS_DIR.rglob("*.md"))
        if p.parent != TESTS_DIR  # exclude tests/README.md, tests/failing_table.md
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
            f"missing gold file: {gold_path}\nrun: python scripts/benchmark.py --update-gold"
        )

    html = case_path.read_text(encoding="utf-8")
    actual = process_tables_to_text(html)
    expected = gold_path.read_text(encoding="utf-8")

    assert actual == expected, f"output drifted for {_case_id(case_path)}"
