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


def assert_grid_size(rows: int, cols: int) -> None:
    """Raise if a logical grid shape would exceed the configured cell cap."""
    total_cells = rows * cols
    if total_cells > MAX_GRID_CELLS:
        raise TableTooLargeError(
            f"expanded grid would be {rows} x {cols} "
            f"= {total_cells} cells (cap {MAX_GRID_CELLS})"
        )
