import logging
from typing import List, Tuple, Union

from bs4 import BeautifulSoup, Tag

from .cleanup import clean_rules
from .errors import TableTooLargeError
from .exporters import DEFAULT_FORMAT, Exporter, get_exporter
from .grid_parser import clean_text, parse_table_to_grid
from .maze_pathfinder import find_headers_for_cell
from .models import LogicRule
from .quality_gate import GateResult, assess_confidence
from .report import RenderMode, RenderReport, TableReport
from .simple_repair import simple_repair


def _split_compound_tables(soup) -> None:
    """Split tables with mid-body header resets into separate tables.

    Detects all-<th> rows in the body that redefine column names (e.g. OCR
    page-break repeats where "Sales" becomes "Returns").  Each section gets
    its own <table> so it is parsed with the correct headers.

    Operates on the raw soup BEFORE simple_repair to avoid false positives
    from summary rows promoted to <th>.
    """
    for table in list(soup.find_all("table")):
        rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
        if len(rows) < 3:
            continue

        # Find all-th rows in source markup, but only treat them as
        # split points when data rows appear in between.  Consecutive
        # all-th rows (top or post-data) form a single multi-row header,
        # not separate boundaries.  Summary rows that simple_repair later
        # promotes to <th> (e.g. "Total", "Subtotal") must not be treated
        # as boundaries either.
        SUMMARY_LABELS = {"total", "subtotal", "sub total", "grand total"}
        header_indices: List[int] = []
        seen_data_row = False
        prev_was_header_row = False
        for idx, row in enumerate(rows):
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            all_th = len(cells) >= 2 and all(c.name == "th" for c in cells)
            looks_like_summary = any(
                c.get_text(strip=True).lower() in SUMMARY_LABELS for c in cells
            )
            if all_th and not looks_like_summary:
                non_empty = sum(1 for c in cells if c.get_text(strip=True))
                if non_empty >= len(cells) // 2:
                    if not seen_data_row:
                        # Part of the initial header block
                        if not header_indices:
                            header_indices.append(idx)
                    elif not prev_was_header_row:
                        # Genuine reset (previous content row was data, not
                        # another header row continuing a multi-row header)
                        header_indices.append(idx)
                prev_was_header_row = True
            elif len(cells) >= 2:
                # Only multi-cell non-th rows count as data.
                # Single-cell rows (titles, captions) don't flip the flag.
                seen_data_row = True
                prev_was_header_row = False
            else:
                prev_was_header_row = False

        if len(header_indices) < 2:
            continue

        boundaries = header_indices + [len(rows)]
        for i in range(len(header_indices)):
            section_rows = rows[boundaries[i] : boundaries[i + 1]]
            has_data = any(
                len(r.find_all(["td", "th"], recursive=False)) >= 2
                and any(c.name == "td" for c in r.find_all(["td", "th"], recursive=False))
                for r in section_rows
            )
            if not has_data:
                break
        else:
            sections_html = []
            for i in range(len(header_indices)):
                start = boundaries[i]
                end = boundaries[i + 1]
                section_rows = rows[start:end]
                new_table = soup.new_tag("table")
                for row in section_rows:
                    row.extract()
                    new_table.append(row)
                sections_html.append(new_table)
            for section in reversed(sections_html):
                table.insert_after(section)
            table.decompose()


def _extract_cell_rows(table_html: str) -> List[List[str]]:
    """Return raw cell text for each row (header-free). Used as gate-fail fallback."""
    try:
        soup = BeautifulSoup(table_html, "html.parser")
        table = soup.find("table")
        if not isinstance(table, Tag):
            return []
        rows = [
            r
            for r in table.find_all("tr")
            if isinstance(r, Tag) and r.find_parent("table") is table
        ]
        out: List[List[str]] = []
        for row in rows:
            cells = row.find_all(["td", "th"], recursive=False)
            texts = [clean_text(c.get_text(" ", strip=True)) for c in cells]
            if any(texts):
                out.append(texts)
        return out
    except Exception:
        return []


def _build_rules(grid) -> List[LogicRule]:
    """Walk the parsed grid and emit one LogicRule per data cell position."""
    rules: List[LogicRule] = []

    for row_idx in range(len(grid)):
        for col_idx in range(len(grid[0])):
            cell = grid[row_idx][col_idx]

            # Only <td> cells are data cells
            if cell["type"] != "td":
                continue

            # Defensive guard: never emit rules from explicit/implicit header rows
            if cell.get("is_thead", False) or cell.get("is_header_row", False):
                continue

            if not cell.get("text", "").strip():
                continue

            # If this is a span copy, skip it (we'll process it from origin)
            if cell.get("is_span_copy", False):
                continue

            rowspan = cell.get("rowspan", 1)
            colspan = cell.get("colspan", 1)

            for r_offset in range(rowspan):
                for c_offset in range(colspan):
                    target_row = row_idx + r_offset
                    target_col = col_idx + c_offset

                    if target_row >= len(grid) or target_col >= len(grid[0]):
                        continue

                    row_headers, col_headers = find_headers_for_cell(grid, target_row, target_col)

                    rules.append(
                        LogicRule(
                            outcome=cell["text"],
                            position=(target_row, target_col),
                            is_footer=cell.get("is_footer", False),
                            row_headers=tuple(row_headers),
                            col_headers=tuple(col_headers),
                            origin=(row_idx, col_idx),
                        )
                    )

    return rules


def _process_table_with_gate(table_html: str) -> Tuple[List[LogicRule], GateResult]:
    """Runs the full pipeline and returns rules plus the gate verdict.

    Rules are ``[]`` when the gate fails. Raises ``TableTooLargeError`` on
    adversarial span values and propagates other parse errors; the caller
    decides whether to swallow them.
    """
    repaired = simple_repair(table_html)
    soup = BeautifulSoup(repaired, "html.parser")
    table = soup.find("table")
    if not isinstance(table, Tag):
        return [], GateResult(ok=False, score=0.0, reasons=["empty_grid"])

    grid = parse_table_to_grid(table)
    if not grid:
        return [], GateResult(ok=False, score=0.0, reasons=["empty_grid"])

    rules = clean_rules(_build_rules(grid))
    gate = assess_confidence(grid, rules)
    if not gate.ok:
        return [], gate
    return rules, gate


def process_table(table_html: str, *, strict: bool = False) -> List[LogicRule]:
    """Process a single table and return rules (one per cell position).

    Args:
        table_html: HTML string containing a single ``<table>``.
        strict: when ``True``, re-raise parse errors and ``TableTooLargeError``.
                Default ``False`` is fail-open: returns ``[]`` on any parse
                error, adversarial input, or gate failure. Use
                :func:`process_tables_with_stats` if you need to tell those
                apart.
    """
    try:
        rules, _ = _process_table_with_gate(table_html)
        return rules
    except Exception:
        if strict:
            raise
        logging.debug("process_table failed on input, returning empty", exc_info=True)
        return []


def _run(
    html_content: str,
    format: Union[str, Exporter],
    collect_report: bool,
    strict: bool,
) -> Tuple[str, RenderReport]:
    """Shared engine for both public entry points."""
    exporter = get_exporter(format)

    if not html_content:
        return "", RenderReport()

    soup = BeautifulSoup(html_content, "html.parser")
    if not soup.find_all("table"):
        return "", RenderReport()

    # Pre-process: split compound tables that have mid-body header resets
    # (all-<th> rows appearing after the first header row with different
    # column names). Must happen BEFORE repair to avoid false positives
    # from summary rows that Fix 5 promotes to <th>.
    _split_compound_tables(soup)
    all_tables = soup.find_all("table")

    output_chunks: List[str] = []
    reports: List[TableReport] = []
    table_index = 0

    for table in all_tables:
        # Skip nested tables — they're folded into their parent's cell text.
        if table.find_parent("table"):
            continue

        table_html = str(table)
        rules: List[LogicRule] = []
        gate: GateResult = GateResult(ok=False, score=0.0, reasons=[])
        too_large = False
        error_msg = None

        try:
            rules, gate = _process_table_with_gate(table_html)
        except TableTooLargeError as exc:
            if strict:
                raise
            too_large = True
            error_msg = str(exc)
        except Exception as exc:
            if strict:
                raise
            logging.debug("table processing failed; falling back", exc_info=True)
            error_msg = f"{type(exc).__name__}: {exc}"

        render_mode: RenderMode
        table_chunks: List[str] = []
        if rules:
            table_chunks = list(exporter.export_rules(rules))
            render_mode = "rules"
        elif too_large:
            # Refuse to emit anything for span-bomb input — the fallback paths
            # would still iterate the HTML, which is fine, but the signal to
            # downstream consumers is clearer if we skip entirely.
            render_mode = "skipped"
        else:
            cell_rows = _extract_cell_rows(table_html)
            flat = exporter.export_flat(cell_rows) if cell_rows else []
            if flat:
                table_chunks = list(flat)
                render_mode = "flat"
            else:
                table_chunks = [table_html]
                render_mode = "passthrough"
        output_chunks.extend(table_chunks)

        if collect_report:
            reasons = tuple(gate.reasons)
            if too_large:
                reasons = ("input_too_large",) + reasons
            elif error_msg is not None:
                reasons = ("processing_error",) + reasons
            caption_tag = table.find("caption", recursive=False)
            caption_text = (
                clean_text(caption_tag.get_text()) if caption_tag else ""
            ) or None
            reports.append(
                TableReport(
                    table_index=table_index,
                    render_mode=render_mode,
                    gate_ok=gate.ok,
                    gate_score=gate.score,
                    reasons=reasons,
                    error=error_msg,
                    caption=caption_text,
                    text="\n".join(table_chunks),
                )
            )
        table_index += 1

    text = "\n".join(output_chunks) if output_chunks else ""
    report = RenderReport(tables=tuple(reports)) if collect_report else RenderReport()
    return text, report


def process_tables_to_text(
    html_content: str,
    format: Union[str, Exporter] = DEFAULT_FORMAT,
) -> str:
    """HTML -> formatted text (fail-open, no observability).

    Args:
        html_content: raw HTML containing one or more <table> elements.
        format: exporter name (e.g. ``"rules"``) or an ``Exporter`` instance.
                Defaults to ``"rules"`` (one rule per line, full header paths).
    """
    text, _ = _run(html_content, format=format, collect_report=False, strict=False)
    return text


def process_tables_with_stats(
    html_content: str,
    *,
    format: Union[str, Exporter] = DEFAULT_FORMAT,
    strict: bool = False,
) -> Tuple[str, RenderReport]:
    """HTML -> ``(formatted text, RenderReport)``.

    The report has one ``TableReport`` per top-level table in input order,
    carrying the gate verdict, the render mode actually used, and any error
    message captured while processing that table.

    Args:
        html_content: raw HTML containing one or more <table> elements.
        format: exporter name or an ``Exporter`` instance.
        strict: when ``True``, re-raise parse errors and ``TableTooLargeError``
                instead of falling back silently. Useful during development and
                tests; keep the default ``False`` in production pipelines that
                process untrusted input.
    """
    return _run(html_content, format=format, collect_report=True, strict=strict)
