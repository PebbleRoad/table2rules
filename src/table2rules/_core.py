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
from .spans import is_full_width_note


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
    n_cols = len(grid[0])

    # Rows that carry a *real* value — used below to decide which rows need
    # label-only preservation. A value that merely echoes its own column header
    # (a de-spanned or page-break-repeated header cell) carries no independent
    # data and is dropped downstream by clean_rules; it must not mask an
    # otherwise label-only row. Tracked at the value's *target* positions so a
    # rowspan-filled value correctly marks every row it covers.
    rows_with_value: set = set()

    for row_idx in range(len(grid)):
        for col_idx in range(n_cols):
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
            outcome_norm = cell["text"].strip().lower()

            # A wide <td> that reaches the last column AND covers a majority of
            # the grid's columns is structurally a full-width note/description
            # (e.g. a benefit name "Accidental death and permanent disability"
            # or "If the departure of your public transport is delayed…"
            # spanning the whole value region), not a per-column value. We still
            # emit at every spanned position — so the gate detects an
            # overlapping-span corruption (a rowspan intruding into the note's
            # row) as a conflict and fails open to flat — but attribute every
            # position to the *origin* column's header path. The exporter's
            # origin-aware dedup then collapses the identical lines to one,
            # instead of stamping the sentence under each plan×cover header.
            # Legitimate narrow spans (a right-edge colspan=2 amount covering
            # INDIVIDUAL+FAMILY of one plan) fail the majority test and keep
            # their genuine per-column attribution.
            note = is_full_width_note(col_idx, colspan, n_cols)

            for r_offset in range(rowspan):
                for c_offset in range(colspan):
                    target_row = row_idx + r_offset
                    target_col = col_idx + c_offset

                    if target_row >= len(grid) or target_col >= len(grid[0]):
                        continue

                    header_col = col_idx if note else target_col
                    row_headers, col_headers = find_headers_for_cell(grid, target_row, header_col)

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

                    is_header_echo = outcome_norm in {h.strip().lower() for h in col_headers}
                    if not is_header_echo:
                        rows_with_value.add(target_row)

    # Label-only preservation: a body row whose row-header label is present but
    # which carries no independent value would otherwise vanish entirely — the
    # data loop above emits nothing usable for it. This is how de-spanned
    # section headers arrive when an OCR/HTML pipeline drops the original
    # ``colspan``: the value column is either empty (a benefits-schedule title
    # row "2. Public transport double indemnity") or repeats the column header
    # (a "24. COVID-19 Coverage Extension | Sum Insured" row, whose echoed value
    # clean_rules strips, taking the label with it). It is structurally
    # indistinguishable from a leaf row with a genuinely missing value, so we
    # preserve the label verbatim rather than fabricate a section breadcrumb.
    for row_idx in range(len(grid)):
        if row_idx in rows_with_value:
            continue
        # A label-only row promoted to a row-group ancestor (scope="rowgroup")
        # is threaded into the value lines beneath it — emitting it here too
        # would duplicate it as an orphan label.
        if any(grid[row_idx][c].get("scope") == "rowgroup" for c in range(n_cols)):
            continue
        # Anchor the rule at the row's data column so it satisfies the quality
        # gate's "rules originate from <td>" invariant. A row with no <td> at
        # all is a true full-width <th colspan> divider — already handled as a
        # row-group ancestor upstream — so we leave it alone.
        anchor_col = next((c for c in range(n_cols) if grid[row_idx][c]["type"] == "td"), None)
        if anchor_col is None:
            continue
        label_parts: List[str] = []
        for col_idx in range(n_cols):
            cell = grid[row_idx][col_idx]
            if cell["type"] != "th":
                continue
            if cell.get("is_thead", False) or cell.get("is_header_row", False):
                continue
            if cell.get("is_span_copy", False):
                continue
            text = (cell.get("text") or "").strip()
            if not text:
                continue
            label_parts.append(text)
        if not label_parts:
            continue
        rules.append(
            LogicRule(
                outcome=" > ".join(label_parts),
                position=(row_idx, anchor_col),
                row_headers=(),
                col_headers=(),
                origin=(row_idx, anchor_col),
                is_label=True,
            )
        )

    return rules


def _mark_rowgroup_bands(grid) -> None:
    """Promote value-region-wide body dividers to ``<th scope="rowgroup">`` so
    the maze threads them into each value line's row path as bounded, nested
    row-group ancestors — the row-side counterpart of the multi-level column
    header path.

    A candidate is a body cell whose span reaches the last column and covers a
    majority of the grid (``is_full_width_note`` geometry): a section band
    (full width) or a group header / description spanning the value region. A
    candidate is promoted only when its extent contains at least one real data
    row — so a standalone trailing note (which groups nothing) is left as a
    note and still emitted, never stranded as an empty-extent rowgroup. Nested
    candidates are bounded by colspan: a band's extent ends at the next
    candidate whose span is equal or wider. Cells already marked
    ``scope="rowgroup"`` by the source are honored as-is.
    """
    if not grid or not grid[0]:
        return
    n_cols = len(grid[0])
    # Column-header texts. A full-width body cell that merely repeats a column
    # header (a units caption like "(In thousands, except per share data)"
    # reprinted between sections) is an annotation, not a row-group divider —
    # promoting it would stamp it onto every row path (where it is already noise
    # in the column path). Exclude such echoes.
    header_texts = {
        (cell.get("text") or "").strip().lower()
        for row in grid
        for cell in row
        if cell and cell.get("is_thead") and (cell.get("text") or "").strip()
    }
    candidates = []  # (row, col, colspan)
    for r in range(len(grid)):
        for c in range(n_cols):
            cell = grid[r][c]
            if not cell or cell.get("is_span_copy"):
                continue
            if cell.get("is_thead") or cell.get("is_header_row"):
                continue
            text = (cell.get("text") or "").strip()
            if not text:
                continue
            if text.lower() in header_texts:
                continue
            if is_full_width_note(c, cell.get("colspan", 1), n_cols):
                candidates.append((r, c, cell.get("colspan", 1)))
    candidate_rows = {r for (r, _c, _cs) in candidates}

    def _next_band_below(after_row: int, min_colspan: int) -> int:
        for rr in range(after_row + 1, len(grid)):
            if any(r == rr and cs >= min_colspan for (r, _c, cs) in candidates):
                return rr
        return len(grid)

    for r, c, cs in candidates:
        extent_end = _next_band_below(r, cs) - 1
        has_data_row = False
        for rr in range(r + 1, extent_end + 1):
            if rr in candidate_rows:
                continue
            if any(
                grid[rr][cc]["type"] == "td" and (grid[rr][cc].get("text") or "").strip()
                for cc in range(n_cols)
            ):
                has_data_row = True
                break
        if not has_data_row:
            continue
        for cc in range(c, min(c + cs, n_cols)):
            grid[r][cc]["type"] = "th"
            grid[r][cc]["scope"] = "rowgroup"


def _mark_label_only_rowgroups(grid) -> None:
    """Promote *label-only rows* to ``<th scope="rowgroup">`` so the maze threads
    them into each value line's row path, the row-side counterpart of the
    full-width band handled by :func:`_mark_rowgroup_bands`.

    A label-only row is a body row whose value (``<td>``) columns are all empty
    while a leading label column carries text — the ``Label | Value`` form
    pervasive in financial/insurance schedules (``9. Trip Cancellation | (empty)``
    above its value rows). Unlike a full-width band the label cell does *not*
    span the value region; the other columns are simply empty, so
    ``is_full_width_note`` geometry never sees it. Without this pass the row is
    emitted as an orphaned ``is_label`` rule and the values beneath it lose their
    group identity.

    Detection is geometric, not flag-based: a row with no value-bearing ``<td>``
    but exactly one non-empty body ``<th>`` label source cell. (Row-label
    columns are already promoted to ``<th scope="row">`` upstream — Signal A/B/C
    in grid_parser and simple_repair — so "no non-empty ``<td>``" means "no
    value".)

    The single-label-cell requirement is what separates a group header from a
    data row whose *designated* value columns merely happen to be empty. A genuine
    group header carries one title ("9. Trip Cancellation", possibly spanning the
    first N>1 columns via one ``colspan`` cell). A data row whose value columns
    are blank ("Average: | 80.2 | 10.7 | 3.3", or a summary row under a header
    that over-promoted numeric columns to row labels) spreads several distinct
    values across its label cells — threading those as a group path would invent
    a breadcrumb and misattribute it to the rows below. Such rows stay on the
    ``is_label`` preservation path, unchanged.

    Stacking and extent (no content-aware level inference):

    * A maximal run of *consecutive* label-only rows forms one header stack. Its
      members are threaded as nested ancestors in row order — a title followed by
      a description (``10. Travel Delay`` then ``If the departure…``) both land in
      the path, title first.
    * A stack's extent runs from just below the stack down to the row before the
      next stack OR the next full-width band, whichever comes first — so a group
      never leaks into the next line-item or across a section divider.
    * A stack is promoted only when its extent holds a real value row (parity
      with the full-width-note guard): a trailing label that groups nothing is
      left for the ``is_label`` preservation path, never stranded as an
      empty-extent rowgroup.

    The stored ``rowgroup_extent_end`` is what the maze honors for these bands;
    full-width bands keep their colspan-bounded extent. The two compose: a
    section band (wider) and a label-only group (narrower) nest consistently.
    """
    if not grid or not grid[0]:
        return
    n_rows = len(grid)
    n_cols = len(grid[0])

    def _is_body_row(r: int) -> bool:
        return not any(
            grid[r][c].get("is_thead") or grid[r][c].get("is_header_row") for c in range(n_cols)
        )

    def _has_value(r: int) -> bool:
        return any(
            grid[r][c]["type"] == "td" and (grid[r][c].get("text") or "").strip()
            for c in range(n_cols)
        )

    def _label_cols(r: int) -> List[int]:
        cols: List[int] = []
        for c in range(n_cols):
            cell = grid[r][c]
            if cell.get("is_thead") or cell.get("is_header_row"):
                continue
            if cell["type"] != "th":
                continue
            if cell.get("is_span_copy"):
                # A span copy of a label cell originating in this same row is
                # part of a multi-column label (label spans the first N>1
                # columns); promote it too. A span copy reaching down from a
                # row above is not a label of this row.
                origin = cell.get("origin", (r, c))
                if origin[0] != r:
                    continue
                if not (grid[origin[0]][origin[1]].get("text") or "").strip():
                    continue
            elif not (cell.get("text") or "").strip():
                continue
            cols.append(c)
        return cols

    def _single_label_origin(r: int) -> bool:
        # A group header is exactly one label source cell (a title, possibly
        # colspan'd). More than one distinct non-empty label cell means a data
        # row, not a divider — do not thread it.
        origins = set()
        for c in _label_cols(r):
            cell = grid[r][c]
            origins.add(cell.get("origin", (r, c)) if cell.get("is_span_copy") else (r, c))
        return len(origins) == 1

    # A row already carrying a rowgroup cell (a full-width band promoted above,
    # or a source scope="rowgroup") is a boundary, not a label-only candidate.
    band_rows = {
        r for r in range(n_rows) for c in range(n_cols) if grid[r][c].get("scope") == "rowgroup"
    }

    is_label_row = [
        _is_body_row(r)
        and r not in band_rows
        and not _has_value(r)
        and bool(_label_cols(r))
        and _single_label_origin(r)
        for r in range(n_rows)
    ]

    r = 0
    while r < n_rows:
        if not is_label_row[r]:
            r += 1
            continue
        # Gather the maximal consecutive run of label-only rows.
        s_start = r
        while r + 1 < n_rows and is_label_row[r + 1]:
            r += 1
        s_end = r
        r += 1  # advance past the stack for the outer loop

        # Extent: down to the row before the next boundary (next label stack or
        # full-width band). Bounded by a value row's presence.
        extent_end = n_rows - 1
        for rr in range(s_end + 1, n_rows):
            if is_label_row[rr] or rr in band_rows:
                extent_end = rr - 1
                break
        has_data_row = any(_has_value(rr) for rr in range(s_end + 1, extent_end + 1))
        if not has_data_row:
            continue

        for rr in range(s_start, s_end + 1):
            for c in _label_cols(rr):
                grid[rr][c]["type"] = "th"
                grid[rr][c]["scope"] = "rowgroup"
                grid[rr][c]["rowgroup_extent_end"] = extent_end


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

    _mark_rowgroup_bands(grid)
    _mark_label_only_rowgroups(grid)
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
        if not isinstance(table, Tag):
            continue
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
            caption_text = (clean_text(caption_tag.get_text()) if caption_tag else "") or None
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
