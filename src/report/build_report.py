"""Reporte HTML mensual: python -m src.report.build_report [YYYY-MM-DD del snapshot]

Lee el contexto guardado por src.run_monthly (data/processed/monthly_context_<fecha>.pkl) y todo el archivo de
pronósticos; no reestima nada. Escribe reports/<YYYY-MM>.html, autocontenido (gráficos embebidos).
"""

from __future__ import annotations

import base64
import html
import io
import pickle
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.evaluate.errors import attach_observed, point_metrics
from src.ingest.common import ROOT, load_yaml
from src.transform.ratios import monthly_nominal_gdp_sa

VAR_LABEL = {"circ": "Circulante en poder del público", "dav": "Depósitos a la vista no remunerados",
             "m2": "M2 transaccional privado", "m2amp": "M2 ampliado (+ FCI de billeteras)",
             "m2priv": "M2 privado", "m3": "M3 privado"}
MAIN_VARS = ["m2", "circ", "dav"]
KEY_MODELS = ["ENS_F1_avg", "ENS_F1_w", "F1|minimal|long", "IC1_F1", "TVP", "DIFF", "ARIMA", "RW"]
HEAD_MODEL, FALLBACK = "ENS_F1_avg", "F1|minimal|long"

CSS = """
:root{--bg:#ffffff;--fg:#1d2330;--muted:#5b6475;--card:#f5f7fa;--line:#d9dee7;--accent:#1f5aa6;--warn:#b5481f;--ok:#2e7d4f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#14171c;--fg:#e6e9ef;--muted:#9aa3b2;--card:#1d2128;--line:#2e3440;--accent:#6fa3e8;--warn:#f08a5d;--ok:#6cc08b}}
:root[data-theme="dark"]{--bg:#14171c;--fg:#e6e9ef;--muted:#9aa3b2;--card:#1d2128;--line:#2e3440;--accent:#6fa3e8;--warn:#f08a5d;--ok:#6cc08b}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}
main{max-width:1080px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.2rem;margin-top:2.2em;border-bottom:1px solid var(--line);padding-bottom:.3em}
h3{font-size:1rem;margin-top:1.6em}.muted{color:var(--muted)}.card{background:var(--card);border-radius:8px;padding:12px 16px;margin:12px 0}
.warn{color:var(--warn);font-weight:600}.ok{color:var(--ok);font-weight:600}
table{border-collapse:collapse;font-size:.85rem;margin:8px 0;width:100%;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:4px 8px;text-align:right;white-space:nowrap}th{color:var(--muted);font-weight:600}
td:first-child,th:first-child{text-align:left}img{max-width:100%;height:auto;background:#fff;border-radius:6px}
ul{padding-left:1.2em}
"""


def _img(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f'<img alt="" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def _table(df: pd.DataFrame, nd: int = 2, index: bool = True) -> str:
    return df.round(nd).to_html(index=index, border=0, na_rep="–", escape=True)


def load(snapshot: str):
    with open(ROOT / "data" / "processed" / f"monthly_context_{snapshot}.pkl", "rb") as fh:
        ctx = pickle.load(fh)
    from src.run_monthly import load_archive

    return ctx, load_archive()


def current_forecasts(arch: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    return arch[(arch["origin"] == ctx["origin"]) & (arch["source_file"] == f"realtime_{ctx['snapshot']}.csv")]


def fan_chart(var: str, ctx: dict, cur: pd.DataFrame, months: int) -> tuple[str, pd.DataFrame]:
    d = ctx["od_data"]
    y = d[f"y_{var}"].dropna()
    y = y[y.index > ctx["origin"] - months]
    lvl = lambda v: np.exp(v) / 1000
    g = cur[(cur["variable"] == var) & (cur["scenario"] == "exante_rem")]
    head = HEAD_MODEL if (g["model"] == HEAD_MODEL).any() else FALLBACK
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(y.index.to_timestamp(), lvl(y), color="black", lw=1.8, label="observado s.e.")
    x0 = ctx["origin"].to_timestamp()
    h = g[g["model"] == head].sort_values("target")
    xs = [x0] + [t.to_timestamp() for t in h["target"]]
    y0 = lvl(y.iloc[-1])
    ax.fill_between(xs, [y0] + list(lvl(h["q0.025"])), [y0] + list(lvl(h["q0.975"])), color="#1f5aa6", alpha=0.12,
                    label="95% (solo shocks)")
    ax.fill_between(xs, [y0] + list(lvl(h["q0.16"])), [y0] + list(lvl(h["q0.84"])), color="#1f5aa6", alpha=0.25,
                    label="68%")
    ax.plot(xs, [y0] + list(lvl(h["q0.5"])), color="#1f5aa6", lw=2, label=f"{head} (mediana)")
    for m, c, ls in [("RW", "#555555", "--"), ("IC1_F1", "#2e8b57", ":"), ("TVP", "#b5481f", ":")]:
        gm = g[g["model"] == m].sort_values("target")
        if not gm.empty:
            ax.plot(xs, [y0] + list(lvl(gm["point"])), color=c, ls=ls, lw=1.3, label=m)
    for fm in ctx["filled"]:
        ax.axvspan(pd.Period(fm, "M").to_timestamp(), (pd.Period(fm, "M") + 1).to_timestamp(), color="#e39a3b",
                   alpha=0.15, lw=0)
    ax.set_title(f"{VAR_LABEL[var]}: miles de millones de $ de dic-2016, s.e. (escenario REM)", fontsize=9, loc="left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=3, loc="upper left")
    tab = pd.DataFrame({"mes": [str(t) for t in h["target"]],
                        "mediana": lvl(h["q0.5"]).to_numpy(),
                        "var. vs origen (%)": 100 * (np.exp(h["q0.5"] - y.iloc[-1]) - 1).to_numpy(),
                        "68% inf.": lvl(h["q0.16"]).to_numpy(), "68% sup.": lvl(h["q0.84"]).to_numpy()})
    rw = g[g["model"] == "RW"].sort_values("target")
    tab["RW"] = lvl(rw["point"]).to_numpy() if len(rw) == len(tab) else np.nan
    if "pct_q0.5" in h and h["pct_q0.5"].notna().any():
        tab["% PIB (mediana)"] = h["pct_q0.5"].to_numpy()
    return _img(fig), tab.set_index("mes")


def ec_chart(ctx: dict, stab: pd.DataFrame, months: int) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.2), sharey=False)
    for ax, var in zip(axes, MAIN_VARS):
        ec = ctx["ec"].get(var)
        if ec is not None:
            e = ec[ec.index > ctx["origin"] - months]
            ax.plot(e.index.to_timestamp(), 100 * e, color="#1f5aa6", lw=1.4, label="brecha en la muestra (fit actual)")
        s = stab[stab["variable"] == var].sort_values("origin")
        s = s[s["origin"] > ctx["origin"] - months]
        if not s.empty:
            ax.scatter(s["origin"].apply(lambda p: p.to_timestamp()), 100 * s["ec"], s=10, color="#b5481f",
                       label="brecha en cada origen (reestimada)")
        ax.axhline(0, color="black", lw=0.7)
        ax.set_title(VAR_LABEL[var], fontsize=8, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    axes[0].set_ylabel("ec = y − y_lp (%)", fontsize=8)
    axes[0].legend(fontsize=6.5)
    return _img(fig)


def error_section(arch: pd.DataFrame, ctx: dict) -> tuple[str, str]:
    latest = ctx["od_data"][[c for c in ctx["od_data"] if c.startswith("y_")]]
    a = arch[(arch["target"] <= ctx["origin"]) & (arch["scenario"] == "exante_rem")]
    ev = attach_observed(a, latest)
    ev["fuente"] = np.where(ev["realtime"].astype(str) == "true", "tiempo real", "pseudo")
    out = []
    for label, sub in [("Todo el archivo", ev), ("Últimos 12 meses objetivo", ev[ev["target"] > ctx["origin"] - 12]),
                       ("Solo tiempo real", ev[ev["fuente"] == "tiempo real"])]:
        if sub.dropna(subset=["error"]).empty:
            out.append(f"<h3>{label}</h3><p class='muted'>Sin pronósticos evaluables todavía.</p>")
            continue
        pm = point_metrics(sub)
        pm = pm[pm["model"].isin(KEY_MODELS) & pm["variable"].isin(MAIN_VARS + ["m3", "m2amp"]) & pm["h"].isin([1, 3, 6])]
        t = pm.pivot_table(index=["variable", "model"], columns="h", values="RMSE_rel")
        t.columns = [f"RMSE rel h{c}" for c in t.columns]
        n = pm.pivot_table(index=["variable", "model"], columns="h", values="N")
        t["N h1"] = n.get(1)
        t["RMSE h1 (%)"] = pm[pm["h"] == 1].set_index(["variable", "model"])["RMSE"]
        out.append(f"<h3>{label}</h3>" + _table(t))
    # Errores a h=3 en el tiempo
    fig, axes = plt.subplots(1, 2, figsize=(11, 3))
    for ax, var in zip(axes, ["m2", "circ"]):
        s = ev[(ev["variable"] == var) & (ev["h"] == 3)]
        for m, c in [("ENS_F1_avg", "#1f5aa6"), ("F1|minimal|long", "#c0504d"), ("RW", "#555555")]:
            q = s[s["model"] == m].sort_values("target")
            ax.plot(q["target"].apply(lambda p: p.to_timestamp()), 100 * q["error"], color=c, lw=1.2, label=m)
        ax.axhline(0, color="black", lw=0.7)
        ax.axvline(pd.Period("2025-11", "M").to_timestamp(), color="#888", ls=":", lw=0.8)
        ax.set_title(f"{VAR_LABEL[var]}: error a 3 meses (%), pronóstico − observado", fontsize=8, loc="left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    axes[0].legend(fontsize=7)
    return "".join(out), _img(fig)


def bcra_section(ctx: dict) -> tuple[str, str]:
    b = pd.read_csv(ROOT / "data" / "bcra_forecasts.csv")
    last = b[b["origin_month"] == b["origin_month"].max()]
    d = ctx["od_data"]
    gdp = monthly_nominal_gdp_sa(d["act"], d["log_p"], ctx["origin"])
    pct = (np.exp(d["y_m2"]) * np.exp(d["log_p"]) / 100 / gdp * 100).dropna()
    pct = pct[pct.index > ctx["origin"] - 18]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(pct.index.to_timestamp(), pct, color="black", lw=1.6, label="observado, nuestro método (última vintage)")
    o = pd.Period(last["origin_month"].iloc[0], "M")
    xs = [o.to_timestamp()] + [pd.Period(t, "M").to_timestamp() for t in last["target_month"]]
    ax.plot(xs, [last["origin_value"].iloc[0]] + list(last["p50"]), "o--", color="#1f5aa6", label="BCRA base")
    ax.fill_between(xs[1:], last["lo68"], last["hi68"], color="#1f5aa6", alpha=0.2, label="BCRA 68%")
    ax.plot(xs, [last["origin_value"].iloc[0]] + list(last["observed_same_vintage"]), "s-", color="#b5481f",
            label="observado en el gráfico del BCRA")
    ax.set_title(f"M2 transaccional, % del PIB s.e. Último programa del BCRA: {last['vintage_label'].iloc[0]}",
                 fontsize=9, loc="left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    t = last[["target_month", "p50", "lo68", "hi68", "observed_same_vintage"]].copy()
    t["observado (nuestro método)"] = [pct.get(pd.Period(x, "M"), np.nan) for x in t["target_month"]]
    t["cambio BCRA base (pp)"] = t["p50"] - last["origin_value"].iloc[0]
    t["cambio observado BCRA (pp)"] = t["observed_same_vintage"] - last["origin_value"].iloc[0]
    t["cambio observado nuestro (pp)"] = t["observado (nuestro método)"] - pct.get(o, np.nan)
    note = ("<p class='muted'>Valores del BCRA leídos a ojo de gráficos publicados (±0,02 pp; "
            "<code>read_method</code> en <code>data/bcra_forecasts.csv</code>). Los niveles en % del PIB no son "
            "comparables entre vintages: comparar cambios.</p>")
    return _img(fig), _table(t.set_index("target_month"), 3) + note


def aggregates_table(ctx: dict) -> str:
    d = ctx["od_data"]
    o = ctx["origin"]
    rows = []
    for var in ["m2", "m2amp", "m2priv", "m3", "circ", "dav"]:
        y = d.get(f"y_{var}")
        if y is None or pd.isna(y.get(o)):
            continue
        rows.append({"agregado": VAR_LABEL[var], "nivel (miles de mill. $ dic-16)": np.exp(y[o]) / 1000,
                     "var. 3 meses (%)": 100 * (np.exp(y[o] - y.get(o - 3, np.nan)) - 1),
                     "var. 12 meses (%)": 100 * (np.exp(y[o] - y.get(o - 12, np.nan)) - 1)})
    t = pd.DataFrame(rows).set_index("agregado")
    note = ""
    amp = d["y_m2amp"].dropna() if "y_m2amp" in d else pd.Series(dtype=float)
    if not amp.empty:
        last = amp.index.max()
        share = 100 * (np.exp(amp[last]) - np.exp(d["y_m2"][last])) / np.exp(d["y_m2"][last])
        note = f"<p class='muted'>FCI de billeteras / M2 transaccional en {last}: {share:.1f}%."
        if last < o:
            note += (f" El M2 ampliado no figura en {o}: la serie de FCI de billeteras (informe de pagos "
                     f"minoristas) llega hasta {last}.")
        note += "</p>"
    return _table(t) + note


PAGES_URL = "https://tobicardenas.github.io/demanda-dinero"


def write_summary(run_month: str, ctx: dict, tabs: dict, al: pd.DataFrame, flags: list[str]) -> None:
    """reports/<AAAA-MM>_resumen.md: cuerpo del aviso mensual (issue de GitHub -> email)."""
    import re as _re

    L = [f"Reporte de demanda de dinero **{run_month}**: {PAGES_URL}/{run_month}.html", "",
         f"Origen {ctx['origin']} (snapshot {ctx['snapshot']}). Pronóstico ex ante con el escenario REM, en términos "
         "reales y sin estacionalidad.", ""]
    for var, t in tabs.items():
        last = t.iloc[-1]
        L.append(f"- **{VAR_LABEL[var]}**: {last['var. vs origen (%)']:+.1f}% a {t.index[-1]} (mediana; banda 68% "
                 f"{100 * (last['68% inf.'] / last['RW'] - 1):+.1f}% a {100 * (last['68% sup.'] / last['RW'] - 1):+.1f}%). "
                 "Caminata aleatoria: sin cambio.")
    L.append("")
    if al["alarma"].any():
        L.append("⚠️ **Alarma de inestabilidad del equilibrio** en: "
                 + ", ".join(VAR_LABEL.get(v, v) for v in al.loc[al["alarma"], "variable"])
                 + ". Usar la caminata aleatoria como referencia.")
    else:
        L.append("Sin alarmas de inestabilidad del equilibrio.")
    clean = [_re.sub("<[^>]+>", "", f) for f in flags if not f.startswith("AVISO")]
    if clean:
        L += ["", "Notas:"] + [f"- {f}" for f in clean]
    (ROOT / "reports" / f"{run_month}_resumen.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def build(snapshot: str) -> str:
    ctx, arch = load(snapshot)
    months = load_yaml("settings.yaml")["monthly"]["history_months"]
    from src.run_monthly import load_stability

    stab = load_stability()
    cur = current_forecasts(arch, ctx)
    run_month = snapshot[:7]
    al = ctx["alarms"]
    alarm_html = (f"<p class='warn'>Alarma de inestabilidad del equilibrio en: "
                  f"{', '.join(VAR_LABEL.get(v, v) for v in al.loc[al['alarma'], 'variable'])}. "
                  f"Los pronósticos de los modelos con equilibrio (F1, F2, ensambles F1/F2) no son confiables este mes; "
                  f"usar la RW como referencia.</p>" if al["alarma"].any() else
                  "<p class='ok'>Sin alarmas de inestabilidad del equilibrio.</p>")
    flags = []
    if ctx["filled"]:
        flags.append(f"Actividad (EMAE) completada con el PIB del REM en {', '.join(ctx['filled'])} "
                     f"(último EMAE publicado: {ctx['last_emae']}).")
    if ctx["seasonal_method"] != "x13":
        flags.append("<span class='warn'>Desestacionalización con STL provisoria: X13 no disponible.</span>")
    if ctx["fails"]:
        flags.append(f"{len(ctx['fails'])} modelos no pudieron estimarse: "
                     + ", ".join(f"{f['variable']}/{f['model']}" for f in ctx["fails"]))
    flags += [html.escape(w) for w in ctx["validation_warnings"]]

    parts = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Demanda de dinero {run_month}</title><style>{CSS}</style></head><body><main>",
             f"<h1>Demanda real de dinero: reporte {run_month}</h1>",
             f"<p class='muted'>Snapshot {ctx['snapshot']} · origen {ctx['origin']} · horizonte 6 meses · "
             f"escenario ex ante REM. Saldos reales s.e. en miles de millones de $ de dic-2016.</p>",
             "<div class='card'>" + alarm_html + "<ul>" + "".join(f"<li>{f}</li>" for f in flags) + "</ul></div>"]

    parts.append("<h2>1. Pronóstico a 6 meses</h2><p class='muted'>Cabecera: ensamble de la familia lineal (promedio "
                 "simple de los 3 mejores de los últimos 12 meses). La caminata aleatoria (RW) se publica siempre al "
                 "lado: en 2026 ningún modelo le ganó de forma sistemática (Fase 4). Bandas solo con shocks: son "
                 "angostas, la cobertura efectiva es menor que la nominal.</p>")
    tabs = {}
    for var in MAIN_VARS:
        if (cur["variable"] == var).any():
            img, tab = fan_chart(var, ctx, cur, months)
            tabs[var] = tab
            parts += [f"<h3>{VAR_LABEL[var]}</h3>", img, _table(tab, 2)]
    write_summary(run_month, ctx, tabs, al, flags)

    parts.append("<h2>2. Brecha al equilibrio y alarma</h2><p class='muted'>ec = y − y_lp del modelo lineal (F1 mínima). "
                 "Negativa: el modelo cree que la demanda está por debajo de su equilibrio y proyecta suba. La alarma "
                 "compara la revisión del equilibrio del mes anterior con la media de 2021–oct-25.</p>")
    parts += [ec_chart(ctx, stab, months), _table(al.set_index("variable"), 3)]

    err_tables, err_img = error_section(arch, ctx)
    parts += ["<h2>3. Errores acumulados de todos los pronósticos archivados</h2>",
              "<p class='muted'>RMSE relativo a la caminata aleatoria (< 1 = mejor), escenario REM, contra la última "
              "vintage. El archivo incluye el pseudo fuera de muestra de la Fase 4 y cada corrida en tiempo real.</p>",
              err_img, err_tables]

    bimg, btab = bcra_section(ctx)
    parts += ["<h2>4. Último programa del BCRA</h2>", bimg, btab]
    parts += ["<h2>5. Agregados alternativos (hipótesis 6)</h2>", aggregates_table(ctx)]
    parts += ["<h2>6. Frescura de las fuentes</h2>", _table(ctx["freshness"].set_index("serie"), 0)]
    parts.append("<p class='muted'>Generado por <code>python -m src.run_monthly</code>. Decisiones y protocolo en "
                 "DECISIONS.md. Pronósticos archivados en data/forecasts/ (nunca se reescriben).</p></main></body></html>")
    out = ROOT / "reports" / f"{run_month}.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    snap = sys.argv[1] if len(sys.argv) > 1 else sorted(
        p.stem.removeprefix("monthly_context_") for p in (ROOT / "data" / "processed").glob("monthly_context_*.pkl"))[-1]
    print(build(snap))
