"""Tests de modelos sobre datos simulados con parámetros conocidos."""

import numpy as np
import pandas as pd
import pytest

from src.models.ecm_logistic import LogisticECM, weight
from src.models.vecm import VECMModel

T = 240
IDX = pd.period_range("2000-01", periods=T, freq="M")


def _regressors(rng):
    act = 4.6 + np.cumsum(0.002 + rng.normal(0, 0.01, T))
    co = np.empty(T)
    co[0] = 0.03
    for t in range(1, T):
        co[t] = 0.03 + 0.9 * (co[t - 1] - 0.03) + rng.normal(0, 0.004)
    alt = np.linspace(-2.2, 2.2, T) + rng.normal(0, 0.05, T)  # transición completa dentro de la muestra
    return act, co, alt


def _simulate(lr_fn, act, co, alt, rng, theta=-0.35, b1=0.2, phi0=0.3, sd=0.004):
    ylp = lr_fn(act, co, alt)
    y = np.empty(T)
    y[:2] = ylp[:2]
    for t in range(2, T):
        dy = b1 * (y[t - 1] - y[t - 2]) + phi0 * (act[t] - act[t - 1]) + theta * (y[t - 1] - ylp[t - 1])
        y[t] = y[t - 1] + dy + rng.normal(0, sd)
    return pd.DataFrame({"y_circ": y, "act": act, "co": co, "alt": alt}, index=IDX)


TRUE = dict(a0=1.0, b_inf=0.3, a1=-6.0, a2=1.1, theta_alt=0.2, lam=3.0)


def _logistic_lr(act, co, alt, p=TRUE):
    w = weight(alt, p["theta_alt"], p["lam"])
    return p["a0"] + p["b_inf"] * act + w * (p["a1"] * co + (p["a2"] - p["b_inf"]) * act)


def test_logistic_recovers_transition():
    rng = np.random.default_rng(1)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    m = LogisticECM("circ", [], {}, p=1).fit(panel, IDX[-1])
    lr = m.params.lr
    assert lr["theta_alt"] == pytest.approx(TRUE["theta_alt"], abs=0.25)
    assert lr["lambda"] == pytest.approx(TRUE["lam"], rel=0.5)
    assert m.params.theta == pytest.approx(-0.35, abs=0.1)
    assert lr["b_inf"] == pytest.approx(TRUE["b_inf"], abs=0.15)
    assert m.identification()["ssr_rel_range"] > 0.05  # perfil no plano


def test_logistic_profile_flat_without_transition():
    # Si alt no cruza theta_alt (w ~ constante), el perfil en theta debe ser casi plano.
    rng = np.random.default_rng(2)
    act, co, alt = _regressors(rng)
    alt_far = alt * 0.05 - 5  # todo muy por debajo del umbral: w = 1 siempre
    panel = _simulate(lambda a, c, z: 1 + 1.1 * a - 6 * c, act, co, alt_far, rng)
    m = LogisticECM("circ", [], {}, p=1).fit(panel, IDX[-1])
    assert m.identification()["theta_profile_rel_range"] < 0.02


def test_vecm_recovers_long_run():
    rng = np.random.default_rng(3)
    act, co, alt = _regressors(rng)
    panel = _simulate(lambda a, c, z: 1.0 + 0.8 * a - 4.0 * c, act, co, alt, rng)
    m = VECMModel("circ", [], {}, p=1).fit(panel, IDX[-1])
    s = m.structural()
    assert s["a2_act"] == pytest.approx(0.8, abs=0.15)
    assert s["a1_co"] == pytest.approx(-4.0, abs=1.5)
    assert s["theta"] == pytest.approx(-0.35, abs=0.12)


@pytest.mark.parametrize("cls", [VECMModel, LogisticECM])
def test_fit_ignores_data_after_origin(cls):
    rng = np.random.default_rng(4)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[200]
    a = cls("circ", [], {}, p=1).fit(panel, origin)
    poisoned = panel.copy()
    poisoned.loc[poisoned.index > origin, :] = 1e6  # centinela posterior al origen
    b = cls("circ", [], {}, p=1).fit(poisoned, origin)
    assert a.params.theta == b.params.theta
    np.testing.assert_array_equal(a.resid, b.resid)
    assert a.d.index.max() == origin


def test_forecast_quantiles_ordered_and_centered():
    rng = np.random.default_rng(5)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[220]
    m = VECMModel("circ", [], {}, p=1, seed=7).fit(panel, origin)
    sc = panel.loc[panel.index > origin, ["act", "co", "alt"]]
    fc = m.forecast(sc, 6, n_sims=60)
    q = fc[[c for c in fc.columns if c.startswith("q")]].to_numpy()
    assert (np.diff(q, axis=1) >= 0).all()
    assert list(fc.index) == list(sc.index[:6])
    # Con shocks y parámetros simulados, la mediana debe quedar cerca del punto determinístico.
    assert np.abs(fc["q0.5"] - fc["point"]).max() < 0.02


def test_intercept_correction_k1_zeroes_origin_gap():
    from src.models.robust import intercept_corrected
    rng = np.random.default_rng(6)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[200]
    m = intercept_corrected(VECMModel, 1, "circ", [], {}, p=1).fit(panel, origin)
    lr = m.params.lr
    gap = m.d["y_circ"].iloc[-1] - (m.long_run(m.d, lr)[-1] + lr["shift"])
    assert abs(gap) < 1e-12
    # Con la brecha en cero y regresores constantes, la proyección no corrige hacia el equilibrio estimado.
    flat = pd.DataFrame({"act": m.d["act"].iloc[-1], "co": m.d["co"].iloc[-1]}, index=IDX[201:207])
    fc = m.forecast(flat, 6, n_sims=1)
    assert np.abs(fc["point"] - m.d["y_circ"].iloc[-1]).max() < 0.02


def test_diff_ecm_has_no_error_correction():
    from src.models.robust import DiffECM
    rng = np.random.default_rng(7)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    m = DiffECM("circ", [], {}, p=1).fit(panel, IDX[-1])
    assert m.params.theta == 0.0


def test_tvp_and_benchmarks_forecast_shapes():
    from src.models.benchmarks import AutoARIMA, RandomWalk, RandomWalkDrift
    from src.models.robust import TVPModel
    rng = np.random.default_rng(8)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[200]
    sc = panel.loc[panel.index > origin, ["act", "co", "alt"]]
    for m in [TVPModel("circ", {}), RandomWalk("circ"), RandomWalkDrift("circ"), AutoARIMA("circ")]:
        fc = m.fit(panel, origin).forecast(sc, 6, 50)
        q = fc[[c for c in fc.columns if c.startswith("q")]].to_numpy()
        assert fc.shape[0] == 6 and (np.diff(q, axis=1) >= 0).all() and fc["point"].notna().all()
    rw = RandomWalk("circ").fit(panel, origin).forecast(sc, 3)
    assert (rw["point"] == panel.loc[origin, "y_circ"]).all()


def test_tvp_tracks_level_shift():
    # Con un salto permanente del nivel, el TVP debe pronosticar cerca del nivel nuevo.
    from src.models.robust import TVPModel
    rng = np.random.default_rng(9)
    act, co, alt = _regressors(rng)
    y = 1 + 0.8 * act - 4 * co + rng.normal(0, 0.003, T)
    y[150:] += 0.3
    panel = pd.DataFrame({"y_circ": y, "act": act, "co": co, "alt": alt}, index=IDX)
    m = TVPModel("circ", {}).fit(panel, IDX[200])
    fc = m.forecast(panel.loc[panel.index > IDX[200], ["act", "co"]], 3)
    truth = 1.3 + 0.8 * act[201:204] - 4 * co[201:204]
    assert np.abs(fc["point"].to_numpy() - truth).max() < 0.05


def test_forecast_without_reestimation_is_shock_only():
    rng = np.random.default_rng(10)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[220]
    m = VECMModel("circ", [], {}, p=1, seed=3).fit(panel, origin)
    sc = panel.loc[panel.index > origin, ["act", "co", "alt"]]
    a = m.forecast(sc, 6, 80, reestimate=False)
    # Parámetros fijos: el primer paso de cada simulación es el punto más un residuo centrado remuestreado.
    dev = m.paths[:, 0] - a["point"].iloc[0]
    e = m.resid - m.resid.mean()
    assert all(np.isclose(e, v).any() for v in dev)
    b = m.forecast(sc, 6, 80, reestimate=True)
    np.testing.assert_allclose(a["point"], b["point"])


def test_vectorized_paths_match_loop():
    rng = np.random.default_rng(11)
    panel = _simulate(_logistic_lr, *_regressors(rng), rng)
    origin = IDX[220]
    sc = panel.loc[panel.index > origin, ["act", "co", "alt"]]
    for cls in (VECMModel, LogisticECM):
        m = cls("circ", [], {}, p=2).fit(panel, origin)
        shocks = rng.normal(0, 0.01, (4, 6))
        vec = m._paths_fixed(m.params, sc, 6, shocks)
        loop = np.vstack([m._path(m.params, sc, 6, shocks[i]) for i in range(4)])
        np.testing.assert_allclose(vec, loop, atol=1e-12)
