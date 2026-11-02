"""Fase 2: réplica. python -m src.report.fase2

(a) Gráfico 1 del AT 5: circulante real s.e., estimado con datos hasta dic-2024 y escenario 2025
    realizado. Acepta si F2 queda más cerca del observado que F1 y la brecha F1-F2 a dic-2025 es del
    orden del ~20% del nivel (BCRA: lineal ~275, no lineal ~226, observado ~228).
Base = trayectoria central determinística (shocks nulos, parámetros estimados); el bootstrap da las bandas.
(b) Programa dic-2025: estimado hasta nov-2025, escenario REM de fin de nov-2025, M2 transaccional en
    % del PIB. Acepta si la base sube entre dic-25 y mar-26 y el cambio nov-25 -> mar-26 queda a ±0,1 pp
    del cambio del BCRA (5,80 -> 6,03). Se comparan cambios y no niveles: el nivel depende de la vintage
    de factores estacionales y de PIB, que no es pública.
Se reportan todas las variantes; la de cabecera se fijó en settings.yaml antes de ver resultados.
"""

from __future__ import annotations

import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.ingest.common import ROOT, load_yaml
from src.models.ecm_logistic import LogisticECM
from src.models.vecm import VECMModel
from src.transform import model_data as md
from src.transform.ratios import monthly_nominal_gdp_sa, pct_gdp
from src.transform.seasonal import method as sa_method

OUT = ROOT / "reports" / "fase2"
BCRA_CHART1 = {"F1_vecm": 275, "F2_logistic": 226, "observed": 228}


def variants(component: str) -> list[tuple]:
    rep = load_yaml("settings.yaml")["replication"]
    samples = dict(rep["samples"])
    if component in ("dav", "m2"):
        samples.pop("from_2017")  # decisión 2026-10-30: DAV y M2 transaccional existen desde 2021
    out = []
    for sname, sample in samples.items():
        for dname, dets in rep["determinants"].items():
            out.append((VECMModel, "F1_vecm", dname, dets, sname, sample))
            if dname != "alt_linear":
                out.append((LogisticECM, "F2_logistic", dname, dets, sname, sample))
    return out


def run_component(od: md.OriginData, component: str, scenario: pd.DataFrame, h: int, n_sims: int, seed: int):
    rows, models = [], {}
    grid = load_yaml("settings.yaml")["replication"]["logistic_grid"]
    for cls, fam, dname, dets, sname, sample in variants(component):
        kw = {"grid": grid} if cls is LogisticECM else {}
        name = f"{fam}|{dname}|{sname}"
        t = time.time()
        try:
            m = cls(component, dets, sample, seed=seed, name=name, **kw).fit(od.data, od.origin)
            fc = m.forecast(scenario, h, n_sims)
        except Exception as exc:  # se reporta, no se esconde
            rows.append({"component": component, "family": fam, "determinants": dname, "sample": sname,
                         "error": repr(exc)[:200]})
            print(f"  {name:40s} FALLÓ: {exc!r}")
            continue
        models[name] = m
        y0 = od.data.at[od.origin, f"y_{component}"]
        ec0 = y0 - m.long_run(m.d, m.params.lr)[-1]
        info = {"component": component, "family": fam, "determinants": dname, "sample": sname,
                "n_obs": len(m.d) - m.t0, "p": m.p, "theta": m.params.theta, "ec_origin": ec0,
                "sigma": m.params.sigma}
        if fam == "F2_logistic":
            info.update({k: m.params.lr[k] for k in ["theta_alt", "lambda", "b_inf", "a1", "a2"]})
            info.update(m.identification())
            info["w_origin"] = float(m.w_path().iloc[-1])
        else:
            info.update(m.structural())
            info.update(m.johansen_trace())
        for tm, r in fc.iterrows():
            rows.append({**info, "target": tm, "h": (tm - od.origin).n, **r.to_dict()})
        print(f"  {name:40s} n={info['n_obs']:3d} p={m.p} theta={m.params.theta:+.3f} ec0={ec0:+.3f} "
              f"({time.time() - t:.0f}s)")
    return pd.DataFrame(rows), models


def observed_latest(component: str) -> pd.Series:
    panel = md.load_panel()
    return md.build(panel.index.max(), panel).data[f"y_{component}"]


# --- (a) Gráfico 1 --------------------------------------------------------------------------

def test_a(n_sims: int, seed: int) -> dict:
    origin, h = pd.Period("2024-12", "M"), 12
    od = md.build(origin)
    sc = md.scenario_realized(od, h)
    res, models = run_component(od, "circ", sc, h, n_sims, seed)
    obs = observed_latest("circ")
    lvl = lambda y: np.exp(y) / 1000  # miles de millones de ARS de dic-2016
    last = res[res["target"] == origin + h].copy()
    last["level_p50"] = lvl(last["point"])  # trayectoria central determinística
    obs_dec = float(lvl(obs[origin + h]))
    head = load_yaml("settings.yaml")["replication"]["headline"]
    hd = last[(last["determinants"] == head["determinants"]) & (last["sample"] == head["sample"])]
    f1 = float(hd.loc[hd["family"] == "F1_vecm", "level_p50"].iloc[0])
    f2 = float(hd.loc[hd["family"] == "F2_logistic", "level_p50"].iloc[0])
    avg = last.groupby("family")["level_p50"].mean()
    out = {"obs_dec25": obs_dec, "f1": f1, "f2": f2, "f1_avg": avg["F1_vecm"], "f2_avg": avg["F2_logistic"],
           "gap_pct": (f1 - f2) / obs_dec * 100, "gap_pct_avg": (avg["F1_vecm"] - avg["F2_logistic"]) / obs_dec * 100,
           "bcra_gap_pct": (BCRA_CHART1["F1_vecm"] - BCRA_CHART1["F2_logistic"]) / BCRA_CHART1["observed"] * 100}
    out["f2_closer"] = abs(f2 - obs_dec) < abs(f1 - obs_dec)
    out["f2_closer_avg"] = abs(out["f2_avg"] - obs_dec) < abs(out["f1_avg"] - obs_dec)
    out["pass"] = out["f2_closer"] and 10 <= out["gap_pct"] <= 40
    res.to_csv(OUT / "a_grafico1_variantes.csv", index=False)

    fig, ax = plt.subplots(figsize=(8, 4))
    o = lvl(obs[obs.index >= pd.Period("2019-01", "M")])
    ax.plot(o.index.to_timestamp(), o.values, color="black", lw=1.6, label="observado s.e. (última vintage)")
    colors = {"F1_vecm": "#c0504d", "F2_logistic": "#1f5aa6"}
    for fam, col in colors.items():
        r = res[(res["family"] == fam) & (res["determinants"] == head["determinants"]) & (res["sample"] == head["sample"])]
        x = [origin.to_timestamp()] + list(r["target"].apply(lambda p: p.to_timestamp()))
        y0 = lvl(od.data.at[origin, "y_circ"])
        ax.plot(x, [y0] + list(lvl(r["point"])), color=col, lw=1.8, label=f"{fam} (cabecera)")
        ax.fill_between(x[1:], lvl(r["q0.16"]), lvl(r["q0.84"]), color=col, alpha=0.15)
        for name, m in models.items():
            if name.startswith(fam) and not name.endswith(f"{head['determinants']}|{head['sample']}"):
                rr = res[(res["family"] == fam) & (res["determinants"] + "|" + res["sample"] == name.split("|", 1)[1])]
                ax.plot(x, [y0] + list(lvl(rr["point"])), color=col, lw=0.6, alpha=0.5)
    ax.axvline(origin.to_timestamp(), color="#888", ls=":")
    ax.set_title("(a) Circulante real s.e., miles de millones de $ de dic-2016. Origen dic-24, escenario realizado",
                 fontsize=9, loc="left")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "a_grafico1.png", dpi=120)
    plt.close(fig)

    lm = models.get(f"F2_logistic|{head['determinants']}|{head['sample']}")
    if lm is not None:
        plot_logistic(lm, od, sc, OUT / "a_logistica_perfil_w.png", "(a) circulante, origen dic-24")
    return out


def plot_logistic(m: LogisticECM, od, sc, path, title: str) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    pv = m.profile.pivot(index="lambda", columns="theta_alt", values="ssr")
    im = axes[0].imshow(np.log(pv.values), aspect="auto", origin="lower", cmap="viridis",
                        extent=[pv.columns.min(), pv.columns.max(), 0, len(pv.index)])
    axes[0].set_yticks(np.arange(len(pv.index)) + 0.5, [f"{v:g}" for v in pv.index], fontsize=7)
    axes[0].set_xlabel("theta_alt (alt estandarizada)", fontsize=8)
    axes[0].set_ylabel("lambda", fontsize=8)
    axes[0].set_title("log SCR concentrada", fontsize=9, loc="left")
    fig.colorbar(im, ax=axes[0])
    lr = m.params.lr
    axes[0].plot([lr["theta_alt"]], [list(pv.index).index(min(pv.index, key=lambda v: abs(v - lr["lambda"]))) + 0.5],
                 "r*", ms=10)
    w = m.w_path(pd.concat([m.d[["alt"]], sc[["alt"]]]))
    axes[1].plot(w.index.to_timestamp(), w.values, color="#1f5aa6")
    axes[1].axvline(od.origin.to_timestamp(), color="#888", ls=":")
    axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_title(f"w_t (theta_alt={lr['theta_alt']:.2f}, lambda={lr['lambda']:.2f})", fontsize=9, loc="left")
    axes[1].grid(alpha=0.25)
    fig.suptitle(title, fontsize=9, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# --- (b) Programa dic-2025 --------------------------------------------------------------------

def test_b(n_sims: int, seed: int) -> dict:
    origin, h = pd.Period("2025-11", "M"), 4
    od = md.build(origin)
    sc, notes = md.scenario_rem(od, h)
    results = {}
    for comp in ["circ", "dav", "m2"]:
        print(f" componente {comp}")
        results[comp] = run_component(od, comp, sc, h, n_sims, seed)
    allres = pd.concat([r[0] for r in results.values()])
    allres.to_csv(OUT / "b_programa_dic25_variantes.csv", index=False)

    gdp_m = monthly_nominal_gdp_sa(pd.concat([od.data["act"], sc["act"]]),
                                   pd.concat([od.data["log_p"], sc["log_p"]]), origin)
    log_p = pd.concat([od.data["log_p"], sc["log_p"]])
    cheq = md.load_panel()["cheques_canc"]
    cheq_real = float(cheq[origin] / np.exp(od.data.at[origin, "log_p"]) * 100)
    head = load_yaml("settings.yaml")["replication"]["headline"]

    def pick(comp, fam, det, smp, col="point"):
        r = results[comp][0]
        r = r[(r["family"] == fam) & (r["determinants"] == det) & (r["sample"] == smp)]
        return pd.Series(r[col].to_numpy(), index=pd.PeriodIndex(r["target"], freq="M"))

    def as_pct(real_level: pd.Series) -> pd.Series:
        return pct_gdp(real_level, log_p, gdp_m)

    y0 = {c: od.data.at[origin, f"y_{c}"] for c in ["circ", "dav", "m2"]}
    sum0 = np.exp(y0["circ"]) + np.exp(y0["dav"]) + cheq_real
    origin_pct = float(as_pct(pd.Series([sum0], index=[origin])).iloc[0])
    origin_pct_m2 = float(as_pct(pd.Series([np.exp(y0["m2"])], index=[origin])).iloc[0])

    paths = {}
    dav_head = "from_2021" if head["sample"] == "from_2017" else head["sample"]
    for fam in ["F1_vecm", "F2_logistic"]:
        comp_sum = (np.exp(pick("circ", fam, head["determinants"], head["sample"]))
                    + np.exp(pick("dav", fam, head["determinants"], dav_head)) + cheq_real)
        paths[f"{fam} componentes (cabecera)"] = as_pct(comp_sum) - origin_pct
        paths[f"{fam} agregado (cabecera)"] = as_pct(np.exp(pick("m2", fam, head["determinants"], dav_head))) - origin_pct_m2
        # promedio simple de todas las variantes de la familia, por componente
        r = allres[(allres["family"] == fam) & allres["point"].notna()]
        avg = r.groupby(["component", "target"])["point"].apply(lambda v: np.log(np.exp(v).mean())).unstack(0)
        avg.index = pd.PeriodIndex(avg.index, freq="M")
        paths[f"{fam} componentes (prom. variantes)"] = as_pct(np.exp(avg["circ"]) + np.exp(avg["dav"]) + cheq_real) - origin_pct

    bcra = pd.Series({pd.Period("2025-12", "M"): 5.83 - 5.80, pd.Period("2026-03", "M"): 6.03 - 5.80})
    tbl = pd.DataFrame(paths).T
    tbl.columns = [str(c) for c in tbl.columns]
    mar, dec = "2026-03", "2025-12"
    key = "F1_vecm componentes (cabecera)"
    out = {"origin_pct_ours": origin_pct, "origin_pct_bcra": 5.80, "table": tbl, "notes": notes,
           "bcra_dec": bcra.iloc[0], "bcra_mar": bcra.iloc[1],
           "f1_dec": tbl.loc[key, dec], "f1_mar": tbl.loc[key, mar]}
    out["rises"] = out["f1_mar"] > out["f1_dec"] > 0 or (out["f1_mar"] > 0 and out["f1_mar"] > out["f1_dec"])
    out["within_01"] = abs(out["f1_mar"] - out["bcra_mar"]) <= 0.1
    out["pass"] = out["rises"] and out["within_01"]
    out["ec_origin"] = (allres[allres["h"] == 1].set_index(["component", "family", "determinants", "sample"])
                        ["ec_origin"])

    fig, ax = plt.subplots(figsize=(7, 3.8))
    x = [origin.to_timestamp()] + [p.to_timestamp() for p in tbl.columns.map(lambda c: pd.Period(c, "M"))]
    for (name, row), c in zip(tbl.iterrows(), ["#c0504d", "#e39a98", "#f2c6c4", "#1f5aa6", "#8fb0dc", "#c5d6ee"]):
        ax.plot(x, [0] + list(row.values), color=c, lw=1.6 if "cabecera" in name else 1.0, label=name)
    ax.plot([origin.to_timestamp()] + [p.to_timestamp() for p in bcra.index], [0] + list(bcra.values), "ks--",
            label="BCRA base (IPOM, lectura a ojo)")
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_ylabel("cambio vs nov-25, pp del PIB", fontsize=8)
    ax.set_title("(b) Programa dic-25: M2 transaccional, % PIB s.e., escenario REM nov-25", fontsize=9, loc="left")
    ax.legend(fontsize=6.5)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "b_programa_dic25.png", dpi=120)
    plt.close(fig)

    lm = results["circ"][1].get(f"F2_logistic|{head['determinants']}|{head['sample']}")
    if lm is not None:
        plot_logistic(lm, od, sc, OUT / "b_logistica_circ_perfil_w.png", "(b) circulante, origen nov-25")
    return out


def write_report(a: dict, b: dict) -> None:
    f = lambda x, n=1: f"{x:,.{n}f}"
    L = ["# Fase 2: réplica", "",
         f"Desestacionalización: {sa_method()} (pseudo tiempo real, truncada en cada origen). "
         "Cabecera: determinantes mínimos, muestra desde 2017 (DAV: desde 2021).", "",
         "## (a) Gráfico 1: circulante real s.e. a dic-2025 (miles de millones de $ de dic-2016)", "",
         "| | F1 lineal | F2 no lineal | Observado | Brecha (F1−F2)/obs |", "|---|---|---|---|---|",
         f"| BCRA (lectura a ojo, $ de 2016) | {BCRA_CHART1['F1_vecm']} | {BCRA_CHART1['F2_logistic']} "
         f"| {BCRA_CHART1['observed']} | {f(a['bcra_gap_pct'])}% |",
         f"| Réplica, cabecera | {f(a['f1'])} | {f(a['f2'])} | {f(a['obs_dec25'])} | {f(a['gap_pct'])}% |",
         f"| Réplica, promedio de variantes | {f(a['f1_avg'])} | {f(a['f2_avg'])} | {f(a['obs_dec25'])} "
         f"| {f(a['gap_pct_avg'])}% |", "",
         f"- ¿F2 más cerca del observado? Cabecera: {'sí' if a['f2_closer'] else 'no'}; "
         f"promedio de variantes: {'sí' if a['f2_closer_avg'] else 'no'}.",
         f"- **Criterio (a): {'CUMPLE' if a['pass'] else 'NO CUMPLE'}** (F2 más cerca y brecha entre 10% y 40%).", "",
         "## (b) Programa dic-2025: M2 transaccional, cambio en pp del PIB respecto de nov-25", "",
         f"Nivel en el origen: réplica {f(b['origin_pct_ours'], 2)}% contra BCRA 5,80%.", "",
         b["table"].map(lambda v: f"{v:+.3f}").to_markdown() if hasattr(b["table"], "map") else "", "",
         f"BCRA base: dic-25 {b['bcra_dec']:+.2f}, mar-26 {b['bcra_mar']:+.2f}.", "",
         f"- **Criterio (b): {'CUMPLE' if b['pass'] else 'NO CUMPLE'}** (suba dic→mar: "
         f"{'sí' if b['rises'] else 'no'}; mar-26 a ±0,1 pp del BCRA: {'sí' if b['within_01'] else 'no'}; "
         f"réplica F1 {b['f1_mar']:+.3f} contra BCRA {b['bcra_mar']:+.2f}).", "",
         "Supuestos del escenario REM:", ""] + [f"- {n}" for n in b["notes"]] + [""]
    (OUT / "fase2.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_yaml("settings.yaml")
    n_sims, seed = cfg["replication"]["n_sims"], cfg["forecast"]["seed"]
    print("(a) Gráfico 1")
    a = test_a(n_sims, seed)
    print("(b) Programa dic-2025")
    b = test_b(n_sims, seed)
    write_report(a, b)
    print((OUT / "fase2.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
