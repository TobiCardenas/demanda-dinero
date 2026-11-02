"""Fase 4: pronósticos con origen móvil (pseudo tiempo real). python -m src.evaluate.oos [--workers N]

Para cada origen mensual y cada variable dependiente estima todos los modelos con datos <= origen
(X13 truncado) y pronostica h=1..6 con escenario ex ante REM y con escenario realizado. Archiva una fila
por (vintage, origen, modelo, variable, mes, escenario) con cuantiles en log de saldos reales s.e. y en
% del PIB, en un archivo nuevo de data/forecasts/ (los archivos existentes nunca se modifican).
Protocolo fijado en DECISIONS.md (Fase 4).
"""

from __future__ import annotations

import datetime as dt
import os

# Un hilo de BLAS por proceso: con varios procesos, el multihilo de numpy compite por los mismos núcleos.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import pickle
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from src.ingest.common import ROOT, latest_snapshot, load_yaml
from src.models.base import QUANTILES
from src.models.benchmarks import AutoARIMA, RandomWalk, RandomWalkDrift
from src.models.ecm_logistic import LogisticECM
from src.models.robust import DiffECM, TVPModel, intercept_corrected
from src.models.vecm import VECMModel
from src.transform import model_data as md
from src.transform.ratios import monthly_nominal_gdp_sa

H = 6
N_SIMS = 200
LAST_ORIGIN = pd.Period("2026-08", "M")
LAST_REALIZED = pd.Period("2026-08", "M")  # último EMAE publicado
VARIABLES = {
    # variable: (primer origen, muestra larga, ¿admite muestra móvil distinta?)
    "circ": ("2021-02", {"start": "2017-02"}, True),
    "m2priv": ("2021-02", {"start": "2017-02"}, True),
    "m3": ("2021-02", {"start": "2017-02"}, True),
    "dav": ("2025-01", {"start": "2021-02"}, False),
    "m2": ("2025-01", {"start": "2021-02"}, False),
    "m2amp": ("2025-08", {"start": "2023-09"}, False),
}
ROLLING = {"window": 60}
DETS = {"minimal": [], "exp_dep": ["dep_exp"], "alt_linear": ["alt"]}


def model_specs(var: str, seed: int, grid: dict) -> list[tuple[str, str, callable]]:
    """(nombre, grupo de ensamble, fábrica)."""
    _, long_s, has_roll = VARIABLES[var]
    bench = [("RW", "bench", lambda: RandomWalk(var, seed)),
             ("RW_drift", "bench", lambda: RandomWalkDrift(var, seed)),
             ("ARIMA", "bench", lambda: AutoARIMA(var, seed))]
    if var == "m2amp":
        return bench + [("DIFF", "robust", lambda: DiffECM(var, [], long_s, seed=seed))]
    samples = {"long": long_s, **({"roll60": ROLLING} if has_roll else {})}
    out = []
    for sname, s in samples.items():
        for dname, dets in DETS.items():
            out.append((f"F1|{dname}|{sname}", "F1", lambda s=s, dets=dets: VECMModel(var, dets, s, seed=seed)))
            if dname != "alt_linear":
                out.append((f"F2|{dname}|{sname}", "F2",
                            lambda s=s, dets=dets: LogisticECM(var, dets, s, seed=seed, grid=grid)))
    out += [("IC1_F1", "robust", lambda: intercept_corrected(VECMModel, 1, var, [], long_s, seed=seed)),
            ("IC3_F1", "robust", lambda: intercept_corrected(VECMModel, 3, var, [], long_s, seed=seed)),
            ("DIFF", "robust", lambda: DiffECM(var, [], long_s, seed=seed)),
            ("TVP", "robust", lambda: TVPModel(var, long_s, seed=seed))]
    return out + bench


def _pct(q: pd.Series, log_p: pd.Series, gdp_m: pd.Series) -> pd.Series:
    return np.exp(q) * np.exp(log_p.reindex(q.index)) / 100 / gdp_m.reindex(q.index) * 100


def run_origin(origin_str: str, seed: int, grid: dict, opts: dict | None = None,
               last_realized: pd.Period = LAST_REALIZED, context: dict | None = None
               ) -> tuple[list[dict], list[dict], list[dict]]:
    """opts: opciones de model_data.build (p. ej. realtime_fill en la Fase 5).
    context: si se pasa un dict, se completa con od, escenarios, PIB y trayectorias de brecha (para el reporte)."""
    origin = pd.Period(origin_str, "M")
    panel, rem = md.load_panel(), md.load_rem()
    od = md.build(origin, panel, rem, opts)
    scen = {}
    sc_rem, _ = md.scenario_rem(od, H, panel, rem)
    scen["exante_rem"] = sc_rem
    h_re = min(H, (last_realized - origin).n)
    if h_re > 0:
        scen["realized"] = md.scenario_realized(od, h_re, panel, rem)
    gdp = {}
    for k, sc in scen.items():
        log_p = pd.concat([od.data["log_p"], sc["log_p"]])
        gdp[k] = (log_p, monthly_nominal_gdp_sa(pd.concat([od.data["act"], sc["act"]]), log_p, origin))

    if context is not None:
        context.update({"od": od, "scen": scen, "gdp": gdp, "ec": {}, "ylp": {}})
    rows, fails, stab = [], [], []
    for var, (first, _, _) in VARIABLES.items():
        if origin < pd.Period(first, "M") or f"y_{var}" not in od.data or pd.isna(od.data[f"y_{var}"].get(origin)):
            continue
        for name, group, factory in model_specs(var, seed, grid):
            try:
                m = factory().fit(od.data, origin)
                if name == "F1|minimal|long":
                    ylp = pd.Series(m.long_run(m.d, m.params.lr), index=m.d.index)
                    stab.append({"origin": origin, "variable": var, "theta": m.params.theta,
                                 "y_lp_origin": ylp.iloc[-1], "y_lp_prev": ylp.iloc[-2], "ec": m.ec_path().iloc[-1]})
                    if context is not None:
                        context["ec"][var], context["ylp"][var] = m.ec_path(), ylp
                for sname, sc in scen.items():
                    h = len(sc)
                    fc = m.forecast(sc, h, N_SIMS, reestimate=False)
                    log_p, gdp_m = gdp[sname]
                    for tm, r in fc.iterrows():
                        row = {"origin": origin, "model": name, "group": group, "variable": var, "target": tm,
                               "h": (tm - origin).n, "scenario": sname, "point": r["point"]}
                        for q in QUANTILES:
                            row[f"q{q}"] = r[f"q{q}"]
                        rows.append(row)
                    pct = {f"pct_q{q}": _pct(fc[f"q{q}"], log_p, gdp_m) for q in QUANTILES}
                    pct["pct_point"] = _pct(fc["point"], log_p, gdp_m)
                    n = len(fc)
                    for j, tm in enumerate(fc.index):
                        rows[-n + j].update({k: float(v[tm]) for k, v in pct.items()})
            except Exception as exc:
                fails.append({"origin": origin, "variable": var, "model": name, "error": repr(exc)[:300],
                              "trace": traceback.format_exc()[-600:]})
    return rows, fails, stab


def _run_and_save(origin_str: str, seed: int, grid: dict, parts_dir: str) -> tuple[str, int, int]:
    res = run_origin(origin_str, seed, grid)
    tmp = os.path.join(parts_dir, f"{origin_str}.pkl.tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(res, fh)
    os.replace(tmp, os.path.join(parts_dir, f"{origin_str}.pkl"))
    return origin_str, len(res[0]), len(res[1])


def main(argv: list[str]) -> int:
    """--workers N; --resume <directorio de partes> para retomar una corrida cortada."""
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else max(1, (os.cpu_count() or 2) - 1)
    cfg = load_yaml("settings.yaml")
    seed, grid = cfg["forecast"]["seed"], cfg["replication"]["logistic_grid"]
    vintage = latest_snapshot().date.isoformat()
    first = min(pd.Period(v[0], "M") for v in VARIABLES.values())
    origins = [str(o) for o in pd.period_range(first, LAST_ORIGIN, freq="M")]
    out_dir = ROOT / "data" / "forecasts"
    out_dir.mkdir(parents=True, exist_ok=True)
    if "--resume" in argv:
        parts_dir = argv[argv.index("--resume") + 1]
        stamp = os.path.basename(os.path.normpath(parts_dir)).removeprefix("_parts_")
    else:
        stamp = dt.datetime.now().strftime("%Y%m%dT%H%M")
        parts_dir = str(ROOT / "data" / "processed" / f"_parts_{stamp}")  # checkpoints regenerables
    os.makedirs(parts_dir, exist_ok=True)
    path = out_dir / f"pseudo_oos_{vintage}_{stamp}.csv"
    done = {f.removesuffix(".pkl") for f in os.listdir(parts_dir) if f.endswith(".pkl")}
    todo = [o for o in origins if o not in done]
    print(f"Partes en {parts_dir}: {len(done)} hechas, {len(todo)} pendientes", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_run_and_save, o, seed, grid, parts_dir) for o in todo]
        for k, f in enumerate(as_completed(futs), 1):
            o, nr, nf = f.result()
            print(f"  [{k}/{len(todo)}] origen {o}: {nr} filas, {nf} fallas ({time.time() - t0:.0f}s)", flush=True)
    rows, fails, stab = [], [], []
    for o in origins:
        with open(os.path.join(parts_dir, f"{o}.pkl"), "rb") as fh:
            r, fl, st = pickle.load(fh)
        rows += r
        fails += fl
        stab += st
    df = pd.DataFrame(rows)
    df.insert(0, "vintage", vintage)
    df.insert(1, "realtime", "pseudo")
    df = df.sort_values(["variable", "model", "scenario", "origin", "target"])
    with open(path, "x", encoding="utf-8", newline="") as fh:  # archivo nuevo: nunca se pisa uno existente
        df.to_csv(fh, index=False)
    pd.DataFrame(fails).to_csv(out_dir / f"pseudo_oos_{vintage}_{stamp}_fallas.csv", index=False)
    pd.DataFrame(stab).to_csv(out_dir / f"pseudo_oos_{vintage}_{stamp}_estabilidad.csv", index=False)
    print(f"{len(df)} filas -> {path}; {len(fails)} fallas; {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
