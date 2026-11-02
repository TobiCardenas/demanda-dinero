"""Ratio % del PIB, solo para comparar con el BCRA (la variable de modelado es el log de saldos reales).

Método (PIB nominal mensual s.e., a tasa anual):
1. PIB nominal trimestral s.e. = PIB real s.e. x deflactor implícito (nominal / real, series originales).
   Los trimestrales de INDEC vienen anualizados: el promedio de los 4 trimestres de 2025 = PIB anual 2025.
2. Deflactor mensual: interpolación log-lineal del trimestral ubicado en el mes central; después del último
   trimestre se extrapola con el IPC.
3. PIB mensual provisorio = EMAE s.e. (X13 truncado en el origen) x deflactor mensual.
4. Se reescala por trimestre para que el promedio mensual coincida con el trimestral s.e. Después del último
   trimestre disponible se mantiene el último factor.
Solo se usan trimestres cuyo último mes es <= origen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ingest.common import ROOT


def load_gdp() -> pd.DataFrame:
    g = pd.read_csv(ROOT / "data" / "processed" / "gdp_quarterly.csv", index_col=0)
    g.index = pd.PeriodIndex(g.index, freq="Q")
    return g


def monthly_nominal_gdp_sa(act: pd.Series, log_p: pd.Series, origin: pd.Period,
                           gdp: pd.DataFrame | None = None) -> pd.Series:
    gdp = load_gdp() if gdp is None else gdp
    gdp = gdp[[q.asfreq("M", "end") <= origin for q in gdp.index]].dropna()
    defl_q = gdp["gdp_nominal_q"] / gdp["gdp_real_q"]
    nom_sa_q = gdp["gdp_real_sa_q"] * defl_q

    months = act.dropna().index
    mid = {q.asfreq("M", "start") + 1: np.log(v) for q, v in defl_q.items()}
    ld = pd.Series(np.nan, index=months)
    for m, v in mid.items():
        if m in ld.index:
            ld[m] = v
    last_mid = max(m for m in mid if m in ld.index)
    ld[ld.index <= last_mid] = ld[ld.index <= last_mid].interpolate(limit_area="inside")
    after = ld.index > last_mid
    ld[after] = ld[last_mid] + (log_p.reindex(months)[after] - log_p[last_mid])
    ld = ld.bfill()

    raw = np.exp(act.reindex(months) + ld)
    k = pd.Series(np.nan, index=months)
    for q, target in nom_sa_q.items():
        mm = pd.period_range(q.asfreq("M", "start"), q.asfreq("M", "end"), freq="M")
        if mm.isin(months).all():
            k[mm] = target / raw[mm].mean()
    k = k.ffill().bfill()
    return (raw * k).rename("gdp_nominal_sa_m")


def pct_gdp(real_sa_level: pd.Series, log_p: pd.Series, gdp_m: pd.Series) -> pd.Series:
    """real_sa_level en millones de ARS de dic-2016; devuelve % del PIB anual."""
    nominal = real_sa_level * np.exp(log_p.reindex(real_sa_level.index)) / 100
    return (nominal / gdp_m.reindex(real_sa_level.index) * 100).rename("pct_gdp")
