"""Datos de modelado en un origen y escenarios (ex ante REM y realizado).

Todo lo que entra a fit() se construye con datos <= origin: X13 sobre series truncadas,
estandarización de alt con media y desvío de la muestra hasta el origen.

Variables (mensuales, PeriodIndex):
  y_circ, y_dav, y_m2  log de saldos reales s.e. (millones ARS de dic-2016)
  y_m2priv, y_m3       M2 privado y M3 privado (hipótesis 6)
  y_m2amp              log[exp(y_m2) + FCI vía billeteras real]: el M2 transaccional se desestacionaliza y
                       los FCI (desde ago-23, sin estacionalidad estimable) se suman sin ajuste
  act                  log EMAE s.e.
  co                   ln(1 + i_m), plazo fijo 30 días
  alt                  log[(transf. push + PCT) / (EMAE x IPC)] s.e., estandarizado
  dep_exp              ln(TC REM para t+1 / A3500 promedio de t), relevamiento de fin de t
  d_*                  dummies de impulso (settings.yaml)
  log_p                log IPC (para pasar a nominal)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.ingest.common import ROOT, load_yaml
from src.transform.deflate import opportunity_cost, real_balance
from src.transform.seasonal import seasadj_log

COMPONENTS = {"circ": "circ_public", "dav": "dav_nr", "m2": "m2_trans_priv",
              # Hipótesis 6 (agregados alternativos, Fase 4)
              "m2priv": "m2_priv", "m3": "m3_priv"}
TC_VAR = "Tipo de cambio nominal"
IPC_VAR = "Precios minoristas (IPC nivel general; INDEC)"
GDP_VAR = "PIB a precios constantes"


def load_panel() -> pd.DataFrame:
    p = pd.read_csv(ROOT / "data" / "processed" / "panel_monthly.csv", index_col=0)
    p.index = pd.PeriodIndex(p.index, freq="M")
    return p


def load_rem() -> pd.DataFrame:
    r = pd.read_csv(ROOT / "data" / "processed" / "rem_long.csv", parse_dates=["forecast_date"])
    r["survey"] = r["forecast_date"].dt.to_period("M")
    return r


def dummies(index: pd.PeriodIndex) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    for name, d in load_yaml("settings.yaml")["break_dummies"].items():
        lo, hi = pd.Period(d["start"], "M"), pd.Period(d.get("end", d["start"]), "M")
        out[f"d_{name}"] = ((index >= lo) & (index <= hi)).astype(float)
    return out


def _monthly_points(rem: pd.DataFrame, variable: str, survey: pd.Period, ref_prefix: str) -> pd.Series:
    x = rem[(rem["survey"] == survey) & (rem["variable"] == variable)
            & (rem["reference"].str.split(";").str[0].str.strip() == ref_prefix)].copy()
    x = x[pd.to_datetime(x["period"], errors="coerce").notna()]
    return pd.Series(x["median"].astype(float).values,
                     index=pd.PeriodIndex(pd.to_datetime(x["period"]), freq="M")).sort_index()


def expected_depreciation(panel: pd.DataFrame, rem: pd.DataFrame) -> pd.Series:
    out = {}
    for survey in sorted(rem["survey"].unique()):
        tc = _monthly_points(rem, TC_VAR, survey, "$/USD")
        nxt = survey + 1
        if nxt in tc.index and survey in panel.index and pd.notna(panel.at[survey, "fx_a3500"]):
            out[survey] = np.log(tc[nxt] / panel.at[survey, "fx_a3500"])
    return pd.Series(out, name="dep_exp").sort_index()


@dataclass
class OriginData:
    origin: pd.Period
    data: pd.DataFrame
    alt_mean: float
    alt_sd: float
    opts: dict = field(default_factory=dict)


# Opciones de especificación. Los valores por defecto son las decisiones de settings.yaml y de la
# conversación del 2026-10-30; las alternativas existen para el diagnóstico de la Fase 2.
DEFAULT_OPTS = {"alt": "montos", "co": "pf30", "deflator": "headline"}


def expected_inflation(rem: pd.DataFrame) -> pd.Series:
    """Mediana REM de la inflación mensual de t+1, relevada a fin de t (en %)."""
    out = {}
    for survey in sorted(rem["survey"].unique()):
        pts = _monthly_points(rem, IPC_VAR, survey, "var. % mensual")
        if survey + 1 in pts.index:
            out[survey] = pts[survey + 1]
    return pd.Series(out, name="infl_exp").sort_index()


def _alt_raw(p: pd.DataFrame, how: str) -> pd.Series:
    nominal_act = p["emae_orig"] * p["ipc_headline"]
    if how == "montos":
        return np.log((p["transf_push_ars_monto"] + p["pct_monto"]) / nominal_act)
    if how == "montos_debito":
        return np.log((p["transf_push_ars_monto"] + p["pct_monto"] + p["debit_card_monto"]) / nominal_act)
    if how == "cantidades":
        return np.log((p["transf_push_ars_cant"] + p["pct_cant"]) / p["emae_orig"])
    raise ValueError(how)


def _co(p: pd.DataFrame, rem: pd.DataFrame, how: str) -> pd.Series:
    if how == "pf30":
        return opportunity_cost(p["rate_pf30"])
    if how == "badlar":
        return opportunity_cost(p["rate_badlar"])
    if how == "infl_exp":
        return np.log1p(expected_inflation(rem).reindex(p.index) / 100)
    raise ValueError(how)


def build(origin: pd.Period, panel: pd.DataFrame | None = None, rem: pd.DataFrame | None = None,
          opts: dict | None = None) -> OriginData:
    panel = load_panel() if panel is None else panel
    rem = load_rem() if rem is None else rem
    opts = {**DEFAULT_OPTS, **(opts or {})}
    p = panel[panel.index <= origin]
    d = pd.DataFrame(index=p.index)
    price = p["ipc_headline"] if opts["deflator"] == "headline" else p["ipc_core"]
    for short, col in COMPONENTS.items():
        rb = real_balance(p[col], price)
        if len(rb) >= 48:  # X13 necesita >= 39 obs.; 48 = mínimo del protocolo de la Fase 4
            d[f"y_{short}"] = seasadj_log(np.log(rb).rename(f"y_{short}_{opts['deflator']}"), origin)
    if "y_m2" in d and "fci_psp_saldo" in p:
        fci_real = real_balance(p["fci_psp_saldo"], price)
        d["y_m2amp"] = np.log(np.exp(d["y_m2"]) + fci_real.reindex(d.index))
    d["act"] = seasadj_log(np.log(p["emae_orig"].dropna()).rename("act"), origin)
    d["co"] = _co(p, rem, opts["co"])
    alt_sa = seasadj_log(_alt_raw(p, opts["alt"]).dropna().rename(f"alt_{opts['alt']}"), origin)
    mu, sd = alt_sa.mean(), alt_sa.std()
    d["alt"] = (alt_sa - mu) / sd
    d["alt_sa_raw"] = alt_sa
    d["dep_exp"] = expected_depreciation(p, rem)
    d["log_p"] = np.log(price)
    if opts.get("realtime_fill"):
        _fill_realtime(d, origin, rem)
    d = d.join(dummies(d.index))
    return OriginData(origin, d, mu, sd, opts)


def _fill_realtime(d: pd.DataFrame, origin: pd.Period, rem: pd.DataFrame) -> None:
    """Completa act y alt entre el último dato publicado y el origen (Fase 5, ver DECISIONS.md).
    act: PIB trimestral s.e. del REM más reciente relevado hasta el origen; alt: cambio medio de 12 meses.
    Las columnas act_filled / alt_filled marcan los meses completados."""
    d["act_filled"], d["alt_filled"] = False, False
    last_act = d["act"].last_valid_index()
    missing = [m for m in d.index if last_act < m <= origin]
    if missing:
        surveys = sorted(s for s in rem["survey"].unique() if s <= origin)
        qg = _quarter_growth(rem, surveys[-1])
        for m in missing:
            g = qg.get(m.asfreq("Q"), qg.iloc[-1])
            d.loc[m, "act"] = d.loc[m - 1, "act"] + np.log1p(g / 100) / 3
            d.loc[m, "act_filled"] = True
    hist = d["alt_sa_raw"].dropna()
    last_alt = hist.index.max()
    missing = [m for m in d.index if last_alt < m <= origin]
    if missing:
        drift = (hist.iloc[-1] - hist.iloc[-13]) / 12
        for m in missing:
            d.loc[m, "alt_sa_raw"] = d.loc[m - 1, "alt_sa_raw"] + drift
            d.loc[m, "alt_filled"] = True
        # Misma media y desvío de la estandarización (serie publicada hasta el origen).
        d.loc[missing, "alt"] = (d.loc[missing, "alt_sa_raw"] - hist.mean()) / hist.std()


# --- Escenarios ---------------------------------------------------------------------------

def scenario_realized(od: OriginData, h: int, panel: pd.DataFrame | None = None,
                      rem: pd.DataFrame | None = None) -> pd.DataFrame:
    """Trayectoria realizada de los regresores (última vintage), anclada al nivel del origen:
    se aplican los cambios de la serie s.e. con toda la muestra al nivel truncado del origen."""
    panel = load_panel() if panel is None else panel
    rem = load_rem() if rem is None else rem
    full = build(panel.index.max(), panel, rem, od.opts).data
    months = pd.period_range(od.origin + 1, periods=h, freq="M")
    last = od.data.loc[od.origin]
    sc = pd.DataFrame(index=months)
    for v in ["act", "alt_sa_raw", "log_p"]:
        chg = full[v].reindex(months) - full[v].reindex(months).shift(1)
        chg.iloc[0] = full[v].get(months[0]) - full[v].get(od.origin)
        sc[v] = last[v] + chg.cumsum()
    sc["alt"] = (sc["alt_sa_raw"] - od.alt_mean) / od.alt_sd
    sc["co"] = full["co"].reindex(months)
    sc["dep_exp"] = full["dep_exp"].reindex(months)
    sc = sc.join(dummies(months))
    if sc[["act", "co", "alt", "log_p"]].isna().any().any():
        raise ValueError(f"Escenario realizado incompleto para {months[0]}..{months[-1]}:\n{sc.isna().sum()}")
    return sc


def _quarter_growth(rem: pd.DataFrame, survey: pd.Period) -> pd.Series:
    x = rem[(rem["survey"] == survey) & (rem["variable"] == GDP_VAR)
            & rem["reference"].str.startswith("var. % trim. s.e.")]
    roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
    out = {}
    for per, val in zip(x["period"], x["median"]):
        q, yy = str(per).replace("Trim.", "").strip().split("-")
        out[pd.Period(year=2000 + int(yy), quarter=roman[q], freq="Q")] = float(val)
    return pd.Series(out).sort_index()


def scenario_rem(od: OriginData, h: int, panel: pd.DataFrame | None = None,
                 rem: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Escenario ex ante con el REM relevado a fin del mes de origen. Devuelve (escenario, notas)."""
    panel = load_panel() if panel is None else panel
    rem = load_rem() if rem is None else rem
    survey, notes = od.origin, []
    months = pd.period_range(od.origin + 1, periods=h, freq="M")
    last = od.data.loc[od.origin]
    sc = pd.DataFrame(index=months)

    infl = _monthly_points(rem, IPC_VAR, survey, "var. % mensual").reindex(months)
    if infl.isna().any():
        fill = infl.dropna().iloc[-1]
        notes.append(f"IPC REM sin dato para {list(map(str, infl[infl.isna()].index))}: se repite {fill:.2f}%")
        infl = infl.fillna(fill)
    sc["log_p"] = last["log_p"] + np.log1p(infl / 100).cumsum()

    if od.opts["co"] == "infl_exp":
        # Expectativa en t de la inflación de t+1: la trayectoria REM corrida un mes.
        nxt = _monthly_points(rem, IPC_VAR, survey, "var. % mensual").reindex(months + 1).ffill()
        sc["co"] = np.log1p(nxt.to_numpy() / 100)
        notes.append("co: inflación esperada REM de t+1 (la última, repetida si falta)")
    else:
        rate_var = "Tasa de interés (TAMAR)" if survey >= pd.Period("2024-12", "M") else "Tasa de interés (BADLAR)"
        rate_col = "rate_tamar" if "TAMAR" in rate_var else "rate_badlar"
        rate = _monthly_points(rem, rate_var, survey, "TNA").reindex(months).ffill()
        base = panel.at[od.origin, rate_col]
        target_col = "rate_pf30" if od.opts["co"] == "pf30" else "rate_badlar"
        sc["co"] = opportunity_cost(panel.at[od.origin, target_col] * rate / base)
        notes.append(f"co: {target_col} = REM {rate_var} x ({target_col} / {rate_col} en el origen = "
                     f"{panel.at[od.origin, target_col] / base:.3f})")

    qg = _quarter_growth(rem, survey)
    g_m = pd.Series({m: qg.get(m.asfreq("Q"), np.nan) for m in months})
    if g_m.isna().any():
        fill = qg.iloc[-1]
        notes.append(f"PIB REM sin trimestre para {list(map(str, g_m[g_m.isna()].index))}: se repite {fill:.2f}% t/t")
        g_m = g_m.fillna(fill)
    sc["act"] = last["act"] + np.log1p(g_m.astype(float) / 100).div(3).cumsum().values

    alt_hist = od.data["alt_sa_raw"].dropna()
    drift = (alt_hist.iloc[-1] - alt_hist.iloc[-13]) / 12
    sc["alt_sa_raw"] = last["alt_sa_raw"] + drift * np.arange(1, h + 1)
    sc["alt"] = (sc["alt_sa_raw"] - od.alt_mean) / od.alt_sd
    notes.append(f"alt: sin pronóstico REM; se extrapola el cambio medio de 12 meses ({drift:+.4f} log/mes)")

    # dep_exp del mes t usa el TC de t+1: hace falta la trayectoria hasta origin + h + 1.
    tc = _monthly_points(rem, TC_VAR, survey, "$/USD").reindex(pd.period_range(od.origin, periods=h + 2, freq="M"))
    tc.iloc[0] = panel.at[od.origin, "fx_a3500"]
    dep = np.log(tc.shift(-1) / tc).reindex(months)
    if dep.isna().any():
        notes.append(f"dep_exp: REM sin TC para {list(map(str, dep[dep.isna()].index))}; se repite el último")
    sc["dep_exp"] = dep.ffill().values
    sc = sc.join(dummies(months))
    return sc, notes
