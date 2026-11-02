"""Ensambles (Fase 4). Protocolo en DECISIONS.md.

En cada origen o y para cada grupo (F1, F2, todos):
1. Errores pasados: pronósticos del grupo con mes objetivo en (o-12, o] y h en {1,2,3}, evaluados contra
   el observado de la vintage del origen o (X13 truncado en o). Nada posterior a o.
2. Se eligen los 3 modelos de menor ECM entre los que tienen el mismo conjunto completo de errores.
3. Esquema "w": pesos >= 0 que suman 1 y minimizan el ECM de la combinación en esos errores (nota 48).
   Esquema "avg": promedio simple de los 3.
4. El pronóstico combinado (punto y cuantiles) es el promedio ponderado de los pronósticos en o.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

QCOLS = ["q0.025", "q0.16", "q0.5", "q0.84", "q0.975", "point"]
TOP_K = 3
WINDOW = 12
MIN_ERRORS = 6


def optimal_weights(F: np.ndarray, y: np.ndarray) -> np.ndarray:
    k = F.shape[1]
    if k == 1:
        return np.ones(1)
    obj = lambda w: np.mean((F @ w - y) ** 2)
    res = minimize(obj, np.full(k, 1 / k), method="SLSQP", bounds=[(0, 1)] * k,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def combine(fc: pd.DataFrame, vint: pd.DataFrame, groups: dict[str, list[str]],
            only_origins: list | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """fc: pronósticos de una variable y un escenario. vint: pseudo-vintages (origin, period, y_<var>).
    only_origins: calcular el ensamble solo en esos orígenes (Fase 5: el origen de la corrida)."""
    var = fc["variable"].iloc[0]
    ycol = f"y_{var}"
    rows, log = [], []
    origins = sorted(fc["origin"].unique()) if only_origins is None else list(only_origins)
    for o in origins:
        obs_o = vint[vint["origin"] == o].set_index("period")[ycol] if ycol in vint else pd.Series(dtype=float)
        past = fc[(fc["target"] <= o) & (fc["target"] > o - WINDOW) & (fc["h"] <= 3)].copy()
        past["err"] = past["point"] - past["target"].map(obs_o)
        past = past.dropna(subset=["err"])
        now = fc[fc["origin"] == o]
        for gname, members in groups.items():
            p = past[past["model"].isin(members)]
            if p.empty:
                continue
            piv = p.pivot_table(index=["origin", "target"], columns="model", values="point")
            piv = piv.dropna(axis=1, thresh=int(0.9 * len(piv))).dropna()
            if len(piv) < MIN_ERRORS or piv.shape[1] == 0:
                continue
            y = pd.Series(piv.index.get_level_values("target").map(obs_o).to_numpy(dtype=float), index=piv.index)
            mse = ((piv.sub(y, axis=0)) ** 2).mean().sort_values()
            sel = list(mse.index[:TOP_K])
            for scheme in ["w", "avg"]:
                w = optimal_weights(piv[sel].to_numpy(), y.to_numpy()) if scheme == "w" else np.full(len(sel), 1 / len(sel))
                cur = now[now["model"].isin(sel)]
                if cur["model"].nunique() < len(sel):
                    continue
                wmap = dict(zip(sel, w))
                for tm, g in cur.groupby("target"):
                    ww = g["model"].map(wmap).to_numpy()
                    row = {c: float(ww @ g[c].to_numpy()) for c in QCOLS}
                    row.update({"origin": o, "target": tm, "h": int(g["h"].iloc[0]), "model": f"ENS_{gname}_{scheme}",
                                "group": "ensemble", "variable": var, "scenario": g["scenario"].iloc[0]})
                    rows.append(row)
                log.append({"origin": o, "variable": var, "scenario": now["scenario"].iloc[0], "group": gname,
                            "scheme": scheme, "n_errors": len(piv), **{f"m{i}": m for i, m in enumerate(sel)},
                            **{f"w{i}": float(x) for i, x in enumerate(w)}})
    return pd.DataFrame(rows), pd.DataFrame(log)
