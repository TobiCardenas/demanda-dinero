"""Modelos robustos ante cambios de nivel del equilibrio.

- Corrección de intercepto: se proyecta con el ECM estimado, pero el equilibrio se desplaza en la brecha
  promedio de los últimos k meses (k en {1, 3}). Con k=1 la brecha en el origen se anula.
  Interpretación del plan ("ec se reinicia al desvío observado promedio de los últimos k meses"):
  el nivel de equilibrio pasa a ser el observado reciente, no el estimado.
- ECM en diferencias: se elimina el término de corrección (theta = 0) y se reestima la dinámica de dy.
- Parámetros variables: TVPModel (intercepto de largo plazo como caminata aleatoria, filtro de Kalman).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import QUANTILES, ConditionalECM, ECMParams, Model
from .ecm_logistic import LogisticECM
from .vecm import VECMModel


def intercept_corrected(base_cls, k: int, *args, **kw):
    """Instancia de base_cls (VECMModel o LogisticECM) cuyo fit aplica la corrección de intercepto."""

    class IC(base_cls):
        family = f"{base_cls.family}_ic{k}"

        def fit(self, panel, origin):
            super().fit(panel, origin)
            return self.apply_intercept_correction(k)

    IC.__name__ = f"{base_cls.__name__}IC{k}"
    return IC(*args, **kw)


class DiffECM(ConditionalECM):
    family = "diff_ecm"

    def _estimate(self, y: np.ndarray) -> ECMParams:
        act, co, F = self._arrays(self.d)
        X = self.sr_design(y, act, co, F, self.p, self.t0)
        target = np.diff(y)[self.t0 - 1:]
        coef, *_ = np.linalg.lstsq(X, target, rcond=None)
        resid = target - X @ coef
        p, k = self.p, len(self.dcols)
        return ECMParams(b=coef[:p], phi=coef[p:2 * p + 1], fi=coef[2 * p + 1:3 * p + 2], g=coef[3 * p + 2:3 * p + 2 + k],
                         theta=0.0, lr={}, sigma=float(resid.std(ddof=X.shape[1])))

    def long_run(self, levels, lr: dict) -> np.ndarray:
        return np.zeros(len(levels))


class TVPModel(Model):
    """Relación de largo plazo con intercepto variable:
        y_t = mu_t + a2*act_t + a1*co_t + u_t,   mu_t = mu_{t-1} + eta_t,   u_t = rho*u_{t-1} + eps_t
    Estimado por máxima verosimilitud con filtro de Kalman (statsmodels UnobservedComponents)."""

    family = "tvp"

    def __init__(self, component: str, sample: dict, seed: int = 0, name: str = "TVP"):
        self.component, self.ycol, self.sample, self.seed, self.name = component, f"y_{component}", sample, seed, name

    def fit(self, panel: pd.DataFrame, origin: pd.Period) -> "TVPModel":
        import warnings

        from statsmodels.tsa.statespace.structural import UnobservedComponents

        d = panel[panel.index <= origin].dropna(subset=[self.ycol, "act", "co"])
        if "start" in self.sample:
            d = d[d.index >= pd.Period(self.sample["start"], "M")]
        if "window" in self.sample:
            d = d.iloc[-self.sample["window"]:]
        if d.index.max() != origin:
            raise ValueError(f"TVP: último dato {d.index.max()} != origen {origin}")
        self.d, self.origin = d, origin
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.res = UnobservedComponents(d[self.ycol].to_numpy(), level="llevel", autoregressive=1,
                                            exog=d[["act", "co"]].to_numpy()).fit(disp=False, maxiter=500)
        return self

    def forecast(self, scenario: pd.DataFrame, h: int, n_sims: int = 0, reestimate: bool = False) -> pd.DataFrame:
        from scipy.stats import norm

        sc = scenario.iloc[:h]
        f = self.res.get_forecast(h, exog=sc[["act", "co"]].to_numpy())
        mu, sd = np.asarray(f.predicted_mean), np.sqrt(np.asarray(f.var_pred_mean))
        out = pd.DataFrame({f"q{q}": mu + norm.ppf(q) * sd for q in QUANTILES}, index=sc.index)
        out["point"] = mu
        return out


__all__ = ["intercept_corrected", "DiffECM", "TVPModel", "VECMModel", "LogisticECM"]
