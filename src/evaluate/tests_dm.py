"""Diebold-Mariano con corrección de Harvey-Leybourne-Newbold (pérdida cuadrática)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import t as student_t


def dm_hln(e_model: np.ndarray, e_bench: np.ndarray, h: int) -> tuple[float, float, int]:
    """Estadístico, p-valor bilateral y N. d_t = e_model^2 - e_bench^2; negativo => el modelo es mejor.
    Varianza de largo plazo con autocovarianzas hasta h-1 (los errores a h pasos se superponen)."""
    d = np.asarray(e_model, float) ** 2 - np.asarray(e_bench, float) ** 2
    d = d[~np.isnan(d)]
    n = len(d)
    if n < 5:
        return np.nan, np.nan, n
    dbar = d.mean()
    dc = d - dbar
    gamma = [dc @ dc / n] + [dc[k:] @ dc[:-k] / n for k in range(1, h)]
    var = (gamma[0] + 2 * sum(gamma[1:])) / n
    if var <= 0:
        var = gamma[0] / n
    stat = dbar / np.sqrt(var)
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat *= hln
    p = 2 * (1 - student_t.cdf(abs(stat), df=n - 1))
    return float(stat), float(p), n


def dm_table(df: pd.DataFrame, bench: str = "RW") -> pd.DataFrame:
    rows = []
    d = df.dropna(subset=["error"])
    for (var, sc, h), g in d.groupby(["variable", "scenario", "h"]):
        b = g[g["model"] == bench].set_index("origin")["error"]
        for mdl, gm in g.groupby("model"):
            if mdl == bench:
                continue
            e = gm.set_index("origin")["error"]
            common = e.index.intersection(b.index).sort_values()
            stat, p, n = dm_hln(e[common].to_numpy(), b[common].to_numpy(), int(h))
            rows.append({"variable": var, "scenario": sc, "h": h, "model": mdl, "dm_stat": stat, "dm_p": p, "dm_N": n})
    return pd.DataFrame(rows)
