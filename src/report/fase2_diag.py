"""Fase 2, diagnóstico: qué supuesto explica los desvíos respecto del BCRA. python -m src.report.fase2_diag

Cambia un supuesto por vez (alt, co, deflactor) sobre la variante de cabecera (determinantes mínimos,
muestra desde 2017; DAV desde 2021) y repite (a) y (b) con pronósticos puntuales. Es diagnóstico: si
alguna alternativa se adopta después, queda en DECISIONS.md como elegida mirando el Gráfico 1 / dic-25.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.ingest.common import ROOT, load_yaml
from src.models.ecm_logistic import LogisticECM
from src.models.vecm import VECMModel
from src.transform import model_data as md
from src.transform.ratios import monthly_nominal_gdp_sa, pct_gdp

OUT = ROOT / "reports" / "fase2"
ALTERNATIVES = [
    ("base", {}),
    ("alt=cantidades", {"alt": "cantidades"}),
    ("alt=montos+débito", {"alt": "montos_debito"}),
    ("co=BADLAR", {"co": "badlar"}),
    ("co=inflación esperada REM", {"co": "infl_exp"}),
    ("deflactor=IPC núcleo", {"deflator": "core"}),
]
SAMPLE = {"circ": {"start": "2017-02"}, "dav": {"start": "2021-02"}}


def fit_pair(od, comp, sc, h, grid):
    out = {}
    for fam, cls, kw in [("F1", VECMModel, {}), ("F2", LogisticECM, {"grid": grid})]:
        m = cls(comp, [], SAMPLE[comp], **kw).fit(od.data, od.origin)
        out[fam] = (m, m.forecast(sc, h, n_sims=1)["point"])
    return out


def diag_a(label, opts, grid) -> dict:
    origin, h = pd.Period("2024-12", "M"), 12
    od = md.build(origin, opts=opts)
    sc = md.scenario_realized(od, h)
    res = fit_pair(od, "circ", sc, h, grid)
    panel = md.load_panel()
    obs = md.build(panel.index.max(), panel, opts=opts).data["y_circ"]
    lvl = lambda y: float(np.exp(y) / 1000)
    f1, f2, o = lvl(res["F1"][1].iloc[-1]), lvl(res["F2"][1].iloc[-1]), lvl(obs[origin + h])
    m1, m2 = res["F1"][0], res["F2"][0]
    s1, lr2, idn = m1.structural(), m2.params.lr, m2.identification()
    return {"supuesto": label, "obs": o, "F1": f1, "F2": f2, "brecha_%": (f1 - f2) / o * 100,
            "F2_mas_cerca": abs(f2 - o) < abs(f1 - o),
            "F1_a2_act": s1["a2_act"], "F1_a1_co": s1["a1_co"], "F1_theta": s1["theta"],
            "F2_theta_alt": lr2["theta_alt"], "F2_lambda": lr2["lambda"], "F2_b_inf": lr2["b_inf"],
            "F2_a2": lr2["a2"], "F2_a1": lr2["a1"], "F2_theta": m2.params.theta,
            "F2_borde": idn["best_on_theta_edge"] or idn["best_on_lambda_edge"],
            "F2_perfil_theta": idn["theta_profile_rel_range"]}


def diag_b(label, opts, grid) -> dict:
    origin, h = pd.Period("2025-11", "M"), 4
    od = md.build(origin, opts=opts)
    sc, _ = md.scenario_rem(od, h)
    fits = {c: fit_pair(od, c, sc, h, grid) for c in ["circ", "dav"]}
    log_p = pd.concat([od.data["log_p"], sc["log_p"]])
    gdp_m = monthly_nominal_gdp_sa(pd.concat([od.data["act"], sc["act"]]), log_p, origin)
    cheq = float(md.load_panel().at[origin, "cheques_canc"] / np.exp(od.data.at[origin, "log_p"]) * 100)
    lvl0 = np.exp(od.data.at[origin, "y_circ"]) + np.exp(od.data.at[origin, "y_dav"]) + cheq
    p0 = float(pct_gdp(pd.Series([lvl0], index=[origin]), log_p, gdp_m).iloc[0])
    out = {"supuesto": label, "nivel_nov25": p0}
    for fam in ["F1", "F2"]:
        lvl = np.exp(fits["circ"][fam][1]) + np.exp(fits["dav"][fam][1]) + cheq
        ch = pct_gdp(lvl, log_p, gdp_m) - p0
        out[f"{fam}_dic25"], out[f"{fam}_mar26"] = ch.iloc[0], ch.iloc[-1]
        out[f"{fam}_circ_mar26_%"] = (np.exp(fits["circ"][fam][1].iloc[-1] - od.data.at[origin, "y_circ"]) - 1) * 100
        out[f"{fam}_dav_mar26_%"] = (np.exp(fits["dav"][fam][1].iloc[-1] - od.data.at[origin, "y_dav"]) - 1) * 100
    return out


def main() -> int:
    grid = load_yaml("settings.yaml")["replication"]["logistic_grid"]
    a_rows, b_rows = [], []
    for label, opts in ALTERNATIVES:
        print(label)
        a_rows.append(diag_a(label, opts, grid))
        b_rows.append(diag_b(label, opts, grid))
    a, b = pd.DataFrame(a_rows), pd.DataFrame(b_rows)
    a.to_csv(OUT / "diag_a.csv", index=False)
    b.to_csv(OUT / "diag_b.csv", index=False)
    fmt = lambda df: df.round(3).to_markdown(index=False)
    txt = ["# Fase 2: diagnóstico por supuesto (un cambio por vez, variante de cabecera, pronóstico puntual)", "",
           "## (a) Circulante a dic-2025, miles de millones de $ de dic-2016 (BCRA: F1 ~275, F2 ~226, obs ~228; "
           "brecha 21%)", "", fmt(a), "",
           "## (b) Programa dic-25, cambio en pp del PIB respecto de nov-25 (BCRA: dic +0,03, mar +0,23)", "",
           fmt(b), ""]
    (OUT / "diagnostico.md").write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
