"""Exporter protocol and registry for table2rules.

Exporters turn a list of LogicRule objects (one per cell) into a list of
output lines. Third parties can add new formats by subclassing Exporter
and calling register_exporter().
"""

from __future__ import annotations

from typing import Dict, List, Protocol

from ..models import LogicRule


class Exporter(Protocol):
    name: str

    def export_rules(self, rules: List[LogicRule]) -> List[str]: ...

    def export_flat(self, cell_rows: List[List[str]]) -> List[str]: ...


_REGISTRY: Dict[str, Exporter] = {}


def register_exporter(exporter: Exporter) -> None:
    _REGISTRY[exporter.name] = exporter


def get_exporter(name_or_instance) -> Exporter:
    if isinstance(name_or_instance, str):
        if name_or_instance not in _REGISTRY:
            raise ValueError(
                f"unknown exporter {name_or_instance!r}; registered: {sorted(_REGISTRY)}"
            )
        return _REGISTRY[name_or_instance]
    return name_or_instance


def available_exporters() -> List[str]:
    return sorted(_REGISTRY)
