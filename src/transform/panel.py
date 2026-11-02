"""Panel mensual a partir de un snapshot: python -m src.transform.panel [YYYY-MM-DD]

Salidas en data/processed/ (regenerables):
  daily_bcra.csv     series diarias del BCRA + componentes derivados
  panel_monthly.csv  panel mensual (saldos en millones ARS nominales, índices, tasas)
  gdp_quarterly.csv  PIB trimestral
  rem_long.csv       REM en formato largo
"""

from __future__ import annotations

import datetime as dt
import sys

import pandas as pd

from src.ingest import bcra, indec, medios_pago, rem
from src.ingest.common import ROOT, Snapshot, load_yaml, latest_snapshot

STOCKS = ["circ_public", "cheques_canc", "m2_trans_priv", "cc_priv", "ca_priv",
          "pf_priv", "pf_uva_priv", "other_dep_priv", "dep_priv_total_106", "dep_priv_usd_104"]
DAILY_OTHER = ["rate_pf30", "rate_badlar", "rate_tamar", "fx_a3500", "circ_public_pv"]
# Un mes de datos diarios se considera completo si el último dato cae a menos de estos días del fin de mes.
COMPLETE_TOLERANCE_DAYS = 4


def build_daily(snap: Snapshot) -> pd.DataFrame:
    d = pd.concat([bcra.parse(snap, n) for n in STOCKS + DAILY_OTHER], axis=1).sort_index()
    # DAV privados no remunerados: M2 transaccional menos circulante y cheques cancelatorios
    # (definición del glosario del IMM). Se calcula con datos diarios de la misma planilla (Series.xlsm).
    d["dav_nr"] = d["m2_trans_priv"] - d["circ_public"] - d["cheques_canc"]
    d["m2_priv"] = d["circ_public"] + d["cheques_canc"] + d["cc_priv"] + d["ca_priv"]
    # M3 privado (glosario del IMM): circulante + cheques + depósitos privados en pesos.
    d["m3_priv"] = d["m2_priv"] + d["pf_priv"] + d["pf_uva_priv"] + d["other_dep_priv"]
    return d


def monthly_from_daily(d: pd.DataFrame, how: str, asof: dt.date) -> pd.DataFrame:
    """Promedio (o fin) mensual. Se anulan los meses incompletos: el mes del snapshot y posteriores,
    y cualquier mes cuyo último dato quede a más de COMPLETE_TOLERANCE_DAYS del fin de mes."""
    g = d.groupby(d.index.to_period("M"))
    m = g.mean() if how == "monthly_mean" else g.last()
    last_obs = d.apply(lambda s: s.dropna().groupby(s.dropna().index.to_period("M")).apply(lambda x: x.index.max()))
    for col in m.columns:
        lo = last_obs[col].reindex(m.index)
        month_end = m.index.to_timestamp(how="end").normalize()
        incomplete = ((month_end - lo).dt.days > COMPLETE_TOLERANCE_DAYS).fillna(True)
        incomplete |= m.index >= pd.Period(asof, "M")
        m.loc[incomplete.values, col] = float("nan")
    return m


def build(snap: Snapshot) -> dict[str, pd.DataFrame]:
    how = load_yaml("settings.yaml")["modeling"]["aggregation"]
    daily = build_daily(snap)
    monthly = monthly_from_daily(daily, how, snap.date)

    emae = indec.parse_emae(snap)
    pay = medios_pago.parse(snap)
    wallets = medios_pago.parse_wallets(snap)
    infl = bcra.parse(snap, "infl_bcra")
    infl.index = infl.index.to_period("M")
    monthly = monthly.join([
        indec.parse_ipc(snap),
        indec.parse_datos_gob(snap, "ipc_core").rename("ipc_core"),
        emae, pay, wallets, infl.rename("infl_bcra"),
    ], how="outer")
    # M2 ampliado (hipótesis 6): M2 transaccional (promedio mensual) + FCI vía billeteras (stock a fin de mes).
    monthly["m2_amp"] = monthly["m2_trans_priv"] + monthly["fci_psp_saldo"]
    monthly = monthly[monthly.index >= pd.Period("2016-01", "M")]
    monthly.index.name = "period"

    gdp = pd.concat([indec.parse_datos_gob(snap, n) for n in
                     ["gdp_nominal_q", "gdp_real_q", "gdp_real_sa_q", "gdp_deflator_q"]], axis=1)
    gdp.index.name = "quarter"
    return {"daily_bcra": daily, "panel_monthly": monthly, "gdp_quarterly": gdp, "rem_long": rem.parse(snap)}


def main(argv: list[str]) -> int:
    snap = Snapshot(dt.date.fromisoformat(argv[0])) if argv else latest_snapshot()
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in build(snap).items():
        df.to_csv(out_dir / f"{name}.csv")
    (out_dir / "SOURCE_SNAPSHOT").write_text(snap.date.isoformat(), encoding="utf-8")
    print(f"Panel construido desde {snap.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
