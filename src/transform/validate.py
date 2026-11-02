"""Validaciones del panel: python -m src.transform.validate

Falla (exit 1) ante huecos, unidades implausibles o discrepancias entre canales de publicación.
Escribe reports/fase0/validacion.md con el detalle y los últimos datos para cotejar con lo publicado.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.ingest import bcra, indec
from src.ingest.common import ROOT, Snapshot, latest_snapshot

# Rangos plausibles del último dato: detectan errores de unidad (miles vs millones, variación vs saldo).
PLAUSIBLE_LAST = {
    "circ_public": (1e6, 1e9),       # millones ARS
    "dav_nr": (1e6, 1e9),
    "m2_trans_priv": (1e6, 1e9),
    "m2_priv": (1e6, 1e9),
    "m3_priv": (1e6, 1e10),
    "fci_psp_saldo": (1e5, 1e9),
    "rate_pf30": (0.5, 300),         # % TNA
    "rate_badlar": (0.5, 300),
    "ipc_headline": (100, 1e7),      # dic-2016 = 100
    "ipc_core": (100, 1e7),
    "emae_sa": (50, 400),            # 2004 = 100
    "emae_orig": (50, 400),
}
# Fecha desde la cual cada serie mensual debe estar sin huecos.
REQUIRED_FROM = {
    "circ_public": "2016-01", "cc_priv": "2016-01", "ca_priv": "2016-01", "m2_priv": "2016-01",
    "m2_trans_priv": "2021-01", "dav_nr": "2021-01",
    "rate_pf30": "2016-01", "rate_badlar": "2016-01", "fx_a3500": "2016-01",
    "ipc_headline": "2016-12", "ipc_core": "2016-12", "emae_orig": "2016-01", "emae_sa": "2016-01",
    "transf_push_ars_monto": "2017-01", "pct_monto": "2021-01", "debit_card_monto": "2017-01",
    "m3_priv": "2016-01", "fci_psp_saldo": "2023-08", "m2_amp": "2023-08",
}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def check(self, ok: bool, msg: str, *, warn_only: bool = False) -> None:
        prefix = "OK  " if ok else ("AVISO " if warn_only else "FALLA ")
        (self.notes if ok else (self.warnings if warn_only else self.errors)).append(prefix + msg)


def check_gaps(panel: pd.DataFrame, rep: Report) -> None:
    for col, start in REQUIRED_FROM.items():
        s = panel[col].dropna()
        s = s[s.index >= pd.Period(start, "M")]
        if s.empty:
            rep.check(False, f"{col}: sin datos desde {start}")
            continue
        full = pd.period_range(pd.Period(start, "M"), s.index.max(), freq="M")
        missing = full.difference(s.index)
        rep.check(missing.empty, f"{col}: continuo {start}..{s.index.max()}"
                  + ("" if missing.empty else f"; faltan {list(map(str, missing[:6]))}"))


# 7 días: Semana Santa 2024 (27-mar al 3-abr: jueves y viernes santo, puente del 1-abr y Malvinas el 2-abr).
def check_daily_gaps(daily: pd.DataFrame, rep: Report, max_days: int = 7) -> None:
    for col in ["circ_public", "m2_trans_priv", "cc_priv", "ca_priv", "rate_pf30"]:
        idx = daily[col].dropna().index
        gaps = pd.Series(idx[1:] - idx[:-1], index=idx[1:])
        big = gaps[gaps > pd.Timedelta(days=max_days)]
        rep.check(big.empty, f"{col} diario: sin saltos > {max_days} días corridos"
                  + ("" if big.empty else f"; {[(str(d.date()), g.days) for d, g in big.head(5).items()]}"))


def check_units(panel: pd.DataFrame, rep: Report) -> None:
    for col, (lo, hi) in PLAUSIBLE_LAST.items():
        last = panel[col].dropna()
        val = last.iloc[-1]
        rep.check(lo <= val <= hi, f"{col}: último {last.index[-1]} = {val:,.2f} dentro de [{lo:g}, {hi:g}]")
    # Saldos: no negativos en ningún mes.
    for col in ["circ_public", "dav_nr", "m2_trans_priv", "cc_priv", "ca_priv", "pf_priv", "m3_priv",
                "fci_psp_saldo"]:
        neg = panel[col].dropna() < 0
        rep.check(not neg.any(), f"{col}: sin valores negativos")


def check_identities(daily: pd.DataFrame, rep: Report) -> None:
    d = daily.dropna(subset=["m2_trans_priv"])
    rep.check((d["dav_nr"] > 0).all(), "DAV no remunerados > 0 todos los días")
    excess = (d["m2_trans_priv"] - d["m2_priv"]).max()
    rep.check(excess <= 0, f"M2 transaccional <= M2 privado todos los días (máx exceso {excess:,.0f})")
    # Depósitos privados en pesos: componentes (94..98) = total (106) - dólares valuados en pesos (104).
    dd = daily.dropna(subset=["dep_priv_total_106", "dep_priv_usd_104", "pf_priv"])
    pesos = dd["cc_priv"] + dd["ca_priv"] + dd["pf_priv"] + dd["pf_uva_priv"] + dd["other_dep_priv"]
    rel = ((pesos - (dd["dep_priv_total_106"] - dd["dep_priv_usd_104"])).abs() / pesos).max()
    rep.check(rel < 1e-6, f"depósitos privados en pesos: 94+95+96+97+98 = 106 - 104 (máx. dif. relativa {rel:.1e})")
    rep.check((daily["m3_priv"].dropna() >= daily["m2_priv"].dropna()).all(), "M3 privado >= M2 privado todos los días")
    share = (d["m2_trans_priv"] / d["m2_priv"])
    rep.notes.append(f"INFO M2 transaccional / M2 privado: {share.iloc[0]:.3f} ({d.index[0].date()}) "
                     f"-> {share.iloc[-1]:.3f} ({d.index[-1].date()})")


def _split_check(rep: Report, bad: pd.Series, recent_from: pd.Period, msg: str, fmt) -> None:
    """Discrepancias recientes son error; las viejas (ya conocidas y documentadas) son advertencia."""
    recent, old = bad[bad.index >= recent_from], bad[bad.index < recent_from]
    rep.check(recent.empty, f"{msg} desde {recent_from}" + ("" if recent.empty else f": {fmt(recent)}"))
    if not old.empty:
        rep.check(False, f"{msg} antes de {recent_from}: {fmt(old)}", warn_only=True)


def check_cross(snap: Snapshot, panel: pd.DataFrame, daily: pd.DataFrame, rep: Report) -> None:
    recent_from = pd.Period(snap.date, "M") - 24

    # Circulante: Series.xlsm (67) contra Principales Variables (17). La 17 viene redondeada a millones
    # y en 2016-2017 difiere hasta 4 millones (dif. relativa ~1e-5).
    both = daily[["circ_public", "circ_public_pv"]].dropna()
    rel = (both["circ_public"] / both["circ_public_pv"] - 1).abs().max()
    rep.check(rel < 1e-4, f"circulante id 67 vs id 17: máx. dif. relativa {rel:.2e} ({len(both)} días)")

    # IPC: CSV de INDEC vs datos.gob.ar. Conocida: abr-2019 difiere (213,05 vs 212,96; ambos 3,4% m/m redondeado).
    ipc = indec.parse_ipc(snap)
    dg = indec.parse_datos_gob(snap, "ipc_headline_dg")
    ov = ipc.index.intersection(dg.index)
    rel = (ipc[ov] / dg[ov] - 1).abs()
    _split_check(rep, rel[rel > 1e-5], recent_from, "IPC INDEC vs datos.gob.ar idénticos",
                 lambda s: {str(k): f"{v:.1e}" for k, v in s.items()})

    # IPC: variación mensual INDEC vs inflación mensual republicada por el BCRA (redondeada a 0,1).
    # Conocida: ene/feb-2017 el BCRA usa otro índice (previo a la serie nacional).
    infl = panel["infl_bcra"].dropna()
    vm = (panel["ipc_headline"].pct_change() * 100).round(1)
    ov = infl.index.intersection(vm.dropna().index)
    diff = (vm[ov] - infl[ov]).abs()
    _split_check(rep, diff[diff > 0.1 + 1e-9], recent_from, "IPC var. m/m INDEC vs BCRA id 27 (±0,1 pp)",
                 lambda s: {str(k): f"{v:.1f}pp" for k, v in s.items()})
    rep.notes.append(f"INFO IPC {ov.max()}: INDEC {vm[ov.max()]:.1f}% / BCRA {infl[ov.max()]:.1f}%")

    # EMAE: xls de INDEC vs datos.gob.ar. Las revisiones recientes son esperables; la historia vieja no debe moverse.
    emae = indec.parse_emae(snap)
    for col, name in [("emae_orig", "emae_orig_dg"), ("emae_sa", "emae_sa_dg")]:
        dg = indec.parse_datos_gob(snap, name)
        ov = emae.index.intersection(dg.index)
        rel = (emae.loc[ov, col] / dg[ov] - 1).abs()
        old = rel[rel.index <= ov.max() - 24]
        rep.check(old.max() < 5e-3, f"{col} INDEC vs datos.gob.ar, hasta {ov.max() - 24}: máx. dif. {old.max():.2e}")
        rep.notes.append(f"INFO {col}: dif. máx. en los últimos 24 meses (revisiones) {rel[rel.index > ov.max() - 24].max():.2e}")

    # PIB: el trimestre más reciente debe ser como mucho 2 trimestres anterior al trimestre del snapshot.
    gdp = indec.parse_datos_gob(snap, "gdp_nominal_q")
    lag = (pd.Period(snap.date, "Q") - gdp.index.max()).n
    rep.check(lag <= 2, f"PIB nominal: último trimestre {gdp.index.max()} (rezago {lag} trimestres)")


def latest_values(panel: pd.DataFrame) -> list[str]:
    out = ["| Serie | Último mes | Valor | Var. % m/m |", "|---|---|---|---|"]
    for col in ["circ_public", "dav_nr", "m2_trans_priv", "rate_pf30", "ipc_headline", "ipc_core",
                "emae_sa", "transf_push_ars_monto", "pct_monto"]:
        s = panel[col].dropna()
        out.append(f"| {col} | {s.index[-1]} | {s.iloc[-1]:,.2f} | {100 * (s.iloc[-1] / s.iloc[-2] - 1):.2f} |")
    return out


def run(snap: Snapshot) -> Report:
    proc = ROOT / "data" / "processed"
    panel = pd.read_csv(proc / "panel_monthly.csv", index_col=0)
    panel.index = pd.PeriodIndex(panel.index, freq="M")
    daily = pd.read_csv(proc / "daily_bcra.csv", index_col=0, parse_dates=True)
    rep = Report()
    check_gaps(panel, rep)
    check_daily_gaps(daily, rep)
    check_units(panel, rep)
    check_identities(daily, rep)
    check_cross(snap, panel, daily, rep)

    lines = [f"# Validación del panel (snapshot {snap.date})", "",
             f"Errores: {len(rep.errors)} · Advertencias: {len(rep.warnings)}", ""]
    for title, items in [("Errores", rep.errors), ("Advertencias", rep.warnings), ("Chequeos", rep.notes)]:
        if items:
            lines += [f"## {title}", ""] + [f"- {x}" for x in items] + [""]
    lines += ["## Últimos datos (cotejar con la publicación oficial)", ""] + latest_values(panel)
    out = ROOT / "reports" / "fase0"
    out.mkdir(parents=True, exist_ok=True)
    (out / "validacion.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rep


def main() -> int:
    rep = run(latest_snapshot())
    for x in rep.errors + rep.warnings:
        print(x)
    print(f"{len(rep.errors)} errores, {len(rep.warnings)} advertencias, {len(rep.notes)} chequeos OK/info "
          f"-> reports/fase0/validacion.md")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
