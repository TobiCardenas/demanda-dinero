import numpy as np
import pandas as pd
import pytest

from src.ensemble.combine import combine, optimal_weights
from src.evaluate.coverage import crps_normal
from src.evaluate.tests_dm import dm_hln


def test_optimal_weights_pick_the_true_forecast():
    rng = np.random.default_rng(0)
    y = rng.normal(size=200)
    F = np.column_stack([y + rng.normal(0, 0.01, 200), rng.normal(size=200), y + rng.normal(0, 1, 200)])
    w = optimal_weights(F, y)
    assert w.sum() == pytest.approx(1) and (w >= 0).all() and w[0] > 0.95


def test_crps_normal_known_value():
    # CRPS de N(0,1) evaluada en 0 = 2*phi(0) - 1/sqrt(pi)
    assert crps_normal(0.0, 0.0, 1.0) == pytest.approx(2 * 0.3989422804 - 1 / np.sqrt(np.pi))


def test_dm_detects_better_model():
    rng = np.random.default_rng(1)
    e_b = rng.normal(0, 1, 120)
    e_m = 0.5 * e_b + rng.normal(0, 0.1, 120)
    stat, p, n = dm_hln(e_m, e_b, 1)
    assert stat < 0 and p < 0.01 and n == 120
    stat2, p2, _ = dm_hln(e_b, e_b + rng.normal(0, 1e-9, 120), 3)
    assert p2 > 0.05


def test_combine_uses_only_past_vintage_and_selects_best():
    # Dos modelos: "good" pronostica el observado; "bad" le suma 1. En el pasado (vintage del origen) "good" acierta.
    origins = pd.period_range("2020-01", periods=30, freq="M")
    rows = []
    truth = pd.Series(np.arange(60, dtype=float) * 0.01, index=pd.period_range("2020-01", periods=60, freq="M"))
    for o in origins:
        for h in range(1, 4):
            t = o + h
            for mdl, bias in [("good", 0.0), ("bad", 1.0)]:
                v = truth[t] + bias
                rows.append({"origin": o, "target": t, "h": h, "model": mdl, "variable": "x", "scenario": "s",
                             "point": v, "q0.025": v, "q0.16": v, "q0.5": v, "q0.84": v, "q0.975": v})
    fc = pd.DataFrame(rows)
    vint = pd.DataFrame([{"origin": o, "period": p, "y_x": truth[p]} for o in origins for p in truth.index if p <= o])
    ens, log = combine(fc, vint, {"all": ["good", "bad"]})
    w = log[log["scheme"] == "w"].iloc[-1]
    chosen = {w["m0"]: w["w0"], w.get("m1"): w.get("w1")}
    assert chosen.get("good", 0) > 0.99
    # El primer origen con ensamble necesita errores pasados suficientes: nunca el primer origen.
    assert ens["origin"].min() > origins[0]
