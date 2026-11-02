"""Relevamiento de Expectativas de Mercado (REM) del BCRA: archivo histórico completo."""

from __future__ import annotations

import io

import pandas as pd

from .common import Snapshot, SourceError, http_get, load_yaml


def ingest(snap: Snapshot) -> None:
    spec = load_yaml("series.yaml")["bcra_xlsx"]["rem_historico"]
    content = http_get(spec["url"])
    snap.write("bcra_rem_historico.xlsx", content, source=spec["url"])
    last = parse(snap)["forecast_date"].max()
    print(f"  REM histórico: último relevamiento {last:%Y-%m-%d}")


def parse(snap: Snapshot) -> pd.DataFrame:
    """Formato largo: una fila por (fecha de relevamiento, variable, referencia, período)."""
    spec = load_yaml("series.yaml")["bcra_xlsx"]["rem_historico"]
    x = pd.read_excel(io.BytesIO(snap.path("bcra_rem_historico.xlsx").read_bytes()),
                      sheet_name=spec["sheet"], header=1)
    cols = list(x.columns[:9])
    expected = ["Fecha de pronóstico", "Variable", "Referencia", "Período", "Mediana", "Promedio"]
    if [str(c).strip() for c in cols[:6]] != expected:
        raise SourceError(f"REM: cambió el encabezado: {cols}")
    x = x.iloc[:, :9]
    x.columns = ["forecast_date", "variable", "reference", "period", "median", "mean", "sd", "max", "min"]
    x = x.dropna(subset=["forecast_date", "variable"])
    x["forecast_date"] = pd.to_datetime(x["forecast_date"])
    x["variable"] = x["variable"].astype(str).str.strip()
    x["reference"] = x["reference"].astype(str).str.strip()
    return x.reset_index(drop=True)
