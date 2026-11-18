"""Secciones del reporte mensual agregadas en nov-2026:

- comparación con la corrida anterior (qué cambió en el pronóstico, en los parámetros y en los datos);
- semáforo de desempeño reciente (¿el modelo principal viene errando más que "igual que hoy"?);
- explicaciones en lenguaje simple para cada gráfico.

Todo se arma con lo archivado en el repo (data/runs/<fecha>/ y data/forecasts/), nada se reestima.
"""

from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.evaluate.errors import attach_observed
from src.ingest.common import ROOT, load_yaml

RUNS_DIR = ROOT / "data" / "runs"
HEAD, FALLBACK = "ENS_F1_avg", "F1|minimal|long"
SHORT = {"m2": "M2 transaccional", "circ": "circulante", "dav": "depósitos a la vista no remunerados",
         "m3": "M3 privado", "m2priv": "M2 privado"}


# --- utilidades ------------------------------------------------------------------------------

# Artículo y número de cada variable, para que las frases concuerden ("los depósitos ... suben").
ART = {"m2": ("el", False), "circ": ("el", False), "dav": ("los", True), "m3": ("el", False), "m2priv": ("el", False)}
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def name(var: str) -> str:
    return f"{ART[var][0]} {SHORT[var]}"


def plural(var: str, sing: str, plur: str) -> str:
    return plur if ART[var][1] else sing


def mes(p) -> str:
    p = pd.Period(str(p), "M")
    return f"{MES[p.month - 1]}-{str(p.year)[2:]}"


def explain(title: str, body: str, criollo: str | None = None) -> str:
    """Recuadro "¿Cómo se lee?" con un párrafo fijo y, si hay, una lectura con los números del mes."""
    out = f"<details class='explain' open><summary>{title}</summary><p>{body}</p>"
    if criollo:
        out += f"<p class='criollo'><strong>En criollo:</strong> {criollo}</p>"
    return out + "</details>"


def pct(x: float, nd: int = 1) -> str:
    return f"{x:+.{nd}f}%".replace(".", ",")


def num(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _head(g: pd.DataFrame) -> str:
    return HEAD if (g["model"] == HEAD).any() else FALLBACK


def previous_run(date: str) -> str | None:
    prev = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir() and p.name < date
                  and (p / "contexto.pkl").exists()) if RUNS_DIR.exists() else []
    return prev[-1] if prev else None


def load_run(date: str) -> tuple[dict, pd.DataFrame]:
    with open(RUNS_DIR / date / "contexto.pkl", "rb") as fh:
        ctx = pickle.load(fh)
    mp = RUNS_DIR / date / "modelo.csv"
    return ctx, (pd.read_csv(mp) if mp.exists() else pd.DataFrame())


def run_forecasts(arch: pd.DataFrame, date: str) -> pd.DataFrame:
    return arch[(arch["source_file"] == f"realtime_{date}.csv") & (arch["scenario"] == "exante_rem")]


# --- 1. Semáforo de desempeño -----------------------------------------------------------------

def performance(arch: pd.DataFrame, ctx: dict) -> pd.DataFrame:
    """RMSE del modelo principal / RMSE de "igual que hoy" (RW), últimos 12 meses objetivo, h = 1..3,
    escenario REM, todo el archivo (pseudo y tiempo real). Regla fijada en DECISIONS.md (nov-2026)."""
    cfg = load_yaml("settings.yaml")["monthly"]
    win, lo, hi = cfg["perf_window_months"], cfg["perf_green_below"], cfg["perf_red_above"]
    latest = ctx["od_data"][[c for c in ctx["od_data"] if c.startswith("y_")]]
    o = ctx["origin"]
    a = arch[(arch["scenario"] == "exante_rem") & (arch["h"] <= 3) & (arch["target"] <= o) & (arch["target"] > o - win)
             & arch["model"].isin([HEAD, FALLBACK, "RW"])]
    ev = attach_observed(a, latest).dropna(subset=["error"])
    rows = []
    for var in ["m2", "circ", "dav"]:
        e = ev[ev["variable"] == var]
        head = HEAD if (e["model"] == HEAD).any() else FALLBACK
        mh = e[e["model"] == head].set_index(["origin", "target"])["error"]
        rw = e[e["model"] == "RW"].set_index(["origin", "target"])["error"]
        common = mh.index.intersection(rw.index)
        if len(common) < 6:
            rows.append({"variable": var, "ratio": np.nan, "N": len(common), "estado": "sin datos suficientes"})
            continue
        r = np.sqrt((mh[common] ** 2).mean()) / np.sqrt((rw[common] ** 2).mean())
        estado = "verde" if r < lo else ("rojo" if r > hi else "amarillo")
        n_rt = int(e[(e["realtime"].astype(str) == "true") & (e["model"] == head)].shape[0])
        rows.append({"variable": var, "modelo": head, "ratio": r, "N": len(common), "N tiempo real": n_rt,
                     "estado": estado})
    return pd.DataFrame(rows)


def performance_html(perf: pd.DataFrame, ctx: dict) -> str:
    cfg = load_yaml("settings.yaml")["monthly"]
    color = {"verde": "var(--ok)", "amarillo": "#c9a227", "rojo": "var(--warn)", "sin datos suficientes": "var(--muted)"}
    label = {"verde": "le gana a 'igual que hoy'", "amarillo": "empata con 'igual que hoy'",
             "rojo": "viene errando más que 'igual que hoy'", "sin datos suficientes": "todavía sin datos suficientes"}
    items = []
    for _, r in perf.iterrows():
        ratio = "" if pd.isna(r["ratio"]) else f" (error relativo {num(r['ratio'], 2)}, N = {int(r['N'])})"
        items.append(f"<li><span style='color:{color[r['estado']]};font-weight:700'>●</span> "
                     f"<strong>{SHORT[r['variable']].capitalize()}</strong>: {label[r['estado']]}{ratio}</li>")
    reds = perf[perf["estado"] == "rojo"]
    if len(reds):
        verdict = ("<p class='warn'>El modelo principal viene errando más que la regla más simple en: "
                   + ", ".join(SHORT[v] for v in reds["variable"])
                   + ". Los parámetros se reestiman solos cada mes, pero eso no alcanza: conviene revisar la "
                     "especificación (ver DECISIONS.md, regla de desempeño).</p>")
    else:
        verdict = "<p class='ok'>Ninguna variable en rojo: no hace falta revisar la especificación este mes.</p>"
    body = ("Cada mes guardamos lo que el modelo pronosticó. Cuando llegan los datos de verdad, medimos cuánto se "
            "equivocó y lo comparamos con la regla más tonta posible: decir que el mes que viene va a ser igual que "
            f"hoy. Se usan los últimos {cfg['perf_window_months']} meses y pronósticos a 1, 2 y 3 meses. Un error "
            "relativo menor a 1 quiere decir que el modelo erra menos que esa regla (sirve); mayor a 1, que erra más. "
            f"Verde: menor a {num(cfg['perf_green_below'], 2)}. Rojo: mayor a {num(cfg['perf_red_above'], 2)}.")
    return explain("¿Cómo se lee el semáforo?", body) + "<ul>" + "".join(items) + "</ul>" + verdict


# --- 2. Comparación con la corrida anterior ----------------------------------------------------

def comparison(ctx: dict, model_now: pd.DataFrame, arch: pd.DataFrame) -> str:
    prev_date = previous_run(ctx["snapshot"])
    if prev_date is None:
        return "<p class='muted'>Es la primera corrida guardada: todavía no hay con qué comparar.</p>"
    pctx, pmodel = load_run(prev_date)
    cur = run_forecasts(arch, ctx["snapshot"])
    prev = run_forecasts(arch, prev_date)
    latest = ctx["od_data"]
    out = [f"<p class='muted'>Reporte anterior: corrida del {prev_date} (datos hasta {pctx['origin']}). "
           f"Este reporte: corrida del {ctx['snapshot']} (datos hasta {ctx['origin']}).</p>"]
    lines, tables = [], []
    for var in ["m2", "circ", "dav"]:
        gp, gc = prev[prev["variable"] == var], cur[cur["variable"] == var]
        if gp.empty or gc.empty:
            continue
        hp, hc = gp[gp["model"] == _head(gp)], gc[gc["model"] == _head(gc)]
        t = pd.DataFrame({"anterior": hp.set_index("target")["q0.5"], "actual": hc.set_index("target")["q0.5"]})
        obs = latest[f"y_{var}"]
        t["observado"] = [obs.get(m, np.nan) if m <= ctx["origin"] else np.nan for m in t.index]
        lvl = np.exp(t) / 1000
        tab = pd.DataFrame({"pronóstico anterior": lvl["anterior"], "pronóstico actual": lvl["actual"],
                            "cambio del pronóstico (%)": 100 * (np.exp(t["actual"] - t["anterior"]) - 1),
                            "observado": lvl["observado"],
                            "error del anterior (%)": 100 * (np.exp(t["anterior"] - t["observado"]) - 1)})
        tab.index = [str(i) for i in tab.index]
        tables.append(f"<h3>{SHORT[var].capitalize()}</h3>" + tab.round(2).to_html(border=0, na_rep="–"))
        seen = tab.dropna(subset=["observado"])
        if len(seen):
            m, r = seen.index[0], seen.iloc[0]
            e = r["error del anterior (%)"]
            sentido = ("acertó casi justo" if abs(e) < 0.3 else
                       f"esperaba {num(abs(e))}% {'más' if e > 0 else 'menos'} de lo que hubo")
            lines.append(f"para {name(var)} de {mes(m)} el reporte anterior esperaba {num(r['pronóstico anterior'])} y "
                         f"salió {num(r['observado'])}: {sentido}")
        common = tab.dropna(subset=["pronóstico anterior", "pronóstico actual"])
        if len(common):
            last = common.iloc[-1]
            c = last["cambio del pronóstico (%)"]
            lines.append(f"para {mes(common.index[-1])} ahora se espera {num(abs(c))}% "
                         f"{'más' if c > 0 else 'menos'} que en el reporte anterior")
    criollo = (". ".join(l[0].upper() + l[1:] for l in lines) + ".") if lines else None
    body = ("Acá ponemos lado a lado lo que decía el reporte anterior y lo que dice este. Sirve para dos cosas: "
            "ver si el pronóstico del mes que ya pasó acertó (columna «error del anterior») y ver cuánto cambió "
            "la idea del modelo con la información nueva (columna «cambio del pronóstico»). Si el pronóstico "
            "salta mucho de un mes al otro sin que haya pasado nada raro, es una señal de que el modelo es "
            "inestable.")
    out.append(explain("¿Cómo se lee esta comparación?", body, criollo))
    out.append(compare_chart(ctx, pctx, cur, prev))
    out += tables

    # Parámetros
    if not pmodel.empty and not model_now.empty:
        cols = [c for c in ["theta", "ec", "a1_co", "a2_act"] if c in model_now and c in pmodel]
        p = pmodel.set_index("variable")[cols].add_suffix(" anterior")
        c = model_now.set_index("variable")[cols].add_suffix(" actual")
        par = p.join(c, how="outer")
        par = par[[f"{x} {w}" for x in cols for w in ("anterior", "actual")]]
        par = par.loc[[v for v in ["m2", "circ", "dav", "m3", "m2priv"] if v in par.index]]
        par.index = [SHORT.get(i, i) for i in par.index]
        body = ("Estos son los números internos del modelo lineal, que se vuelven a calcular solos cada mes con todos "
                "los datos. <em>theta</em> es la velocidad con la que el modelo cree que la plata vuelve a su nivel "
                "«normal» (más negativo = más rápido; cerca de cero = casi no vuelve). <em>ec</em> es la brecha: cuán "
                "lejos está hoy la demanda de ese nivel normal. <em>a1</em> es cuánto baja la demanda cuando sube la "
                "tasa y <em>a2</em>, cuánto sube cuando crece la actividad (debería ser positivo). Si estos números "
                "cambian mucho de un mes a otro, el modelo no es estable.")
        out += [explain("¿Qué cambió adentro del modelo?", body), par.round(3).to_html(border=0, na_rep="–")]

    # Revisión de datos
    po = pctx["od_data"].get("y_m2")
    if po is not None:
        last6 = [m for m in latest.index if m <= pctx["origin"]][-6:]
        rv = pd.DataFrame({"visto antes": np.exp(po.reindex(last6)) / 1000,
                           "visto ahora": np.exp(latest["y_m2"].reindex(last6)) / 1000})
        rv["revisión (%)"] = 100 * (rv["visto ahora"] / rv["visto antes"] - 1)
        rv.index = [str(i) for i in rv.index]
        mx = rv["revisión (%)"].abs().max()
        body = ("Los meses ya pasados también cambian un poco entre reportes: cuando entra un dato nuevo, el ajuste "
                "por estacionalidad (sacar el efecto aguinaldo, vacaciones, etc.) se recalcula y mueve los valores "
                "anteriores. Esta tabla muestra cuánto se movió el M2 transaccional de los últimos 6 meses.")
        criollo = (f"la revisión más grande fue de {pct(mx, 2)}; "
                   + ("es chica, no cambia la historia." if mx < 0.5 else
                      "no es despreciable: parte del cambio en el pronóstico viene de que cambió la foto del pasado."))
        out += [explain("¿Cambiaron los datos pasados?", body, criollo), rv.round(2).to_html(border=0, na_rep="–")]
    return "".join(out)


def compare_chart(ctx: dict, pctx: dict, cur: pd.DataFrame, prev: pd.DataFrame) -> str:
    import base64
    import io

    var = "m2"
    lvl = lambda v: np.exp(v) / 1000
    y = ctx["od_data"][f"y_{var}"].dropna()
    y = y[y.index > ctx["origin"] - 12]
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(y.index.to_timestamp(), lvl(y), color="black", lw=1.8, label="observado (datos de hoy)")
    for g, o, color, lab in [(prev, pctx["origin"], "#888888", "reporte anterior"),
                             (cur, ctx["origin"], "#1f5aa6", "este reporte")]:
        g = g[g["variable"] == var]
        h = g[g["model"] == _head(g)].sort_values("target")
        if h.empty:
            continue
        x = [t.to_timestamp() for t in h["target"]]
        ax.fill_between(x, lvl(h["q0.16"]), lvl(h["q0.84"]), color=color, alpha=0.18)
        ax.plot(x, lvl(h["q0.5"]), color=color, lw=2, marker="o", ms=3, label=f"{lab} (datos hasta {o})")
    ax.set_title("M2 transaccional: pronóstico anterior contra pronóstico actual (miles de millones de $ de dic-2016)",
                 fontsize=9, loc="left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f'<img alt="" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


# --- 3. Textos en criollo para las secciones existentes --------------------------------------

def forecast_criollo(var: str, tab: pd.DataFrame) -> str:
    last = tab.iloc[-1]
    ch = last["var. vs origen (%)"]
    lo, hi = 100 * (last["68% inf."] / last["RW"] - 1), 100 * (last["68% sup."] / last["RW"] - 1)
    verbo = (plural(var, "se mantenga casi igual", "se mantengan casi iguales") if abs(ch) < 0.5 else
             plural(var, "suba", "suban") if ch > 0 else plural(var, "baje", "bajen"))
    s = (f"el modelo espera que {name(var)} {verbo} ({pct(ch)}) de acá a {mes(tab.index[-1])}, en pesos de poder de "
         f"compra constante. El rango probable va de {pct(lo)} a {pct(hi)}")
    if lo < 0 < hi:
        s += ", o sea que no se puede descartar ni una suba ni una baja"
    return s + "."


FORECAST_BODY = ("La línea negra es lo que efectivamente pasó (cuánta plata tiene la gente, sin el efecto de la "
                 "inflación ni de los meses estacionales como diciembre o julio). La línea azul es lo que el modelo "
                 "espera para los próximos 6 meses, y la zona celeste es el rango probable: la más oscura cubre en "
                 "teoría 2 de cada 3 casos y la más clara 19 de cada 20, aunque en la práctica estas bandas son "
                 "demasiado angostas y la realidad se sale más seguido. La línea gris punteada es la regla «igual que "
                 "hoy». Si la azul queda arriba de la gris, el modelo espera que la gente quiera tener más pesos; si "
                 "queda abajo, menos. La franja naranja marca los meses en que la actividad todavía no se publicó y "
                 "la completamos con lo que esperan los analistas (REM).")

GAP_BODY = ("El modelo calcula cuánta plata «debería» querer tener la gente según cuánto se produce y cuánto pagan las "
            "tasas de interés. La brecha es la distancia entre lo que tienen de verdad y ese nivel «normal». Si es "
            "negativa, el modelo piensa que la gente tiene menos plata de la normal y por eso pronostica que va a "
            "subir. Ojo: en 2025-2026 la brecha estuvo muy negativa durante mucho tiempo y la plata nunca volvió; por "
            "eso desconfiamos de ese tirón y publicamos siempre la regla «igual que hoy» al lado. La alarma salta si "
            "el nivel «normal» se recalcula mucho de un mes al otro.")


def gap_criollo(al: pd.DataFrame) -> str:
    parts = []
    for _, r in al[al["variable"].isin(["m2", "circ", "dav"])].iterrows():
        e = r["brecha ec (%)"]
        v = r["variable"]
        parts.append(f"{name(v)} {plural(v, 'está', 'están')} {num(abs(e), 0)}% "
                     f"{'por debajo' if e < 0 else 'por encima'} de lo que el modelo considera normal")
    s = "; ".join(parts)
    return (s[0].upper() + s[1:] + ". " if s else "") + (
        "Ninguna alarma: el nivel «normal» no se movió de más este mes." if not al["alarma"].any()
        else "Hay alarma: el nivel «normal» se recalculó mucho, no confíes en los modelos con equilibrio este mes.")


ERRORS_BODY = ("Esta tabla responde «¿el modelo sirve?». Para cada modelo calculamos cuánto se equivocó en promedio y "
               "lo dividimos por lo que se equivoca la regla «igual que hoy» (RW). Un 1 es empate; menos de 1, el "
               "modelo erra menos (por ejemplo 0,7 = erra 30% menos); más de 1, erra más. h1, h3 y h6 son pronósticos "
               "a 1, 3 y 6 meses. «Todo el archivo» incluye las pruebas hacia atrás (2021-2025); «Últimos 12 meses» "
               "muestra cómo viene funcionando ahora, que es lo que más importa. El gráfico muestra el error de cada "
               "mes a 3 meses: arriba de cero, el modelo esperaba más plata de la que hubo.")

BCRA_BODY = ("Acá comparamos con el último programa monetario del BCRA, medido como porcentaje del PIB (que es como lo "
             "publica el BCRA). La línea azul es lo que esperaba el BCRA y la zona celeste su rango; los cuadrados "
             "naranjas, lo que el BCRA mostró como observado; la línea negra, lo que da con nuestros datos. No mires "
             "los niveles (cada uno usa su propia corrección estacional y su PIB), mirá los cambios: si el BCRA "
             "esperaba que subiera y bajó, su base falló.")

AGG_BODY = ("La plata que la gente usa para pagar puede estar en distintos lugares: efectivo, cuentas sin interés, "
            "cuentas que pagan interés, plazos fijos o fondos de las billeteras virtuales. El M2 transaccional (el que "
            "mira el BCRA) solo cuenta los primeros dos. Si los demás crecen mientras el M2 transaccional cae, puede "
            "ser que la gente no quiera menos pesos sino que los guarde en otro lado.")

FRESH_BODY = ("Cada dato llega con cierta demora (la actividad, por ejemplo, unos 50 días). Esta tabla muestra el "
              "último dato disponible de cada fuente y si está dentro de la demora normal. Si alguna se atrasa de más, "
              "la corrida se frena y te llega un aviso en lugar de un reporte con datos viejos.")
