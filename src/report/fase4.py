"""Fase 4: ranking pseudo fuera de muestra, agregados (hipótesis 6) y, al final, 2026.
python -m src.report.fase4 [archivo de pronósticos]

Orden del informe (protocolo de DECISIONS.md):
  1. Muestra de desarrollo (mes objetivo <= oct-25): ranking por horizonte, ensambles, densidades, DM.
  2. Agregados: estabilidad del equilibrio y error relativo a la caminata aleatoria.
  3. Recién al final: test (objetivo >= nov-25) y los orígenes de los programas del BCRA.
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ensemble.combine import combine
from src.evaluate import vintages
from src.evaluate.coverage import density_metrics
from src.evaluate.errors import attach_observed, point_metrics
from src.evaluate.tests_dm import dm_table
from src.ingest.common import ROOT
from src.transform import model_data as md
from src.transform.ratios import monthly_nominal_gdp_sa

OUT = ROOT / "reports" / "fase4"
DEV_END = pd.Period("2025-10", "M")
TEST_START = pd.Period("2025-11", "M")
BCRA_ORIGINS = {"2025-11": 4, "2026-04": 3, "2026-07": 2}
VAR_LABEL = {"circ": "Circulante", "dav": "DAV no remunerados", "m2": "M2 transaccional", "m2priv": "M2 privado",
             "m3": "M3 privado", "m2amp": "M2 ampliado"}


def latest_forecast_file():
    files = sorted(p for p in (ROOT / "data" / "forecasts").glob("pseudo_oos_*.csv")
                   if not p.stem.endswith(("_fallas", "_estabilidad")))
    if not files:
        raise FileNotFoundError("No hay pronósticos archivados: correr python -m src.evaluate.oos")
    return files[-1]


def load(path) -> pd.DataFrame:
    fc = pd.read_csv(path)
    for c in ["origin", "target"]:
        fc[c] = pd.PeriodIndex(fc[c], freq="M")
    return fc


def add_ensembles(fc: pd.DataFrame, vint: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts, logs = [fc], []
    for (var, sc), g in fc.groupby(["variable", "scenario"]):
        models = g["model"].unique()
        groups = {"F1": [m for m in models if m.startswith("F1|")], "F2": [m for m in models if m.startswith("F2|")],
                  "all": list(models)}
        groups = {k: v for k, v in groups.items() if v}
        ens, log = combine(g, vint, groups)
        parts.append(ens)
        logs.append(log)
    return pd.concat(parts, ignore_index=True), pd.concat(logs, ignore_index=True)


def ranking(pm: pd.DataFrame, dens: pd.DataFrame, dm: pd.DataFrame, var: str, sc: str) -> pd.DataFrame:
    p = pm[(pm["variable"] == var) & (pm["scenario"] == sc)]
    if p.empty:
        return pd.DataFrame()
    rel = p.pivot(index="model", columns="h", values="RMSE_rel")
    rank = p.assign(r=p.groupby("h")["RMSE"].rank()).pivot(index="model", columns="h", values="r").mean(axis=1)
    out = pd.DataFrame({f"RMSE rel h{h}": rel[h] for h in [1, 3, 6] if h in rel})
    out["rango medio (h1-6)"] = rank
    out["acierto dir. h3"] = p[p["h"] == 3].set_index("model")["dir_acc"]
    d = dens[(dens["variable"] == var) & (dens["scenario"] == sc)].groupby("model")
    out["cob68"] = d["cov68"].mean()
    out["cob95"] = d["cov95"].mean()
    out["CRPS"] = d["crps"].mean()
    dd = dm[(dm["variable"] == var) & (dm["scenario"] == sc)]
    for h in [1, 6]:
        out[f"DM p h{h}"] = dd[dd["h"] == h].set_index("model")["dm_p"]
    out["N h1"] = p[p["h"] == 1].set_index("model")["N"]
    out["N h6"] = p[p["h"] == 6].set_index("model")["N"]
    return out.sort_values("rango medio (h1-6)")


def stability(stab: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for var, g in stab.groupby("variable"):
        g = g.sort_values("origin").set_index("origin")
        g = g[g.index <= DEV_END]
        prev = g["y_lp_origin"].shift(1)
        consecutive = pd.Series(g.index, index=g.index).diff().apply(lambda x: getattr(x, "n", np.nan)) == 1
        rev = (g["y_lp_prev"] - prev)[consecutive]
        rows.append({"variable": var, "N orígenes": len(g), "revisión media |Δ y_lp| (%)": 100 * rev.abs().mean(),
                     "revisión máx. (%)": 100 * rev.abs().max(), "theta medio": g["theta"].mean(),
                     "desvío theta": g["theta"].std(), "|ec| medio (%)": 100 * g["ec"].abs().mean()})
    return pd.DataFrame(rows).set_index("variable")


def pct_obs_m2(latest: pd.DataFrame) -> pd.Series:
    panel = md.load_panel()
    gdp = monthly_nominal_gdp_sa(latest["act"], latest["log_p"], panel["emae_orig"].dropna().index.max())
    return np.exp(latest["y_m2"]) * np.exp(latest["log_p"]) / 100 / gdp * 100


def fmt(df: pd.DataFrame, nd: int = 2) -> str:
    return df.round(nd).to_markdown()


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    path = argv[0] if argv else latest_forecast_file()
    fc = load(path)
    stab = pd.read_csv(str(path).replace(".csv", "_estabilidad.csv"))
    stab["origin"] = pd.PeriodIndex(stab["origin"], freq="M")
    fpath = str(path).replace(".csv", "_fallas.csv")
    try:
        fails = pd.read_csv(fpath)
    except (FileNotFoundError, pd.errors.EmptyDataError):  # cero fallas -> archivo vacío
        fails = pd.DataFrame()
    vint = vintages.load()
    panel = md.load_panel()
    latest = md.build(panel.index.max(), panel).data

    allfc, wlog = add_ensembles(fc, vint)
    allfc = attach_observed(allfc, latest[[c for c in latest if c.startswith("y_")]])
    allfc.to_csv(OUT / "pronosticos_con_ensambles.csv", index=False)
    wlog.to_csv(OUT / "pesos_ensambles.csv", index=False)

    dev = allfc[allfc["target"] <= DEV_END]
    test = allfc[allfc["target"] >= TEST_START]
    pm, dens, dm = point_metrics(dev), density_metrics(dev), dm_table(dev)
    pm.to_csv(OUT / "metricas_desarrollo.csv", index=False)

    L = [f"# Fase 4: tablas (pronósticos: `{pd.io.common.stringify_path(path).split('forecasts')[-1]}`)", "",
         f"Fallas de estimación: {len(fails)} de {fc.groupby(['origin', 'variable', 'model']).ngroups} "
         f"ajustes.", "",
         "Errores en % (100 × log). RMSE rel < 1: mejor que la caminata aleatoria (RW) de la misma variable. "
         "DM p: Diebold-Mariano-HLN contra RW (bilateral). Cobertura y CRPS con bandas de solo shocks "
         "(piso, ver DECISIONS).", ""]

    L += ["## 1. Muestra de desarrollo (mes objetivo ≤ oct-25)", ""]
    for sc in ["exante_rem", "realized"]:
        for var in ["circ", "m2priv", "m3", "dav", "m2"]:
            r = ranking(pm, dens, dm, var, sc)
            if r.empty:
                continue
            L += [f"### {VAR_LABEL[var]}, escenario {sc}", "", fmt(r), ""]

    L += ["## 2. Agregados (hipótesis 6), muestra de desarrollo", "",
          "Estabilidad del equilibrio (F1 mínima, muestra larga): revisión del equilibrio del mes anterior al "
          "agregar una observación, y dispersión de theta entre orígenes.", "", fmt(stability(stab), 3), ""]
    best = []
    for var in ["circ", "dav", "m2", "m2priv", "m3"]:
        p = pm[(pm["variable"] == var) & (pm["scenario"] == "exante_rem")]
        if p.empty:
            continue
        for h in [1, 3, 6]:
            ph = p[p["h"] == h]
            b = ph.loc[ph["RMSE_rel"].idxmin()]
            rw = ph[ph["model"] == "RW"].iloc[0]
            best.append({"variable": var, "h": h, "RMSE RW (%)": rw["RMSE"], "mejor modelo": b["model"],
                         "RMSE rel del mejor": b["RMSE_rel"], "N": int(b["N"])})
    L += ["Error absoluto de la RW (volatilidad del agregado) y mejor modelo, escenario REM:", "",
          pd.DataFrame(best).round(3).to_markdown(index=False), ""]

    # --- 3. Test -----------------------------------------------------------------------------
    L += ["## 3. Test: mes objetivo ≥ nov-25 (no decide nada; se reporta al final)", ""]
    pmt = point_metrics(test)
    for sc in ["exante_rem", "realized"]:
        for var in ["circ", "dav", "m2", "m2priv", "m3", "m2amp"]:
            p = pmt[(pmt["variable"] == var) & (pmt["scenario"] == sc)]
            if p.empty:
                continue
            rel = p.pivot(index="model", columns="h", values="RMSE_rel")
            n = p.pivot(index="model", columns="h", values="N")
            t = pd.DataFrame({f"RMSE rel h{h}": rel[h] for h in [1, 3, 6] if h in rel})
            t["RMSE h3 (%)"] = p[p["h"] == 3].set_index("model")["RMSE"]
            t["N h1"], t["N h6"] = n.get(1), n.get(6)
            t = t.sort_values(t.columns[1] if "RMSE rel h3" in t else t.columns[0])
            L += [f"### {VAR_LABEL[var]}, escenario {sc}", "", fmt(t), ""]

    pobs = pct_obs_m2(latest)
    rows = []
    for o, hp in BCRA_ORIGINS.items():
        o_p = pd.Period(o, "M")
        tgt = o_p + hp
        g = allfc[(allfc["variable"] == "m2") & (allfc["scenario"] == "exante_rem") & (allfc["origin"] == o_p)
                  & (allfc["target"] == tgt)]
        for _, r in g.iterrows():
            rows.append({"origen": o, "objetivo": str(tgt), "modelo": r["model"],
                         "cambio pronosticado (%)": 100 * r["fc_change"], "cambio observado (%)": 100 * r["obs_change"],
                         "error en cambios (%)": 100 * (r["fc_change"] - r["obs_change"]),
                         "pp PIB observado (última vintage)": pobs.get(tgt, np.nan) - pobs.get(o_p, np.nan)})
    t = pd.DataFrame(rows)
    if not t.empty:
        keep = ["F1|minimal|long", "F2|minimal|long", "IC1_F1", "IC3_F1", "DIFF", "TVP", "RW", "RW_drift", "ARIMA",
                "ENS_F1_w", "ENS_F1_avg", "ENS_F2_w", "ENS_all_w", "ENS_all_avg"]
        t = t[t["modelo"].isin(keep)]
        L += ["### M2 transaccional en los orígenes de los programas del BCRA (escenario REM)", "",
              "BCRA base (Fase 1, lectura a ojo): nov-25 → mar-26 +0,23 pp; abr-26 → jul-26 −0,09 pp; "
              "jul-26 → sep-26 +0,095 pp. La comparación de modelos es en saldos reales; el cambio observado en pp "
              "del PIB (última vintage, nuestro método) se muestra para contrastar con el observado del BCRA en su "
              "vintage (nov-25 → mar-26: −0,15 pp).",
              "", t.round(3).to_markdown(index=False), ""]
    (OUT / "fase4_tablas.md").write_text("\n".join(L), encoding="utf-8")

    # Gráfico: RMSE relativo por horizonte (desarrollo, REM), modelos seleccionados
    sel = ["F1|minimal|long", "F2|minimal|long", "IC1_F1", "DIFF", "TVP", "RW_drift", "ARIMA", "ENS_F1_w",
           "ENS_all_w", "ENS_all_avg"]
    vars_ = ["circ", "m2priv", "m3", "dav", "m2"]
    fig, axes = plt.subplots(1, len(vars_), figsize=(16, 3.6), sharey=True)
    for ax, var in zip(axes, vars_):
        p = pm[(pm["variable"] == var) & (pm["scenario"] == "exante_rem")]
        for m in sel:
            q = p[p["model"] == m].sort_values("h")
            if not q.empty:
                ax.plot(q["h"], q["RMSE_rel"], marker="o", ms=3, lw=1.2, label=m)
        ax.axhline(1, color="black", lw=0.8)
        ax.set_title(VAR_LABEL[var], fontsize=9, loc="left")
        ax.set_xlabel("h", fontsize=8)
        ax.grid(alpha=0.25)
        ax.set_ylim(0, 3)
    axes[0].set_ylabel("RMSE / RMSE RW (desarrollo, REM)", fontsize=8)
    axes[-1].legend(fontsize=6, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "rmse_relativo.png", dpi=120)
    plt.close(fig)
    print((OUT / "fase4_tablas.md").read_text(encoding="utf-8")[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
