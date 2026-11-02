"""Fase 1: evaluación de los pronósticos publicados por el BCRA (data/bcra_forecasts.csv).

python -m src.evaluate.published

Todo en % del PIB s.e., cada fila contra el observado de su propia vintage (no se mezclan vintages).
Métricas por fila: error, z-score, cobertura 68/95, acierto direccional y error de la caminata aleatoria
(pronóstico = valor del origen en esa misma vintage). La incertidumbre de lectura a ojo (±0,02 pp) se
propaga por Monte Carlo con lecturas uniformes independientes.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.ingest.common import ROOT

Z95 = 1.959964
READ_ERROR = {"eyeball": 0.02, "webplotdigitizer": 0.005}
N_MC = 20000
SEED = 20261030


def load() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "bcra_forecasts.csv")
    for c in ["origin_month", "target_month"]:
        df[c] = pd.PeriodIndex(df[c], freq="M")
    df["h"] = [(t - o).n for t, o in zip(df["target_month"], df["origin_month"])]
    return df


def sigma_from_bands(row: pd.Series) -> float:
    """Desvío implícito: semiancho de la banda del 68%; si falta, banda del 95% / 1,96."""
    if pd.notna(row["lo68"]) and pd.notna(row["hi68"]):
        return (row["hi68"] - row["lo68"]) / 2
    if pd.notna(row["lo95"]) and pd.notna(row["hi95"]):
        return (row["hi95"] - row["lo95"]) / (2 * Z95)
    return np.nan


def direction(change: float, tol: float = 1e-9) -> int:
    return 0 if abs(change) <= tol else int(np.sign(change))


def evaluate_row(row: pd.Series) -> dict:
    obs, p50, o = row["observed_same_vintage"], row["p50"], row["origin_value"]
    sigma = sigma_from_bands(row)
    err, err_rw = obs - p50, obs - o
    d_fc, d_obs = direction(p50 - o), direction(obs - o)
    return {
        "error": err,
        "error_rw": err_rw,
        "abs_ratio_vs_rw": abs(err) / abs(err_rw) if err_rw != 0 else np.inf,
        "sigma_implied": sigma,
        "z": err / sigma if sigma > 0 else np.nan,
        "in68": (row["lo68"] <= obs <= row["hi68"]) if pd.notna(row["lo68"]) else None,
        "in95": (row["lo95"] <= obs <= row["hi95"]) if pd.notna(row["lo95"]) else None,
        "dir_forecast": d_fc,
        "dir_observed": d_obs,
        "dir_hit": (d_fc == d_obs) if d_obs != 0 else None,
        "opposite": d_fc * d_obs == -1,
    }


def read_uncertainty(row: pd.Series, rng: np.random.Generator) -> dict:
    """Probabilidades bajo error de lectura uniforme ±r en cada valor leído del gráfico."""
    r = READ_ERROR.get(row["read_method"], 0.02)
    u = lambda: rng.uniform(-r, r, N_MC)
    obs, p50, o = row["observed_same_vintage"] + u(), row["p50"] + u(), row["origin_value"] + u()
    out = {"p_rw_better": float(np.mean(np.abs(obs - o) < np.abs(obs - p50))),
           "p_opposite": float(np.mean(np.sign(p50 - o) * np.sign(obs - o) < 0))}
    if pd.notna(row["lo95"]):
        lo, hi = row["lo95"] + u(), row["hi95"] + u()
        out["p_outside95"] = float(np.mean((obs < lo) | (obs > hi)))
    if pd.notna(row["lo68"]):
        lo, hi = row["lo68"] + u(), row["hi68"] + u()
        out["p_outside68"] = float(np.mean((obs < lo) | (obs > hi)))
    return out


def evaluate(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = [{**evaluate_row(r), **read_uncertainty(r, rng)} for _, r in df.iterrows()]
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def by_vintage(ev: pd.DataFrame) -> pd.DataFrame:
    def agg(g: pd.DataFrame) -> pd.Series:
        last = g.loc[g["h"].idxmax()]
        return pd.Series({
            "origin": str(g["origin_month"].iloc[0]),
            "n": len(g),
            "h_max": int(last["h"]),
            "mae": g["error"].abs().mean(),
            "mae_rw": g["error_rw"].abs().mean(),
            "rmse_rel_rw": np.sqrt((g["error"] ** 2).mean() / (g["error_rw"] ** 2).mean())
            if (g["error_rw"] ** 2).mean() > 0 else np.inf,
            "error_hmax": last["error"],
            "error_rw_hmax": last["error_rw"],
            "z_hmax": last["z"],
            "opposite_hmax": bool(last["opposite"]),
            "p_rw_better_hmax": last["p_rw_better"],
        })
    return ev.groupby("vintage_label", sort=False)[list(ev.columns)].apply(agg)


def sign_test_rw(summary: pd.DataFrame) -> float:
    """P(caminata aleatoria mejor en k o más de n vintages | 50%), al horizonte máximo de cada vintage."""
    from scipy.stats import binomtest
    k = int((summary["error_rw_hmax"].abs() < summary["error_hmax"].abs()).sum())
    return binomtest(k, len(summary), 0.5, alternative="greater").pvalue


def plot(ev: pd.DataFrame, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    vintages = list(dict.fromkeys(ev["vintage_label"]))
    fig, axes = plt.subplots(1, len(vintages), figsize=(4.2 * len(vintages), 3.8), sharey=True)
    for ax, v in zip(np.atleast_1d(axes), vintages):
        g = ev[ev["vintage_label"] == v].sort_values("h")
        o, x0 = g["origin_value"].iloc[0], 0
        hs = g["h"].to_numpy()
        ax.axhline(o, color="#888", lw=1, ls=":", label="caminata aleatoria")
        ax.plot(np.r_[x0, hs], np.r_[o, g["p50"]], color="#1f5aa6", lw=1.6, ls="--", marker="o", ms=4,
                label="BCRA p50")
        has95, has68 = g["lo95"].notna(), g["lo68"].notna()
        ax.vlines(hs[has95], g["lo95"][has95], g["hi95"][has95], color="#1f5aa6", alpha=0.25, lw=9, label="95%")
        ax.vlines(hs[has68], g["lo68"][has68], g["hi68"][has68], color="#1f5aa6", alpha=0.45, lw=9, label="68%")
        ax.plot(np.r_[x0, hs], np.r_[o, g["observed_same_vintage"]], color="#c0504d", lw=1.4, marker="s", ms=5,
                label="observado (misma vintage)")
        ax.set_xticks(np.r_[x0, hs])
        ax.set_xticklabels([str(g["origin_month"].iloc[0])] + [str(t) for t in g["target_month"]],
                           rotation=45, fontsize=7)
        ax.set_title(f"{v} ({g['chart'].iloc[0]})", fontsize=9, loc="left")
        ax.grid(alpha=0.25)
        ax.tick_params(axis="y", labelsize=8)
    np.atleast_1d(axes)[0].set_ylabel("M2 privado transaccional, % PIB s.e.", fontsize=8)
    np.atleast_1d(axes)[0].legend(fontsize=7, loc="upper left")
    fig.text(0.01, 0.01, "Valores leídos a ojo de gráficos publicados (±0,02 pp). Meses intermedios faltantes "
             "no se interpolan.", fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _fmt(x, nd=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    if isinstance(x, (bool, np.bool_)):
        return "sí" if x else "no"
    if isinstance(x, (int, np.integer)):
        return str(x)
    return f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def write_report(ev: pd.DataFrame, summary: pd.DataFrame, p_sign: float, path) -> None:
    dir_lbl = {1: "↑", -1: "↓", 0: "="}
    lines = ["# Fase 1: pronósticos publicados del BCRA", "",
             "M2 privado transaccional, % del PIB s.e. Cada fila se compara con el observado de su propia vintage.",
             "Caminata aleatoria (CA) = valor del origen en esa vintage. σ implícito = semiancho de la banda del 68%.",
             "Las columnas P(·) incorporan error de lectura uniforme de ±0,02 pp en cada valor leído.", "",
             "## Por pronóstico", "",
             "| vintage | origen | destino | h | p50 | obs | error | error CA | z | en 68% | en 95% "
             "| dir. BCRA / obs | P(CA mejor) | P(fuera 95%) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in ev.iterrows():
        lines.append(
            f"| {r.vintage_label} | {r.origin_month} | {r.target_month} | {r.h} | {r.p50:.3f} "
            f"| {r.observed_same_vintage:.3f} | {_fmt(r.error)} | {_fmt(r.error_rw)} | {_fmt(r.z, 2)} "
            f"| {_fmt(r.in68)} | {_fmt(r.in95)} | {dir_lbl[r.dir_forecast]} / {dir_lbl[r.dir_observed]} "
            f"| {r.p_rw_better:.2f} | {f'{r.p_outside95:.2f}' if pd.notna(r.get('p_outside95')) else '–'} |")
    lines += ["", "## Por vintage", "",
              "| vintage | origen | N | h máx | MAE | MAE CA | RMSE rel. CA | error h máx | error CA h máx "
              "| z h máx | dirección opuesta h máx | P(CA mejor) h máx |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v, s in summary.iterrows():
        lines.append(f"| {v} | {s.origin} | {s.n} | {s.h_max} | {s.mae:.3f} | {s.mae_rw:.3f} | {s.rmse_rel_rw:.2f} "
                     f"| {_fmt(s.error_hmax)} | {_fmt(s.error_rw_hmax)} | {_fmt(s.z_hmax, 2)} "
                     f"| {_fmt(s.opposite_hmax)} | {s.p_rw_better_hmax:.2f} |")
    n_opp = int(summary["opposite_hmax"].sum())
    n_rw = int((summary["error_rw_hmax"].abs() < summary["error_hmax"].abs()).sum())
    in68 = ev["in68"].dropna().astype(bool)
    in95 = ev["in95"].dropna().astype(bool)
    lines += ["", "## Lectura", "",
              f"- En el horizonte máximo, la CA tuvo menor error absoluto en {n_rw} de {len(summary)} vintages. "
              f"Test de signo unilateral (H0: 50%): p = {p_sign:.3f}. Con N = {len(summary)} vintages "
              f"independientes, el test no puede rechazar al 5% aunque la CA gane en todos.",
              f"- Dirección opuesta a la base en el horizonte máximo: {n_opp} de {len(summary)} vintages.",
              f"- Cobertura observada: 68% → {in68.sum()}/{len(in68)}; 95% → {in95.sum()}/{len(in95)}. "
              "Las filas de una misma vintage no son independientes.",
              f"- Sesgo: el error medio es {ev['error'].mean():+.3f} pp, con {int((ev['error'] > 0).sum())} filas "
              f"de {len(ev)} con error positivo.", ""]
    rev = revisions(ev)
    if not rev.empty:
        lines += ["## Revisiones entre vintages (mismo mes, distinto gráfico)", "",
                  "| mes | vintage A | valor A | vintage B | valor B | B − A |", "|---|---|---|---|---|---|"]
        for _, r in rev.iterrows():
            lines.append(f"| {r.month} | {r.vintage_a} | {r.value_a:.3f} | {r.vintage_b} | {r.value_b:.3f} "
                         f"| {r.revision:+.3f} |")
        lines += ["", "Una revisión de este tamaño se compara directamente con los errores de pronóstico de arriba.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def revisions(ev: pd.DataFrame) -> pd.DataFrame:
    """Meses que aparecen en más de una vintage, como origen u observado."""
    obs = pd.concat([
        ev[["vintage_label", "origin_month", "origin_value"]].set_axis(["vintage", "month", "value"], axis=1),
        ev[["vintage_label", "target_month", "observed_same_vintage"]].set_axis(["vintage", "month", "value"], axis=1),
    ]).drop_duplicates(["vintage", "month"])
    order = {v: i for i, v in enumerate(dict.fromkeys(ev["vintage_label"]))}
    out = []
    for month, g in obs.groupby("month"):
        g = g.sort_values("vintage", key=lambda s: s.map(order))
        for (_, a), (_, b) in zip(g.iloc[:-1].iterrows(), g.iloc[1:].iterrows()):
            out.append({"month": month, "vintage_a": a.vintage, "value_a": a.value,
                        "vintage_b": b.vintage, "value_b": b.value, "revision": b.value - a.value})
    return pd.DataFrame(out)


def main() -> int:
    out = ROOT / "reports" / "fase1"
    out.mkdir(parents=True, exist_ok=True)
    ev = evaluate(load())
    summary = by_vintage(ev)
    p = sign_test_rw(summary)
    ev.to_csv(out / "evaluacion_por_pronostico.csv", index=False)
    summary.to_csv(out / "evaluacion_por_vintage.csv")
    plot(ev, out / "observado_vs_bandas.png")
    write_report(ev, summary, p, out / "fase1.md")
    print((out / "fase1.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
