"""Control de frescura de las fuentes (Fase 5). Si una serie supera su rezago admitido, la corrida falla."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from src.ingest.common import load_yaml

SERIES = {"money": "m2_trans_priv", "ipc_headline": "ipc_headline", "emae_orig": "emae_orig",
          "rate_pf30": "rate_pf30", "transf_push_ars_monto": "transf_push_ars_monto"}


def check(panel: pd.DataFrame, gdp: pd.DataFrame, rem: pd.DataFrame, asof: dt.date) -> tuple[list[str], pd.DataFrame]:
    """Devuelve (errores, tabla de últimos datos y rezagos)."""
    limits = load_yaml("settings.yaml")["freshness"]
    run_m, run_q = pd.Period(asof, "M"), pd.Period(asof, "Q")
    rows, errors = [], []
    for key, col in SERIES.items():
        last = panel[col].dropna().index.max()
        rows.append({"serie": col, "último dato": str(last), "rezago": (run_m - last).n, "máximo": limits[key]})
    last_rem = rem["survey"].max()
    rows.append({"serie": "REM (relevamiento)", "último dato": str(last_rem), "rezago": (run_m - last_rem).n,
                 "máximo": limits["rem_survey"]})
    last_q = gdp["gdp_nominal_q"].dropna().index.max()
    rows.append({"serie": "PIB trimestral (trimestres)", "último dato": str(last_q), "rezago": (run_q - last_q).n,
                 "máximo": limits["gdp_quarterly"]})
    tab = pd.DataFrame(rows)
    tab["ok"] = tab["rezago"] <= tab["máximo"]
    for _, r in tab[~tab["ok"]].iterrows():
        errors.append(f"{r['serie']}: último dato {r['último dato']}, rezago {r['rezago']} > {r['máximo']} admitido")
    return errors, tab
