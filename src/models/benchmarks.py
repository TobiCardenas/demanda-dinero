"""Benchmarks en log de saldos reales s.e.: caminata aleatoria, caminata con drift (12 meses) y ARIMA automático."""

from __future__ import annotations

import itertools
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm

from .base import QUANTILES, Model


def _normal_quantiles(idx, mu, sd) -> pd.DataFrame:
    out = pd.DataFrame({f"q{q}": mu + norm.ppf(q) * sd for q in QUANTILES}, index=idx)
    out["point"] = mu
    return out


class RandomWalk(Model):
    family = "rw"

    def __init__(self, component: str, seed: int = 0, name: str = "RW"):
        self.component, self.ycol, self.seed, self.name = component, f"y_{component}", seed, name

    def _y(self, panel, origin):
        y = panel.loc[panel.index <= origin, self.ycol].dropna()
        if y.index.max() != origin:
            raise ValueError(f"{self.name}: último dato {y.index.max()} != origen {origin}")
        return y

    def fit(self, panel: pd.DataFrame, origin: pd.Period) -> "RandomWalk":
        y = self._y(panel, origin)
        self.origin, self.y0 = origin, float(y.iloc[-1])
        self.sigma = float(np.diff(y.to_numpy()[-61:]).std(ddof=1))
        return self

    def forecast(self, scenario: pd.DataFrame, h: int, n_sims: int = 0, reestimate: bool = False) -> pd.DataFrame:
        k = np.arange(1, h + 1)
        return _normal_quantiles(scenario.index[:h], self.y0 + 0.0 * k, self.sigma * np.sqrt(k))


class RandomWalkDrift(RandomWalk):
    family = "rw_drift"

    def __init__(self, component: str, seed: int = 0, name: str = "RW_drift"):
        super().__init__(component, seed, name)

    def fit(self, panel, origin):
        super().fit(panel, origin)
        self.drift = float(np.diff(self._y(panel, origin).to_numpy())[-12:].mean())
        return self

    def forecast(self, scenario, h, n_sims=0, reestimate=False):
        k = np.arange(1, h + 1)
        return _normal_quantiles(scenario.index[:h], self.y0 + self.drift * k, self.sigma * np.sqrt(k))


class AutoARIMA(RandomWalk):
    """ARIMA(p,1,q) con drift, p,q en {0,1,2}, elegido por AIC sobre los últimos `window` meses."""

    family = "arima"

    def __init__(self, component: str, seed: int = 0, name: str = "ARIMA", window: int = 120):
        super().__init__(component, seed, name)
        self.window = window

    def fit(self, panel, origin):
        from statsmodels.tsa.arima.model import ARIMA

        y = self._y(panel, origin).iloc[-self.window:]
        self.origin, self.y0 = origin, float(y.iloc[-1])
        best = None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for p, q in itertools.product(range(3), range(3)):
                try:
                    r = ARIMA(y.to_numpy(), order=(p, 1, q), trend="t").fit()
                except Exception:
                    continue
                if best is None or r.aic < best[0]:
                    best = (r.aic, r, (p, q))
        if best is None:
            raise ValueError("ARIMA: ninguna especificación convergió")
        self.res, self.order = best[1], best[2]
        return self

    def forecast(self, scenario, h, n_sims=0, reestimate=False):
        f = self.res.get_forecast(h)
        return _normal_quantiles(scenario.index[:h], np.asarray(f.predicted_mean), np.sqrt(np.asarray(f.var_pred_mean)))
