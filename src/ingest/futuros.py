"""Futuros de dólar (A3 Mercados).

No hay acceso programático (respuesta del usuario, 2026-10-30). La depreciación esperada se toma
de la mediana del REM (settings.yaml: modeling.expected_depreciation.source = rem_median).
Este módulo existe para que el hueco quede explícito y no se reemplace en silencio.
"""

from __future__ import annotations

from .common import Snapshot, SourceError, load_yaml


def ingest(snap: Snapshot) -> None:
    source = load_yaml("settings.yaml")["modeling"]["expected_depreciation"]["source"]
    if source != "rem_median":
        raise SourceError("Se pidió depreciación esperada desde futuros, pero no hay fuente de futuros configurada.")
    print("  Futuros: sin acceso; depreciación esperada desde el REM (decisión registrada).")
