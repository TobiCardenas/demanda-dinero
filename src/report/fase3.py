"""Fase 3: diagnóstico de 2026. python -m src.report.fase3

Para los orígenes de los programas del BCRA (nov-25, abr-26, jul-26) y por componente:
- pronósticos de la réplica (F1 VECM y F2 logística de cabecera), corrección de intercepto (k=1,3),
  ECM en diferencias y caminata aleatoria, con escenario ex ante REM y realizado;
- descomposición escenario / modelo / revisión (src/evaluate/decompose.py);
- atribución del componente de escenario a cada regresor (act, co, alt), cambiando uno por vez;
- brecha ec_t y equilibrio estimado en tiempo pseudo-real (reestimando en cada mes 2024-01..2026-08), y w_t.
Tablas en reports/fase3/fase3_tablas.md; el veredicto se escribe en reports/fase3/fase3.md.
"""

from __future__ import annotations

import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.evaluate.decompose import contemporaneous_sa, decompose, log_sum
from src.ingest.common import ROOT, load_yaml
from src.models.benchmarks import RandomWalk
from src.models.ecm_logistic import LogisticECM
from src.models.robust import DiffECM, intercept_corrected
from src.models.vecm import VECMModel
from src.transform import model_data as md

OUT = ROOT / "reports" / "fase3"
ORIGINS = {"2025-11": 4, "2026-04": 3, "2026-07": 2}  # horizonte de cada programa del BCRA
LAST_OBS = pd.Period("2026-09", "M")
# El escenario realizado necesita el EMAE: llega hasta ago-26 (sep-26 se publica a fines de noviembre).
# Para el programa de jul-26 la descomposición se hace a h=1 (ago-26) en vez de h=2.
LAST_REALIZED = pd.Period("2026-08", "M")
SAMPLE = {"circ": {"start": "2017-02"}, "dav": {"start": "2021-02"}}
MODELS = ["REP_F1", "REP_F2", "IC1_F1", "IC3_F1", "DIFF", "RW"]


def make(label: str, comp: str, seed: int, grid: dict):
    s = SAMPLE[comp]
    return {
        "REP_F1": lambda: VECMModel(comp, [], s, seed=seed),
        "REP_F2": lambda: LogisticECM(comp, [], s, seed=seed, grid=grid),
        "IC1_F1": lambda: intercept_corrected(VECMModel, 1, comp, [], s, seed=seed),
        "IC3_F1": lambda: intercept_corrected(VECMModel, 3, comp, [], s, seed=seed),
        "DIFF": lambda: DiffECM(comp, [], s, seed=seed),
        "RW": lambda: RandomWalk(comp, seed=seed),
    }[label]()


def run_origins(n_sims: int, seed: int, grid: dict):
    panel = md.load_panel()
    latest = md.build(panel.index.max(), panel).data
    rows, attrib, extra = [], [], {}
    for o_str, h_prog in ORIGINS.items():
        origin = pd.Period(o_str, "M")
        h = (LAST_REALIZED - origin).n
        h_prog = min(h_prog, h)
        od = md.build(origin, panel)
        sc_rem, notes = md.scenario_rem(od, h, panel)
        sc_re = md.scenario_realized(od, h, panel)
        extra[o_str] = {"notes": notes, "sc_rem": sc_rem, "sc_re": sc_re, "od": od}
        months = sc_re.index
        fcs = {}
        for comp in ["circ", "dav"]:
            obs_latest = latest[f"y_{comp}"]
            obs_contemp = contemporaneous_sa(comp, months, panel)
            y0o, y0l = od.data.at[origin, f"y_{comp}"], obs_latest[origin]
            for label in MODELS:
                t = time.time()
                m = make(label, comp, seed, grid).fit(od.data, origin)
                fx = m.forecast(sc_rem, h, n_sims if label != "RW" else 1)
                fr = m.forecast(sc_re, h, n_sims if label != "RW" else 1)
                dec = decompose(fx["point"], fr["point"], obs_latest, obs_contemp, y0o, y0l)
                half = (fr["q0.84"] - fr["q0.16"]) / 2
                dec["z_realized"] = -dec["model_change"] / half.replace(0, np.nan)
                dec["in95_realized"] = dec["z_realized"].abs() <= 1.96
                ec0 = float(m.ec_path().iloc[-1]) if label not in ("DIFF", "RW") else np.nan
                for tm, r in dec.iterrows():
                    rows.append({"origin": o_str, "component": comp, "model": label, "target": tm,
                                 "h": (tm - origin).n, "h_prog": h_prog, "ec_origin": ec0, **r.to_dict()})
                fcs[(comp, label)] = (fx["point"], fr["point"], obs_latest, obs_contemp, y0o, y0l)
                if label in ("REP_F1", "REP_F2"):
                    for v in ["act", "co", "alt"]:
                        mix = sc_re.copy()
                        mix[v] = sc_rem[v]
                        fv = m.forecast(mix, h, 1)["point"]
                        for tm in months:
                            attrib.append({"origin": o_str, "component": comp, "model": label, "var": v,
                                           "target": tm, "h": (tm - origin).n,
                                           "contrib": fv[tm] - fr["point"][tm]})
                    if label == "REP_F2":
                        extra[o_str][f"w_{comp}"] = m.w_path(pd.concat([m.d[["alt"]], sc_re[["alt"]]]))
                        extra[o_str][f"f2_{comp}"] = {**m.params.lr, **m.identification()}
                print(f"  {o_str} {comp:4s} {label:7s} ec0={ec0:+.3f} ({time.time() - t:.0f}s)")
        # M2 transaccional = circulante + DAV (cheques ~0), por modelo
        for label in MODELS:
            c, d = fcs[("circ", label)], fcs[("dav", label)]
            dec = decompose(pd.Series(log_sum(c[0], d[0]), index=months), pd.Series(log_sum(c[1], d[1]), index=months),
                            pd.Series(log_sum(c[2].reindex(months), d[2].reindex(months)), index=months),
                            pd.Series(log_sum(c[3], d[3]), index=months),
                            float(log_sum(c[4], d[4])), float(log_sum(c[5], d[5])))
            for tm, r in dec.iterrows():
                rows.append({"origin": o_str, "component": "m2_sum", "model": label, "target": tm,
                             "h": (tm - origin).n, "h_prog": h_prog, **r.to_dict()})
    return pd.DataFrame(rows), pd.DataFrame(attrib), extra


def recursive_equilibrium(seed: int) -> pd.DataFrame:
    """Reestima la F1 de cabecera en cada mes y guarda la brecha y el equilibrio en el origen."""
    panel = md.load_panel()
    rows = []
    for origin in pd.period_range("2024-01", LAST_REALIZED, freq="M"):
        od = md.build(origin, panel)
        for comp in ["circ", "dav"]:
            m = VECMModel(comp, [], SAMPLE[comp], seed=seed).fit(od.data, origin)
            ylp = pd.Series(m.long_run(m.d, m.params.lr), index=m.d.index)
            s = m.structural()
            rows.append({"origin": origin, "component": comp, "y": od.data.at[origin, f"y_{comp}"],
                         "y_lp": ylp.iloc[-1], "ec": od.data.at[origin, f"y_{comp}"] - ylp.iloc[-1],
                         "y_lp_nov25": ylp.get(pd.Period("2025-11", "M"), np.nan),
                         "theta": s["theta"], "a1_co": s["a1_co"], "a2_act": s["a2_act"], "p": m.p})
        print(f"  recursivo {origin}")
    return pd.DataFrame(rows)


# --- salida -------------------------------------------------------------------------------------

def tables(res: pd.DataFrame, att: pd.DataFrame, rec: pd.DataFrame, extra: dict) -> str:
    pp = lambda x: 100 * x  # log -> %
    prog = res[res["h"] == res["h_prog"]].copy()
    L = ["# Fase 3: tablas", "", "Unidades: % (100 × diferencia de logs de saldos reales s.e.). "
         "Horizonte de cada programa: nov-25 → mar-26 (h=4), abr-26 → jul-26 (h=3), jul-26 → ago-26 (h=1; "
         "el programa llega a sep-26 pero el EMAE de sep-26 no está publicado).", ""]

    L += ["## 1. Descomposición del error de la réplica (F1 de cabecera), horizonte del programa", "",
          "| origen | componente | total | escenario | modelo | revisión (objetivo) | revisión (origen) "
          "| error del modelo en cambios | ec en el origen |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in prog[prog["model"] == "REP_F1"].iterrows():
        L.append(f"| {r.origin} | {r.component} | {pp(r.total):+.1f} | {pp(r.scenario):+.1f} | {pp(r.model_err):+.1f} "
                 f"| {pp(r.revision):+.1f} | {pp(r.revision_origin):+.1f} | {pp(r.model_change):+.1f} "
                 f"| {pp(r.ec_origin) if pd.notna(r.ec_origin) else float('nan'):+.1f} |")

    L += ["", "## 2. Atribución del componente de escenario (F1), horizonte del programa", "",
          "Cada celda: pronóstico con ese regresor del REM y el resto realizado, menos el pronóstico realizado.", "",
          "| origen | componente | act | co | alt | suma | escenario total |", "|---|---|---|---|---|---|---|"]
    h_of = prog.drop_duplicates("origin").set_index("origin")["h_prog"]
    a = att[(att["model"] == "REP_F1") & (att["h"] == att["origin"].map(h_of))]
    for (o, c), g in a.groupby(["origin", "component"], sort=False):
        v = g.set_index("var")["contrib"]
        tot = prog[(prog["model"] == "REP_F1") & (prog["origin"] == o) & (prog["component"] == c)]["scenario"].iloc[0]
        L.append(f"| {o} | {c} | {pp(v['act']):+.1f} | {pp(v['co']):+.1f} | {pp(v['alt']):+.1f} "
                 f"| {pp(v.sum()):+.1f} | {pp(tot):+.1f} |")

    L += ["", "## 3. Error del modelo en cambios (escenario realizado), horizonte del programa, por modelo", "",
          "Valor absoluto; menor es mejor. z: error / semiancho de la banda del 68% del mismo modelo.", ""]
    piv = prog.pivot_table(index=["origin", "component"], columns="model", values="model_change", sort=False)
    piv = piv[MODELS]
    L += ["| origen | componente | " + " | ".join(MODELS) + " | mejor |", "|---|---|" + "---|" * (len(MODELS) + 1)]
    for (o, c), r in piv.iterrows():
        L.append(f"| {o} | {c} | " + " | ".join(f"{pp(abs(v)):.1f}" for v in r.values) + f" | {r.abs().idxmin()} |")
    L += ["", "Con escenario ex ante (REM), error total en cambios:", "",
          "| origen | componente | " + " | ".join(MODELS) + " | mejor |", "|---|---|" + "---|" * (len(MODELS) + 1)]
    piv2 = prog.pivot_table(index=["origin", "component"], columns="model", values="total_change", sort=False)[MODELS]
    for (o, c), r in piv2.iterrows():
        L.append(f"| {o} | {c} | " + " | ".join(f"{pp(abs(v)):.1f}" for v in r.values) + f" | {r.abs().idxmin()} |")

    z = prog[(prog["model"] == "REP_F1") & (prog["component"] != "m2_sum")][["origin", "component", "z_realized"]]
    L += ["", "z de la réplica F1 (escenario realizado): " + ", ".join(
        f"{o}/{c} {v:+.2f}" for o, c, v in z.itertuples(index=False)), ""]

    L += ["## 4. Equilibrio estimado en tiempo pseudo-real (F1, reestimada cada mes)", "",
          "| origen | componente | y | y_lp | ec (%) | y_lp de nov-25 según ese origen | theta | a1 (co) | a2 (act) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in rec[rec["origin"].isin([pd.Period(x, "M") for x in
                                         ["2024-06", "2024-12", "2025-06", "2025-11", "2026-01", "2026-04",
                                          "2026-07", "2026-08"]])].iterrows():
        L.append(f"| {r.origin} | {r.component} | {r.y:.3f} | {r.y_lp:.3f} | {pp(r.ec):+.1f} "
                 f"| {r.y_lp_nov25:.3f} | {r.theta:+.3f} | {r.a1_co:+.1f} | {r.a2_act:+.2f} |")

    L += ["", "## 5. F2 logística en los orígenes de 2026", "",
          "| origen | componente | theta_alt | lambda | w en el origen | borde de grilla | rango perfil theta |",
          "|---|---|---|---|---|---|---|"]
    for o, ex in extra.items():
        for c in ["circ", "dav"]:
            f2, w = ex[f"f2_{c}"], ex[f"w_{c}"]
            L.append(f"| {o} | {c} | {f2['theta_alt']:.2f} | {f2['lambda']:.2f} | {w.loc[pd.Period(o, 'M')]:.2f} "
                     f"| {'sí' if f2['best_on_theta_edge'] or f2['best_on_lambda_edge'] else 'no'} "
                     f"| {f2['theta_profile_rel_range']:.3f} |")
    L += ["", "Supuestos del escenario REM por origen:", ""]
    for o, ex in extra.items():
        L += [f"- {o}: " + "; ".join(ex["notes"])]
    return "\n".join(L) + "\n"


def plots(res: pd.DataFrame, rec: pd.DataFrame, extra: dict) -> None:
    # Brecha y equilibrio en tiempo pseudo-real
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, comp in zip(axes, ["circ", "dav"]):
        r = rec[rec["component"] == comp]
        x = r["origin"].apply(lambda p: p.to_timestamp())
        ax.plot(x, 100 * r["ec"], color="#1f5aa6", lw=1.6, label="ec en el origen (%)")
        ax2 = ax.twinx()
        ax2.plot(x, 100 * (r["y_lp_nov25"] - r["y_lp_nov25"].dropna().iloc[-1]), color="#c0504d", lw=1.2, ls="--",
                 label="y_lp de nov-25 según cada origen\n(desvío vs estimación de ago-26, %)")
        ax2.tick_params(labelsize=7, colors="#c0504d")
        for o in ORIGINS:
            ax.axvline(pd.Period(o, "M").to_timestamp(), color="#888", ls=":")
        ax.axhline(0, color="#888", lw=0.8)
        lo = max(100 * r["ec"].min(), -120)
        ax.set_ylim(lo - 5, max(100 * r["ec"].max(), 10) + 5)
        clipped = r[100 * r["ec"] < lo - 5]
        for _, c in clipped.iterrows():
            ax.annotate(f"{100 * c['ec']:.0f}% ({c['origin']})", (c["origin"].to_timestamp(), lo - 4), fontsize=6.5,
                        color="#1f5aa6", ha="center")
        ax.set_title(f"{comp}: brecha al equilibrio estimado (F1, reestimada cada mes)", fontsize=9, loc="left")
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=6.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "ec_equilibrio_recursivo.png", dpi=120)
    plt.close(fig)

    # Descomposición, réplica F1
    prog = res[(res["h"] == res["h_prog"]) & (res["model"] == "REP_F1")]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    labels = [f"{o}\n{c}" for o, c in zip(prog["origin"], prog["component"])]
    x = np.arange(len(prog))
    w = 0.2
    for i, (col, name, color) in enumerate([("scenario", "escenario", "#e3a33b"), ("model_err", "modelo", "#1f5aa6"),
                                            ("revision", "revisión (objetivo)", "#7f7f7f"),
                                            ("total", "total", "#c0504d")]):
        ax.bar(x + (i - 1.5) * w, 100 * prog[col], w, label=name, color=color)
    ax.set_xticks(x, labels, fontsize=7)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("% (log)", fontsize=8)
    ax.set_title("Descomposición del error de la réplica F1 (pronóstico − observado), horizonte del programa",
                 fontsize=9, loc="left")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(OUT / "descomposicion.png", dpi=120)
    plt.close(fig)

    # Trayectorias por modelo (escenario realizado y ex ante), M2 transaccional: cambio acumulado vs origen
    colors = {"REP_F1": "#c0504d", "REP_F2": "#8e44ad", "IC1_F1": "#1f5aa6", "IC3_F1": "#7fa7d9",
              "DIFF": "#2e8b57", "RW": "#e39a3b"}
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.4), sharey="row")
    for row, (col, title) in enumerate([("fc_realized", "escenario realizado"), ("fc_exante", "escenario REM")]):
        for ax, o in zip(axes[row], ORIGINS):
            r = res[(res["origin"] == o) & (res["component"] == "m2_sum")]
            x0 = pd.Period(o, "M").to_timestamp()
            for mdl in MODELS:
                g = r[r["model"] == mdl].sort_values("target")
                xs = [x0] + [t.to_timestamp() for t in g["target"]]
                ax.plot(xs, [0] + list(100 * (g[col] - g["y0_origin_vintage"])), color=colors[mdl], lw=1.3,
                        label=mdl)
            g = r[r["model"] == "RW"].sort_values("target")
            ax.plot([x0] + [t.to_timestamp() for t in g["target"]], [0] + list(100 * (g["obs_latest"] - g["y0_latest"])),
                    color="black", lw=2.2, label="observado (última vintage)")
            ax.axvline((pd.Period(o, "M") + min(ORIGINS[o], (LAST_REALIZED - pd.Period(o, "M")).n)).to_timestamp(), color="#888", ls=":", lw=0.8)
            ax.axhline(0, color="black", lw=0.6)
            ax.set_title(f"origen {o}, {title}", fontsize=8, loc="left")
            ax.grid(alpha=0.25)
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
            ax.tick_params(labelsize=6.5, axis="x", rotation=45)
    axes[0][0].set_ylabel("M2 transaccional real s.e.\ncambio acumulado (%)", fontsize=8)
    axes[1][0].set_ylabel("cambio acumulado (%)", fontsize=8)
    axes[0][0].legend(fontsize=6.5)
    fig.tight_layout()
    fig.savefig(OUT / "modelos_m2.png", dpi=120)
    plt.close(fig)


def replot() -> None:
    """Rehace los gráficos desde los CSV guardados (sin reestimar)."""
    res = pd.read_csv(OUT / "errores.csv")
    res["target"] = pd.PeriodIndex(res["target"], freq="M")
    rec = pd.read_csv(OUT / "equilibrio_recursivo.csv")
    rec["origin"] = pd.PeriodIndex(rec["origin"], freq="M")
    plots(res, rec, {})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_yaml("settings.yaml")
    n_sims, seed = cfg["replication"]["n_sims"], cfg["forecast"]["seed"]
    grid = cfg["replication"]["logistic_grid"]
    print("Orígenes 2026")
    res, att, extra = run_origins(n_sims, seed, grid)
    res.to_csv(OUT / "errores.csv", index=False)
    att.to_csv(OUT / "atribucion_escenario.csv", index=False)
    print("Equilibrio recursivo")
    rec = recursive_equilibrium(seed)
    rec.to_csv(OUT / "equilibrio_recursivo.csv", index=False)
    (OUT / "fase3_tablas.md").write_text(tables(res, att, rec, extra), encoding="utf-8")
    plots(res, rec, extra)
    print((OUT / "fase3_tablas.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    if "--replot" in sys.argv:
        replot()
        sys.exit(0)
    sys.exit(main())
