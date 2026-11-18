import numpy as np
import pandas as pd

from src.report import sections as S


def _ctx_and_arch(head_bias: float):
    """Pronósticos a h=1..3 con origen en cada mes; RW pronostica el nivel del origen, el modelo le suma un sesgo."""
    idx = pd.period_range("2025-01", "2026-10", freq="M")
    rng = np.random.default_rng(0)
    y = pd.Series(np.cumsum(rng.normal(0, 0.01, len(idx))) + 13, index=idx)
    od = pd.DataFrame({f"y_{v}": y for v in ["m2", "circ", "dav"]})
    rows = []
    for o in idx[:-1]:
        for h in (1, 2, 3):
            t = o + h
            if t > idx[-1]:
                continue
            for var in ["m2", "circ", "dav"]:
                for model, pt in [("RW", y[o]), ("ENS_F1_avg", y[o] + head_bias)]:
                    rows.append({"origin": o, "target": t, "h": h, "variable": var, "model": model,
                                 "scenario": "exante_rem", "point": pt, "realtime": "pseudo", "source_file": "x.csv"})
    return {"origin": idx[-1], "od_data": od}, pd.DataFrame(rows)


def test_performance_green_red():
    ctx, arch = _ctx_and_arch(0.0)
    assert set(S.performance(arch, ctx)["ratio"].round(6)) == {1.0}  # idéntico a RW -> empate (amarillo)
    ctx, arch = _ctx_and_arch(0.05)  # sesgo grande -> peor que RW
    perf = S.performance(arch, ctx)
    assert (perf["estado"] == "rojo").all() and (perf["ratio"] > 1.1).all()


def test_spanish_agreement():
    assert S.name("dav").startswith("los ") and S.plural("dav", "sube", "suben") == "suben"
    assert S.name("m2").startswith("el ") and S.plural("m2", "sube", "suben") == "sube"
    assert S.mes("2026-10") == "oct-26"


def test_comparison_without_previous_run(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "RUNS_DIR", tmp_path)
    html = S.comparison({"snapshot": "2026-11-18", "origin": pd.Period("2026-10", "M"), "od_data": pd.DataFrame()},
                        pd.DataFrame(), pd.DataFrame())
    assert "primera corrida" in html


def test_headline_choice_rule():
    from src.evaluate.headline import choose
    s = pd.DataFrame({"criterio (prom. variables y h)": [1.03, 1.00, 0.984], "peor variable": [1.3, 1.0, 1.14]},
                     index=["R0", "R1", "R4"])
    assert choose(s) == "R1"  # R1 empata (dentro de 0,02 del mínimo) y tiene menor peor caso
    s.loc["R4", "criterio (prom. variables y h)"] = 0.90
    assert choose(s) == "R4"  # ganador claro
