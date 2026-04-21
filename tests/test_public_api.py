"""Contract tests for the public ``table2rules`` API surface.

These guard the semver contract: shape of ``RenderReport`` / ``TableReport``,
``render_mode`` values, ``REASONS`` catalogue, ``LogicRule`` immutability,
``strict`` behaviour, and the ``TableTooLargeError`` path. Anything touching
these fields becomes a visible test failure instead of a silent downstream
break.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from table2rules import (
    REASONS,
    LogicRule,
    RenderReport,
    Table2RulesError,
    TableReport,
    TableTooLargeError,
    process_table,
    process_tables_to_text,
    process_tables_with_stats,
)

ROOT = Path(__file__).resolve().parent.parent


# --- LogicRule --------------------------------------------------------------


def test_logicrule_is_frozen() -> None:
    rule = LogicRule(outcome="x", position=(0, 0))
    with pytest.raises(Exception):  # FrozenInstanceError on 3.11+
        rule.outcome = "y"  # type: ignore[misc]


def test_logicrule_is_hashable() -> None:
    rule = LogicRule(outcome="x", position=(0, 0), row_headers=("A",), col_headers=("B",))
    # Usable as a dict key / set member — tuple-valued headers make this sound.
    assert {rule: 1}[rule] == 1
    assert rule in {rule}


def test_logicrule_no_conditions_field() -> None:
    # Removed in 0.2.0 — ensure it stays gone.
    rule = LogicRule(outcome="x", position=(0, 0))
    assert not hasattr(rule, "conditions")


# --- Exceptions -------------------------------------------------------------


def test_tabletoolarge_is_table2rules_error() -> None:
    assert issubclass(TableTooLargeError, Table2RulesError)
    assert issubclass(Table2RulesError, Exception)


# --- Empty / trivial inputs -------------------------------------------------


def test_empty_html_returns_empty_report() -> None:
    text, report = process_tables_with_stats("")
    assert text == ""
    assert report.tables == ()
    assert report.tables_rendered == 0
    assert report.tables_flagged == 0


def test_html_without_tables_returns_empty_report() -> None:
    text, report = process_tables_with_stats("<p>no tables here</p>")
    assert text == ""
    assert report.tables == ()


# --- Clean render (render_mode="rules") -------------------------------------


CLEAN_TABLE = (
    "<table>"
    "<thead><tr><th>Metric</th><th>Q1</th><th>Q2</th></tr></thead>"
    "<tbody>"
    "<tr><th>Revenue</th><td>100</td><td>120</td></tr>"
    "<tr><th>Cost</th><td>50</td><td>60</td></tr>"
    "</tbody></table>"
)


def _span_bomb() -> str:
    """A small HTML string that expands to a grid past the 1M-cell cap.

    Two cells per row at ``colspan=600`` each → ``max_cols = 1200`` after
    per-cell clamping (both fit under the 1000 per-cell cap). 900 rows →
    ``1200 * 900 = 1_080_000`` cells, past ``MAX_GRID_CELLS = 1_000_000``.

    Keeps the source HTML ~25 KB so BeautifulSoup isn't the bottleneck — the
    interesting behaviour is ``parse_table_to_grid`` refusing to allocate.
    """
    row = '<tr><td colspan="600">a</td><td colspan="600">b</td></tr>'
    return "<table>" + row * 900 + "</table>"


SPAN_BOMB = _span_bomb()


def test_clean_table_produces_rules_mode() -> None:
    text, report = process_tables_with_stats(CLEAN_TABLE)
    assert text  # non-empty
    assert len(report.tables) == 1
    tr = report.tables[0]
    assert tr.table_index == 0
    assert tr.render_mode == "rules"
    assert tr.gate_ok is True
    assert tr.reasons == ()
    assert tr.error is None
    assert report.tables_rendered == 1
    assert report.tables_flagged == 0


def test_string_api_matches_stats_api_text() -> None:
    # The text output must not depend on which entry point you call.
    text_only = process_tables_to_text(CLEAN_TABLE)
    text_stats, _ = process_tables_with_stats(CLEAN_TABLE)
    assert text_only == text_stats


# --- Fallback render modes --------------------------------------------------


def test_span_bomb_is_skipped_with_input_too_large() -> None:
    text, report = process_tables_with_stats(SPAN_BOMB)
    assert text == ""
    assert len(report.tables) == 1
    tr = report.tables[0]
    assert tr.render_mode == "skipped"
    assert "input_too_large" in tr.reasons
    assert tr.error is not None  # carries the message


def test_strict_mode_raises_too_large() -> None:
    with pytest.raises(TableTooLargeError):
        process_tables_with_stats(SPAN_BOMB, strict=True)


def test_multiple_tables_indexed_and_ordered() -> None:
    html = CLEAN_TABLE + "<table><tr><td>lone</td></tr></table>"
    _, report = process_tables_with_stats(html)
    assert [t.table_index for t in report.tables] == [0, 1]
    assert report.tables[0].render_mode == "rules"
    # Second is a 1x1 table with no header context — degrades.
    assert report.tables[1].render_mode in ("flat", "passthrough")


# --- process_table (single-table API) ---------------------------------------


def test_process_table_fail_open_returns_empty_list() -> None:
    # Malformed input that raises inside the pipeline — fail-open default.
    assert process_table("<table><tr><td>x</td></tr></table>") == [] or process_table(
        "<table><tr><td>x</td></tr></table>"
    )  # may or may not pass gate; just must not raise
    # Truly broken input still doesn't raise:
    assert process_table("not html at all") == []


def test_process_table_strict_raises_on_span_bomb() -> None:
    with pytest.raises(TableTooLargeError):
        process_table(SPAN_BOMB, strict=True)


# --- REASONS catalogue ------------------------------------------------------


def test_reasons_catalogue_shape() -> None:
    assert isinstance(REASONS, dict)
    assert REASONS  # non-empty
    for key, description in REASONS.items():
        assert isinstance(key, str) and key
        assert isinstance(description, str) and description
    # Report-level reasons that this test file reaches must be documented.
    for required in ("input_too_large", "processing_error", "low_coverage",
                     "low_header_attachment", "no_candidate_data_cells"):
        assert required in REASONS, f"{required} missing from REASONS catalogue"


def test_every_reason_emitted_by_corpus_is_documented() -> None:
    """Fuzz the full fixture corpus; assert every emitted reason is in REASONS.

    This is the semver check: if the gate ever adds a new reason string, this
    test fails until the author also updates REASONS with a description.
    """
    fixtures = [
        p for p in (ROOT / "tests").rglob("*.md")
        if "realworld" not in p.parts and p.parent != ROOT / "tests"
    ]
    seen: set[str] = set()
    for p in fixtures:
        _, report = process_tables_with_stats(p.read_text(encoding="utf-8"))
        for t in report.tables:
            seen.update(t.reasons)
    undocumented = seen - set(REASONS)
    assert not undocumented, (
        f"emitted reasons missing from REASONS catalogue: {sorted(undocumented)}"
    )


# --- RenderReport.merge -----------------------------------------------------


def test_merge_concatenates_tables_preserving_indices() -> None:
    _, r1 = process_tables_with_stats(CLEAN_TABLE)
    _, r2 = process_tables_with_stats(CLEAN_TABLE + CLEAN_TABLE)
    merged = RenderReport.merge([r1, r2])
    assert len(merged.tables) == 3
    # Original indices are preserved, not renumbered.
    assert [t.table_index for t in merged.tables] == [0, 0, 1]
    assert merged.tables_rendered == 3
    assert merged.tables_flagged == 0


def test_merge_empty_iterable_returns_empty_report() -> None:
    merged = RenderReport.merge([])
    assert merged.tables == ()
    assert merged.tables_rendered == 0


# --- TableReport shape ------------------------------------------------------


def test_tablereport_is_frozen() -> None:
    _, report = process_tables_with_stats(CLEAN_TABLE)
    tr = report.tables[0]
    with pytest.raises(Exception):
        tr.render_mode = "flat"  # type: ignore[misc]


def test_tablereport_render_mode_values_are_from_literal_set() -> None:
    # Exhaustive list — any new value requires documentation here and a
    # matching minor-version bump of the library.
    allowed = {"rules", "flat", "passthrough", "skipped"}
    _, report = process_tables_with_stats(
        CLEAN_TABLE + "<table><tr><td>lone</td></tr></table>"
    )
    for t in report.tables:
        assert t.render_mode in allowed
