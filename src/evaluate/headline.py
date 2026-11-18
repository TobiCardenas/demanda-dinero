"""Revisión del modelo titular (nov-2026): python -m src.evaluate.headline

Backtest de los candidatos R0..R5 fijados en DECISIONS.md sobre el archivo pseudo fuera de muestra
(orígenes feb-21 a ago-26). Las reglas adaptativas (R2, R5) usan en cada origen solo errores pasados,
evaluados contra la vintage de ese origen. Elección con la muestra de desarrollo; 2026 se reporta aparte.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.evaluate import vintages
from src.ingest.common import ROOT
from src.transform import model_data as md

VARS = ["m2", "circ", "dav"]
DEV_END, TEST_START = pd.Period("2025-10", "M"), pd.Period("2025-11", "M")
WINDOW, THRESH, MIN_PAIRS = 12, 1.10, 6
CANDIDATES = {"R0": "ensamble F1 (actual)", "R1": "igual que hoy (RW)", "R2": "semáforo en tiempo real",
              "R3": "ensamble de todos", "R4": "50/50 ensamble F1 y RW", "R5": "pesos inversos al ECM"}
OUT = ROOT / "reports" / "revision_titular"


def adaptive_stats(fc: pd.DataFrame, vint: pd.DataFrame, var: str, o: pd.Period) -> tuple[float, float, int]:
    """ECM del ensamble F1 y de la RW en los 12 meses previos a o (h<=3), contra la vintage de o."""
    obs = vint[vint["origin"] == o].set_index("period")[f"y_{var}"]
    past = fc[(fc["target"] <= o) & (fc["target"] > o - WINDOW) & (fc["h"] <= 3)]
    piv = past.pivot_table(index=["origin", "target"], columns="model", values="point")
    if not {"ENS_F1_avg", "RW"} <= set(piv.columns):
        return np.nan, np.nan, 0
    piv = piv[["ENS_F1_avg", "RW"]].dropna()
    y = piv.index.get_level_values("target").map(obs).to_numpy(dtype=float)
    ok = ~np.isnan(y)
    if ok.sum() < MIN_PAIRS:
        return np.nan, np.nan, int(ok.sum())
    e = piv.to_numpy()[ok] - y[ok, None]
    mse = (e ** 2).mean(axis=0)
    return float(mse[0]), float(mse[1]), int(ok.sum())


def candidates(arch: pd.DataFrame, vint: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, log = [], []
    for var in VARS:
        fc = arch[(arch["variable"] == var) & (arch["scenario"] == "exante_rem")
                  & arch["model"].isin(["ENS_F1_avg", "RW", "ENS_all_avg"])]
        piv = fc.pivot_table(index=["origin", "target", "h"], columns="model", values="point").dropna()
        for o, g in piv.groupby(level="origin"):
            mse_e, mse_rw, n = adaptive_stats(fc, vint, var, o)
            ratio = np.sqrt(mse_e / mse_rw) if n >= MIN_PAIRS else np.nan
            use_rw = bool(n >= MIN_PAIRS and ratio > THRESH)
            w = (1 / mse_e) / (1 / mse_e + 1 / mse_rw) if n >= MIN_PAIRS else 1.0
            log.append({"variable": var, "origin": o, "ratio_12m": ratio, "pares": n, "R2_usa_RW": use_rw,
                        "R5_peso_ens": w})
            for (oo, t, h), r in g.iterrows():
                e, rw, al = r["ENS_F1_avg"], r["RW"], r["ENS_all_avg"]
                rows.append({"variable": var, "origin": oo, "target": t, "h": h,
                             "R0": e, "R1": rw, "R2": rw if use_rw else e, "R3": al,
                             "R4": 0.5 * e + 0.5 * rw, "R5": w * e + (1 - w) * rw})
    return pd.DataFrame(rows), pd.DataFrame(log)


def score(c: pd.DataFrame, obs: pd.DataFrame, sample: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = c[sample].copy()
    d["obs"] = [obs[f"y_{v}"].get(t, np.nan) for v, t in zip(d["variable"], d["target"])]
    d = d.dropna(subset=["obs"])
    rel = {}
    for k in CANDIDATES:
        err = d[k] - d["obs"]
        rmse = (err ** 2).groupby([d["variable"], d["h"]]).mean() ** 0.5
        rmse_rw = ((d["R1"] - d["obs"]) ** 2).groupby([d["variable"], d["h"]]).mean() ** 0.5
        rel[k] = rmse / rmse_rw
    rel = pd.DataFrame(rel)
    n = d.groupby(["variable", "h"]).size().rename("N")
    by_var = rel.groupby(level="variable").mean()
    summary = pd.DataFrame({"criterio (prom. variables y h)": by_var.mean(), "peor variable": by_var.max()})
    for v in VARS:
        if v in by_var.index:
            summary[f"{v} (prom. h)"] = by_var.loc[v]
    summary["descripción"] = pd.Series(CANDIDATES)
    return summary, rel.join(n)


def choose(summary: pd.DataFrame) -> str:
    best = summary["criterio (prom. variables y h)"].min()
    tied = summary[summary["criterio (prom. variables y h)"] <= best + 0.02]
    return tied["peor variable"].idxmin()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from src.run_monthly import load_archive

    arch = load_archive()
    arch = arch[arch["realtime"].astype(str) == "pseudo"]
    vint = vintages.load()
    panel = md.load_panel()
    obs = md.build(panel.index.max(), panel).data
    c, log = candidates(arch, vint)
    dev_s, dev_d = score(c, obs, c["target"] <= DEV_END)
    tst_s, tst_d = score(c, obs, c["target"] >= TEST_START)
    winner = choose(dev_s)
    c.to_csv(OUT / "candidatos.csv", index=False)
    log.to_csv(OUT / "regla_adaptativa.csv", index=False)
    sw = log[log["R2_usa_RW"]].groupby("variable")["origin"].agg(lambda s: ", ".join(map(str, s)))
    L = ["# Revisión del modelo titular", "",
         "Protocolo fijado antes de calcular (DECISIONS.md, 2026-11-18). RMSE relativo a «igual que hoy» (< 1 = mejor), "
         "escenario REM, filas donde existen todos los candidatos.", "",
         "## Muestra de desarrollo (objetivo ≤ oct-25): decide", "", dev_s.round(3).to_markdown(), "",
         f"**Elegido por la regla: {winner} — {CANDIDATES[winner]}.**", "",
         "N por variable y horizonte (desarrollo):", "",
         dev_d["N"].unstack("h").to_markdown(), "",
         "## Test (objetivo ≥ nov-25): se reporta, no decide", "", tst_s.round(3).to_markdown(), "",
         "N (test):", "", tst_d["N"].unstack("h").to_markdown(), "",
         "## Cuándo la regla R2 (semáforo) habría pasado a «igual que hoy»", ""]
    L += [f"- {v}: {sw.get(v, 'nunca')}" for v in VARS]
    (OUT / "revision.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
