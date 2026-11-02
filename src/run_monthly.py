"""Corrida mensual: python -m src.run_monthly

ingesta -> snapshot -> transformaciones y validación -> frescura -> estimación en el origen de tiempo
real -> pronósticos (ex ante REM y realizado) -> ensambles -> archivo -> evaluación de todo el archivo
-> reporte HTML en reports/<YYYY-MM>.html.

Cualquier falla de fuente, de validación o de frescura termina la corrida con código 1 y mensaje
explícito: nunca se siguen usando datos viejos sin avisar. Decisiones en DECISIONS.md (Fase 5).
"""

from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import pickle
import sys
import time

import numpy as np
import pandas as pd

from src.ensemble.combine import combine
from src.evaluate import oos, vintages
from src.evaluate.coverage import density_metrics
from src.evaluate.errors import attach_observed, point_metrics
from src.ingest import run as ingest_run
from src.ingest.common import ROOT, latest_snapshot, load_yaml
from src.models.base import QUANTILES
from src.transform import freshness, model_data as md, panel as panel_mod, validate
from src.transform.ratios import load_gdp

FC_DIR = ROOT / "data" / "forecasts"
DEV_END = pd.Period("2025-10", "M")


class RunError(RuntimeError):
    pass


def step(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_archive() -> pd.DataFrame:
    parts = []
    for f in sorted(FC_DIR.glob("*.csv")):
        if f.stem.endswith(("_fallas", "_estabilidad", "_pesos")):
            continue
        d = pd.read_csv(f)
        d["source_file"] = f.name
        parts.append(d)
    fc = pd.concat(parts, ignore_index=True)
    for c in ["origin", "target"]:
        fc[c] = pd.PeriodIndex(fc[c], freq="M")
    return fc


def load_stability() -> pd.DataFrame:
    parts = []
    for f in sorted(FC_DIR.glob("*_estabilidad.csv")):
        d = pd.read_csv(f)
        d["realtime"] = f.name.startswith("realtime")
        parts.append(d)
    s = pd.concat(parts, ignore_index=True)
    s["origin"] = pd.PeriodIndex(s["origin"], freq="M")
    return s


def alarms(stab_all: pd.DataFrame, current: pd.DataFrame, multiple: float) -> pd.DataFrame:
    """Revisión del equilibrio del mes anterior respecto de la corrida previa, contra la media de desarrollo."""
    dev = stab_all[(~stab_all["realtime"]) & (stab_all["origin"] <= DEV_END)]
    rows = []
    for _, r in current.iterrows():
        var, o = r["variable"], r["origin"]
        d = dev[dev["variable"] == var].sort_values("origin").set_index("origin")
        rev_dev = (d["y_lp_prev"] - d["y_lp_origin"].shift(1)).abs()
        rev_dev = rev_dev[pd.Series(d.index, index=d.index).diff().apply(lambda x: getattr(x, "n", 0)) == 1]
        prev = stab_all[(stab_all["variable"] == var) & (stab_all["origin"] == o - 1)]
        prev_val = prev.sort_values("realtime")["y_lp_origin"].iloc[-1] if len(prev) else np.nan
        revision = abs(r["y_lp_prev"] - prev_val) if pd.notna(prev_val) else np.nan
        thr = multiple * rev_dev.mean() if len(rev_dev) else np.nan
        flag = (pd.notna(revision) and pd.notna(thr) and revision > thr) or r["theta"] >= 0
        rows.append({"variable": var, "brecha ec (%)": 100 * r["ec"], "theta": r["theta"],
                     "revisión del equilibrio (%)": 100 * revision if pd.notna(revision) else np.nan,
                     "umbral (%)": 100 * thr if pd.notna(thr) else np.nan, "alarma": bool(flag)})
    return pd.DataFrame(rows)


def main(argv: list[str]) -> int:
    t0 = time.time()
    cfg = load_yaml("settings.yaml")
    seed, grid = cfg["forecast"]["seed"], cfg["replication"]["logistic_grid"]

    step("1/7 Ingesta y snapshot")
    if ingest_run.main([]) != 0:
        raise RunError("La ingesta falló (ver arriba). No se continúa con datos viejos.")
    snap = latest_snapshot()

    step("2/7 Panel y validación")
    panel_mod.main([snap.date.isoformat()])
    rep = validate.run(snap)
    if rep.errors:
        raise RunError("Validación con errores:\n  " + "\n  ".join(rep.errors))
    panel, rem, gdp = md.load_panel(), md.load_rem(), load_gdp()

    step("3/7 Frescura de fuentes")
    errs, fresh = freshness.check(panel, gdp, rem, snap.date)
    print(fresh.to_string(index=False))
    if errs:
        raise RunError("Fuentes atrasadas más de lo admitido:\n  " + "\n  ".join(errs))

    origin = min(panel["m2_trans_priv"].dropna().index.max(), panel["ipc_headline"].dropna().index.max())
    last_emae = panel["emae_orig"].dropna().index.max()
    out_csv = FC_DIR / f"realtime_{snap.date.isoformat()}.csv"
    if out_csv.exists():
        raise RunError(f"Ya existe {out_csv.name}: el archivo de pronósticos no se reescribe. "
                       "Para regenerar solo el reporte: python -m src.report.build_report")

    step(f"4/7 Estimación y pronósticos en el origen {origin} (EMAE hasta {last_emae})")
    ctx: dict = {}
    rows, fails, stab = oos.run_origin(str(origin), seed, grid, opts={"realtime_fill": True},
                                       last_realized=last_emae, context=ctx)
    od = ctx["od"]
    if fails:
        print(f"  {len(fails)} modelos fallaron: " + "; ".join(f"{f['variable']}/{f['model']}" for f in fails))
    fc_now = pd.DataFrame(rows)
    fc_now.insert(0, "vintage", snap.date.isoformat())
    fc_now.insert(1, "realtime", "true")
    filled = [str(m) for m in od.data.index[od.data.get("act_filled", pd.Series(False, index=od.data.index)).astype(bool)]]
    fc_now["act_filled_months"] = ",".join(filled)

    step("5/7 Ensambles")
    vfile = ROOT / "data" / "processed" / "pseudo_vintages.csv"
    vint = vintages.load() if vfile.exists() else vintages.build()
    cur = od.data.reindex(columns=vintages.VARS).copy()
    cur.insert(0, "origin", origin)
    cur = cur.rename_axis("period").reset_index()
    vint = pd.concat([vint[vint["origin"] != origin], cur], ignore_index=True)
    vint.to_csv(vfile, index=False)  # regenerable: se agrega la vintage de este origen
    archive = load_archive()
    ens_rows, wlogs = [], []
    for (var, sc), g in fc_now.groupby(["variable", "scenario"]):
        hist = archive[(archive["variable"] == var) & (archive["scenario"] == sc) & (archive["origin"] < origin)
                       & (~archive["model"].str.startswith("ENS_"))]
        both = pd.concat([hist, g], ignore_index=True)
        models = g["model"].unique()
        groups = {"F1": [m for m in models if m.startswith("F1|")], "F2": [m for m in models if m.startswith("F2|")],
                  "all": list(models)}
        e, w = combine(both, vint, {k: v for k, v in groups.items() if v}, only_origins=[origin])
        ens_rows.append(e)
        wlogs.append(w)
    ens = pd.concat(ens_rows, ignore_index=True)
    if not ens.empty:
        for sc, (log_p, gdp_m) in ctx["gdp"].items():
            m = ens["scenario"] == sc
            for c in [f"q{q}" for q in QUANTILES] + ["point"]:
                pc = "pct_point" if c == "point" else f"pct_{c}"
                ens.loc[m, pc] = (np.exp(ens.loc[m, c]) * np.exp(ens.loc[m, "target"].map(log_p))
                                  / 100 / ens.loc[m, "target"].map(gdp_m) * 100)
        ens.insert(0, "vintage", snap.date.isoformat())
        ens.insert(1, "realtime", "true")
        ens["act_filled_months"] = ",".join(filled)
    out = pd.concat([fc_now, ens], ignore_index=True)

    step("6/7 Archivo")
    with open(out_csv, "x", encoding="utf-8", newline="") as fh:
        out.to_csv(fh, index=False)
    pd.DataFrame(stab).to_csv(FC_DIR / f"realtime_{snap.date.isoformat()}_estabilidad.csv", index=False)
    pd.concat(wlogs).to_csv(FC_DIR / f"realtime_{snap.date.isoformat()}_pesos.csv", index=False)
    pd.DataFrame(fails).to_csv(FC_DIR / f"realtime_{snap.date.isoformat()}_fallas.csv", index=False)
    print(f"  {len(out)} filas -> {out_csv.name}")

    step("7/7 Evaluación del archivo y reporte")
    stab_all = load_stability()
    alarm = alarms(stab_all, pd.DataFrame(stab), cfg["monthly"]["alarm_revision_multiple"])
    context = {"snapshot": snap.date.isoformat(), "origin": origin, "last_emae": last_emae, "filled": filled,
               "freshness": fresh, "validation_warnings": rep.warnings, "alarms": alarm,
               "ec": ctx["ec"], "gdp": ctx["gdp"], "od_data": od.data, "fails": fails,
               "seasonal_method": __import__("src.transform.seasonal", fromlist=["method"]).method()}
    ctx_path = ROOT / "data" / "processed" / f"monthly_context_{snap.date.isoformat()}.pkl"
    with open(ctx_path, "wb") as fh:
        pickle.dump(context, fh)
    from src.report import build_report

    path = build_report.build(snap.date.isoformat())
    print(f"Reporte: {path} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RunError as exc:
        print(f"\nCORRIDA MENSUAL FALLIDA: {exc}", file=sys.stderr)
        sys.exit(1)
