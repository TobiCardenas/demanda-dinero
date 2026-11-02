"""Descomposición del error de pronóstico (en log de saldos reales s.e.).

    total     = pronóstico ex ante (REM) - observado última vintage
    escenario = pronóstico ex ante - pronóstico con escenario realizado
    modelo    = pronóstico con escenario realizado - observado última vintage   (columna model_err)
    revisión  = observado vintage contemporánea - observado última vintage

total = escenario + modelo. La revisión se reporta aparte, como pide el plan.

Vintage contemporánea: hay un solo snapshot, así que se aproxima con el valor s.e. que daba X13 sobre la
serie truncada en el mes objetivo. Capta las revisiones de factores estacionales; no las de datos crudos
(los saldos monetarios y el IPC no se revisan; el EMAE sí, pero no entra en y).
También se reporta la revisión del nivel del origen y el error del modelo en cambios, que no depende de
cuánto se revisó el punto de partida.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.transform import model_data as md
from src.transform.deflate import real_balance
from src.transform.seasonal import seasadj_log


def contemporaneous_sa(component: str, months: pd.PeriodIndex, panel: pd.DataFrame | None = None) -> pd.Series:
    panel = md.load_panel() if panel is None else panel
    rb = np.log(real_balance(panel[md.COMPONENTS[component]], panel["ipc_headline"]))
    rb.name = f"y_{component}_headline"
    return pd.Series({m: seasadj_log(rb, m).iloc[-1] for m in months}, name=f"y_{component}_contemp")


def log_sum(*logs) -> np.ndarray:
    return np.log(sum(np.exp(np.asarray(x, dtype=float)) for x in logs))


def decompose(fc_ex: pd.Series, fc_re: pd.Series, obs_latest: pd.Series, obs_contemp: pd.Series,
              y0_origin_vintage: float, y0_latest: float) -> pd.DataFrame:
    idx = fc_ex.index
    out = pd.DataFrame(index=idx)
    out["fc_exante"], out["fc_realized"] = fc_ex, fc_re
    out["obs_latest"], out["obs_contemp"] = obs_latest.reindex(idx), obs_contemp.reindex(idx)
    out["total"] = out["fc_exante"] - out["obs_latest"]
    out["scenario"] = out["fc_exante"] - out["fc_realized"]
    out["model_err"] = out["fc_realized"] - out["obs_latest"]
    out["revision"] = out["obs_contemp"] - out["obs_latest"]
    out["y0_origin_vintage"], out["y0_latest"] = y0_origin_vintage, y0_latest
    out["revision_origin"] = y0_origin_vintage - y0_latest
    out["model_change"] = (out["fc_realized"] - y0_origin_vintage) - (out["obs_latest"] - y0_latest)
    out["total_change"] = (out["fc_exante"] - y0_origin_vintage) - (out["obs_latest"] - y0_latest)
    return out
