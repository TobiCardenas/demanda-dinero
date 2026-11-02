"""Hipótesis 6, panorama descriptivo de los agregados: python -m src.report.hipotesis6

Solo describe; no estima modelos ni elige especificaciones (ver el compromiso previo en DECISIONS.md).
Saldos reales s.e. con X13 sobre la muestra completa (última vintage).
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ingest.common import ROOT
from src.transform import model_data as md

OUT = ROOT / "reports" / "hipotesis6"
AGG = {"y_circ": "Circulante", "y_m2": "M2 transaccional", "y_m2amp": "M2 ampliado (+ FCI billeteras)",
       "y_m2priv": "M2 privado", "y_m3": "M3 privado"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    panel = md.load_panel()
    d = md.build(panel.index.max(), panel).data
    lv = np.exp(d[list(AGG)]) / 1000  # miles de millones de ARS de dic-2016
    act = np.exp(d["act"])

    base = pd.Period("2023-08", "M")
    idx = 100 * lv / lv.loc[base]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sub = idx[idx.index >= pd.Period("2021-01", "M")]
    for col, c in zip(AGG, ["#7f7f7f", "#c0504d", "#1f5aa6", "#2e8b57", "#8e44ad"]):
        axes[0].plot(sub.index.to_timestamp(), sub[col], color=c, lw=2 if col in ("y_m2", "y_m2amp") else 1.2,
                     label=AGG[col])
    a = 100 * act / act.loc[base]
    a = a[a.index >= pd.Period("2021-01", "M")]
    axes[0].plot(a.index.to_timestamp(), a, color="black", ls=":", lw=1.2, label="EMAE s.e.")
    axes[0].axhline(100, color="#888", lw=0.6)
    axes[0].set_title("Saldos reales s.e., ago-23 = 100", fontsize=9, loc="left")
    axes[0].legend(fontsize=7)
    axes[0].grid(alpha=0.25)

    share = pd.DataFrame({
        "FCI billeteras / M2 transaccional": 100 * (lv["y_m2amp"] - lv["y_m2"]) / lv["y_m2"],
        "DAV remunerados / M2 privado": 100 * (panel["m2_priv"] - panel["m2_trans_priv"]) / panel["m2_priv"],
        "Plazos fijos y otros / M3 privado": 100 * (panel["m3_priv"] - panel["m2_priv"]) / panel["m3_priv"],
    })
    share = share[share.index >= pd.Period("2021-01", "M")]
    for col, c in zip(share, ["#1f5aa6", "#2e8b57", "#8e44ad"]):
        axes[1].plot(share.index.to_timestamp(), share[col], color=c, lw=1.5, label=col)
    axes[1].set_title("Participaciones (%), sin desestacionalizar", fontsize=9, loc="left")
    axes[1].legend(fontsize=7)
    axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "agregados.png", dpi=120)
    plt.close(fig)

    pts = [pd.Period(x, "M") for x in ["2023-08", "2024-08", "2025-08", "2025-11", "2026-04", "2026-08"]]
    tab = lv.reindex(pts).rename(columns=AGG).round(1)
    chg = []
    for a_, b_ in [("2023-08", "2024-08"), ("2024-08", "2025-08"), ("2025-08", "2026-08"), ("2025-11", "2026-08")]:
        r = 100 * (lv.loc[pd.Period(b_, "M")] / lv.loc[pd.Period(a_, "M")] - 1)
        r["EMAE s.e."] = 100 * (act.loc[pd.Period(b_, "M")] / act.loc[pd.Period(a_, "M")] - 1)
        chg.append(r.rename(f"{a_} → {b_}"))
    chg = pd.DataFrame(chg).rename(columns=AGG).round(1)
    txt = ["# Hipótesis 6: agregados alternativos (descriptivo)", "",
           "Saldos reales s.e. (X13, última vintage), miles de millones de ARS de dic-2016. El M2 ampliado suma los "
           "FCI vía billeteras (stock de fin de mes, sin desestacionalizar) al M2 transaccional s.e.", "",
           tab.to_markdown(), "", "## Variación real s.e. (%)", "", chg.to_markdown(), "",
           "![agregados](agregados.png)", ""]
    (OUT / "hipotesis6.md").write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
