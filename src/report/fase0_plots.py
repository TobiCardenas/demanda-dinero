"""Gráficos de la Fase 0, uno por serie: python -m src.report.fase0_plots

Incluye un chequeo contra lo publicado: variación real s.e. del M2 transaccional (X13 sobre la muestra
completa) comparada con la cifra del IMM de jul-2026 (+1,8% en julio).
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.x13 import x13_arima_analysis

from src.ingest.common import ROOT, load_yaml

LABELS = {
    "circ_public": "Circulante en poder del público (millones ARS)",
    "dav_nr": "DAV privados no remunerados (millones ARS)",
    "m2_trans_priv": "M2 privado transaccional (millones ARS)",
    "m2_priv": "M2 privado (millones ARS)",
    "cc_priv": "Cuentas corrientes privadas (millones ARS)",
    "ca_priv": "Cajas de ahorro privadas (millones ARS)",
    "cheques_canc": "Cheques cancelatorios (millones ARS)",
    "rate_pf30": "Tasa plazo fijo 30 días (% TNA)",
    "rate_badlar": "BADLAR privados (% TNA)",
    "rate_tamar": "TAMAR privados (% TNA)",
    "fx_a3500": "Tipo de cambio A3500 (ARS/USD)",
    "ipc_headline": "IPC Nacional nivel general (dic-16=100)",
    "ipc_core": "IPC Nacional núcleo (dic-16=100)",
    "emae_orig": "EMAE original (2004=100)",
    "emae_sa": "EMAE desestacionalizado (2004=100)",
    "transf_push_ars_monto": "Transferencias inmediatas push, monto (ARS)",
    "transf_push_ars_cant": "Transferencias inmediatas push, cantidad",
    "pct_monto": "Pagos con transferencia (QR/PCT), monto (ARS)",
    "pct_cant": "Pagos con transferencia (QR/PCT), cantidad",
    "debit_card_monto": "Tarjeta de débito, monto (ARS)",
    "credit_card_monto": "Tarjeta de crédito, monto (ARS)",
    "infl_bcra": "Inflación mensual, BCRA id 27 (%)",
}
LOG_SCALE = {"circ_public", "dav_nr", "m2_trans_priv", "m2_priv", "cc_priv", "ca_priv", "fx_a3500",
             "ipc_headline", "ipc_core", "transf_push_ars_monto", "pct_monto", "debit_card_monto",
             "credit_card_monto", "transf_push_ars_cant", "pct_cant"}


def _plot(s: pd.Series, title: str, path, log: bool, real: pd.Series | None = None) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.6))
    s = s.dropna()
    ax.plot(s.index.to_timestamp(), s.values, color="#1f5aa6", lw=1.6, label="nominal" if real is not None else None)
    if log:
        ax.set_yscale("log")
    if real is not None:
        ax2 = ax.twinx()
        r = real.dropna()
        ax2.plot(r.index.to_timestamp(), r.values, color="#c0504d", lw=1.4, label="real (millones ARS dic-16)")
        ax2.set_ylabel("real, ARS de dic-2016", color="#c0504d", fontsize=8)
        ax2.tick_params(axis="y", labelsize=8, colors="#c0504d")
    ax.set_title(title, fontsize=10, loc="left")
    ax.tick_params(labelsize=8)
    ax.grid(alpha=0.25)
    ax.text(0.99, 0.02, f"último: {s.index[-1]}", transform=ax.transAxes, ha="right", fontsize=7, color="#555")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def m2_check(panel: pd.DataFrame) -> str:
    x13 = ROOT / load_yaml("settings.yaml")["paths"]["x13_binary"]
    real = (panel["m2_trans_priv"] / panel["ipc_headline"]).dropna()
    real.index = real.index.to_timestamp()
    sa = x13_arima_analysis(real, x12path=str(x13), log=True, outlier=True).seasadj
    g = (sa.pct_change() * 100).round(2)
    return (f"M2 transaccional real s.e. (X13, muestra 2021-01..{real.index[-1]:%Y-%m}): "
            f"jun-26 {g['2026-06-01']:+.2f}%, jul-26 {g['2026-07-01']:+.2f}%, ago-26 {g['2026-08-01']:+.2f}%, "
            f"sep-26 {g['2026-09-01']:+.2f}%. IMM jul-2026 publica +1,8% para julio.")


def main() -> int:
    proc = ROOT / "data" / "processed"
    out = ROOT / "reports" / "fase0"
    out.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(proc / "panel_monthly.csv", index_col=0)
    panel.index = pd.PeriodIndex(panel.index, freq="M")
    for col, title in LABELS.items():
        real = panel[col] / panel["ipc_headline"] * 100 if col in {"circ_public", "dav_nr", "m2_trans_priv"} else None
        _plot(panel[col], title, out / f"{col}.png", col in LOG_SCALE, real)

    gdp = pd.read_csv(proc / "gdp_quarterly.csv", index_col=0)
    gdp.index = pd.PeriodIndex(gdp.index, freq="Q")
    for col, title, log in [("gdp_nominal_q", "PIB nominal trimestral (millones ARS)", True),
                            ("gdp_real_sa_q", "PIB real s.e. trimestral (millones ARS de 2004)", False),
                            ("gdp_deflator_q", "Deflactor implícito del PIB (2004=100)", True)]:
        _plot(gdp[col], title, out / f"{col}.png", log)

    msg = m2_check(panel)
    (out / "chequeo_m2_imm.txt").write_text(msg + "\n", encoding="utf-8")
    print(msg)
    print(f"{len(LABELS) + 3} gráficos en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
