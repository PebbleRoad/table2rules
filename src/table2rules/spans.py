"""Shared span limits for table expansion.

Both repair and parsing expand ``rowspan`` / ``colspan`` into logical grid
positions. Keep all coercion and size checks here so adversarial markup is
bounded before either phase allocates span-derived structures.
"""

from __future__ import annotations

from .errors import TableTooLargeError

# Guards against adversarial HTML. Normal tables never approach these.
MAX_SPAN = 1000
MAX_GRID_CELLS = 1_000_000


def clamped_span(raw) -> int:
    """Coerce a raw rowspan/colspan attribute to a safe int in [1, MAX_SPAN]."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    if value < 1:
        return 1
    if value > MAX_SPAN:
        return MAX_SPAN
    return value


def is_full_width_note(col_idx: int, colspan: int, n_cols: int) -> bool:
    """True when a wide data cell is structurally a full-width note/description.

    A ``<td>`` that reaches the last column AND spans a majority of the grid's
    columns (e.g. a benefit name or a "If the departure…" sentence spanning the
    whole value region of a plan×cover matrix) is a description, not a
    per-column value. Such a cell must collapse to a single rule rather than fan
    out across every spanned column — and the confidence gate must count it as a
    single candidate position to match. Legitimate narrow spans (a right-edge
    ``colspan=2`` amount covering two sub-columns of one group) fail the majority
    test and keep their per-column fan-out.
    """
    return colspan > 1 and (col_idx + colspan == n_cols) and (colspan * 2 > n_cols)


def assert_grid_size(rows: int, cols: int) -> None:
    """Raise if a logical grid shape would exceed the configured cell cap."""
    total_cells = rows * cols
    if total_cells > MAX_GRID_CELLS:
        raise TableTooLargeError(
            f"expanded grid would be {rows} x {cols} = {total_cells} cells (cap {MAX_GRID_CELLS})"
        )
