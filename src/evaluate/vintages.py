"""Pseudo-vintages: la serie s.e. tal como se veía en cada origen (X13 truncado). python -m src.evaluate.vintages

Sirve para que los pesos de ensamble y la selección en un origen usen solo el "observado" de ese origen,
y como vintage contemporánea en la descomposición de revisiones. Salida: data/processed/pseudo_vintages.csv
(origin, period, y_<variable>...). Regenerable.
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from src.ingest.common import ROOT
from src.transform import model_data as md

VARS = ["y_circ", "y_dav", "y_m2", "y_m2priv", "y_m3", "y_m2amp"]


def one(origin_str: str) -> pd.DataFrame:
    origin = pd.Period(origin_str, "M")
    d = md.build(origin).data
    out = d.reindex(columns=VARS).copy()
    out.insert(0, "origin", origin)
    out.index.name = "period"
    return out.reset_index()


def build(first: str = "2021-01", last: str | None = None, workers: int | None = None) -> pd.DataFrame:
    panel = md.load_panel()
    last_p = pd.Period(last, "M") if last else panel["emae_orig"].dropna().index.max()
    origins = [str(o) for o in pd.period_range(first, last_p, freq="M")]
    with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
        parts = list(ex.map(one, origins))
    return pd.concat(parts, ignore_index=True)


def load() -> pd.DataFrame:
    v = pd.read_csv(ROOT / "data" / "processed" / "pseudo_vintages.csv")
    v["origin"] = pd.PeriodIndex(v["origin"], freq="M")
    v["period"] = pd.PeriodIndex(v["period"], freq="M")
    return v


def main() -> int:
    v = build()
    v.to_csv(ROOT / "data" / "processed" / "pseudo_vintages.csv", index=False)
    print(f"{v['origin'].nunique()} vintages, {len(v)} filas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
