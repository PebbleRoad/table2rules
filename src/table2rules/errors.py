"""Public exception types for table2rules."""

from __future__ import annotations


class Table2RulesError(Exception):
    """Base class for exceptions raised by table2rules."""


class TableTooLargeError(Table2RulesError):
    """Raised when a table's span-expanded grid would exceed configured caps.

    Typically produced by malformed or adversarial HTML (e.g. a cell with
    ``rowspan=99999`` / ``colspan=99999``). Callers running on untrusted input
    should treat this as a signal to skip or degrade rather than hang on
    allocation.
    """
