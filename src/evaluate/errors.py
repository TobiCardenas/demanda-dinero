"""Errores y métricas puntuales por horizonte.

Convención: error = pronóstico - observado (última vintage), en log de saldos reales s.e. (x100 = %).
El nivel del origen en la vintage del origen es el pronóstico de la caminata aleatoria, de ahí sale el
cambio pronosticado para el acierto direccional.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def attach_observed(fc: pd.DataFrame, latest: pd.DataFrame) -> pd.DataFrame:
    """latest: DataFrame con columnas y_<variable> (última vintage), índice PeriodIndex."""
    out = fc.copy()
    obs = latest.stack().rename("obs").reset_index()
    obs.columns = ["target", "var_col", "obs"]
    obs["variable"] = obs["var_col"].str.removeprefix("y_")
    out = out.merge(obs[["target", "variable", "obs"]], on=["target", "variable"], how="left")
    o0 = obs.rename(columns={"target": "origin", "obs": "obs_origin_latest"})[["origin", "variable", "obs_origin_latest"]]
    out = out.merge(o0, on=["origin", "variable"], how="left")
    rw = out[out["model"] == "RW"][["origin", "variable", "scenario", "target", "point"]].rename(
        columns={"point": "y0_origin_vintage"})
    out = out.merge(rw, on=["origin", "variable", "scenario", "target"], how="left")
    out["error"] = out["point"] - out["obs"]
    out["fc_change"] = out["point"] - out["y0_origin_vintage"]
    out["obs_change"] = out["obs"] - out["obs_origin_latest"]
    return out


def point_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Por (variable, scenario, model, h): N, MAE, RMSE, relativos a RW y acierto direccional."""
    g = df.dropna(subset=["error"]).groupby(["variable", "scenario", "model", "h"])
    m = g.agg(N=("error", "size"), MAE=("error", lambda e: 100 * e.abs().mean()),
              RMSE=("error", lambda e: 100 * np.sqrt((e ** 2).mean())), bias=("error", lambda e: 100 * e.mean()))
    d = df.dropna(subset=["error"]).copy()
    d["dir_hit"] = np.sign(d["fc_change"].round(10)) == np.sign(d["obs_change"].round(10))
    m["dir_acc"] = d.groupby(["variable", "scenario", "model", "h"])["dir_hit"].mean()
    rw = m.xs("RW", level="model")[["MAE", "RMSE"]].rename(columns={"MAE": "MAE_rw", "RMSE": "RMSE_rw"})
    m = m.join(rw, on=["variable", "scenario", "h"])
    m["MAE_rel"] = m["MAE"] / m["MAE_rw"]
    m["RMSE_rel"] = m["RMSE"] / m["RMSE_rw"]
    return m.drop(columns=["MAE_rw", "RMSE_rw"]).reset_index()
