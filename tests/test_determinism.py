"""Determinism check: two runs over the same input produce byte-identical output.

Cheap insurance against accidentally introducing ordering dependencies — set
iteration order, dict traversal, locale-sensitive sorting, etc. — that would
make the library non-reproducible across runs. Integrators who cache rule
output by content hash rely on this property.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from table2rules import process_tables_to_text, process_tables_with_stats

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


def _fixtures() -> list[Path]:
    skip_prefixes = {"realworld"}
    return [
        p
        for p in sorted(TESTS_DIR.rglob("*.md"))
        if not (skip_prefixes & set(p.relative_to(TESTS_DIR).parts)) and p.parent != TESTS_DIR
    ]


FIXTURES = _fixtures()


@pytest.mark.parametrize("fixture", FIXTURES, ids=[str(p.relative_to(TESTS_DIR)) for p in FIXTURES])
def test_text_output_is_deterministic(fixture: Path) -> None:
    html = fixture.read_text(encoding="utf-8")
    first = process_tables_to_text(html)
    second = process_tables_to_text(html)
    assert first == second


def test_stats_output_is_deterministic() -> None:
    # Do one combined pass over the whole corpus for the stats API — per-file
    # parametrization would double the run time for limited extra signal.
    for fixture in FIXTURES:
        html = fixture.read_text(encoding="utf-8")
        first_text, first_report = process_tables_with_stats(html)
        second_text, second_report = process_tables_with_stats(html)
        assert first_text == second_text
        assert first_report == second_report
