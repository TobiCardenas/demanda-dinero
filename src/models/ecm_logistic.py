"""Familia 2: ECM no lineal con transición logística (ecs. 4-5 del AT 5).

    y_lp = a0 + b_inf*act + w*[a1*co + (a2 - b_inf)*act] (+ ax*X)
    w    = 1 / (1 + exp(-lambda*(theta_alt - alt)))

Estimación en un paso por mínimos cuadrados no lineales, concentrando: dados (theta_alt, lambda), la
ec. 2 es lineal en los regresores y_{t-1}, 1, act_{t-1}, (w*co)_{t-1}, (w*act)_{t-1} (y X_{t-1}), así que
la SCR concentrada se obtiene por MCO. Se recorre una grilla (perfil de la SCR, que se guarda) y se
refina el mejor punto con Nelder-Mead sobre (theta_alt, log lambda).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .base import ConditionalECM, ECMParams


def weight(alt, theta_alt: float, lam: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-lam * (theta_alt - np.asarray(alt, dtype=float))))


class LogisticECM(ConditionalECM):
    family = "F2_logistic"

    def __init__(self, *args, grid: dict | None = None, **kw):
        super().__init__(*args, **kw)
        self.grid = grid or {"theta_quantiles": [0.10, 0.90], "n_theta": 17,
                             "lambda": [0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 20]}

    def level_vars(self) -> list[str]:
        return ["act", "co", "alt"] + [v for v in self.determinants if v != "alt"]

    def _xvars(self) -> list[str]:
        return [v for v in self.determinants if v != "alt"]

    def _ols(self, y: np.ndarray, theta_alt: float, lam: float):
        d = self.d
        act, co, F = self._arrays(d)
        X_sr = self.sr_design(y, act, co, F, self.p, self.t0)
        w = weight(d["alt"].to_numpy(), theta_alt, lam)
        lag = slice(self.t0 - 1, -1)
        lr_cols = [y[lag], np.ones(len(y) - self.t0), act[lag], (w * co)[lag], (w * act)[lag]]
        lr_cols += [d[v].to_numpy()[lag] for v in self._xvars()]
        X = np.column_stack([X_sr] + lr_cols)
        target = np.diff(y)[self.t0 - 1:]
        coef, *_ = np.linalg.lstsq(X, target, rcond=None)
        resid = target - X @ coef
        return coef, float(resid @ resid), X_sr.shape[1], X.shape[1]

    def _estimate_boot(self, y: np.ndarray) -> ECMParams:
        # En el bootstrap se reoptimiza localmente desde el estimador puntual, sin recorrer la grilla.
        lr = self.params.lr
        return self._estimate(y, start=(lr["theta_alt"], lr["lambda"]))

    def _estimate(self, y: np.ndarray, keep_profile: bool = False, start: tuple | None = None) -> ECMParams:
        alt = self.d["alt"].iloc[self.t0 - 1:-1]
        a_min, a_max = float(alt.min()), float(alt.max())
        if start is None:
            lo, hi = np.quantile(alt, self.grid["theta_quantiles"])
            thetas = np.linspace(lo, hi, self.grid["n_theta"])
            prof = [(th, lam, self._ols(y, th, lam)[1]) for th in thetas for lam in self.grid["lambda"]]
            prof = pd.DataFrame(prof, columns=["theta_alt", "lambda", "ssr"])
            best = prof.loc[prof["ssr"].idxmin()]
        else:
            prof = None
            best = pd.Series({"theta_alt": start[0], "lambda": start[1], "ssr": self._ols(y, *start)[1]})

        def obj(v):
            th, loglam = v
            if not (a_min <= th <= a_max) or not (np.log(0.1) <= loglam <= np.log(50)):
                return 1e12
            return self._ols(y, th, np.exp(loglam))[1]

        opt = minimize(obj, x0=[best["theta_alt"], np.log(best["lambda"])], method="Nelder-Mead",
                       options={"xatol": 1e-4, "fatol": 1e-12, "maxiter": 400})
        th, lam = (opt.x[0], float(np.exp(opt.x[1]))) if opt.fun <= best["ssr"] else (best["theta_alt"], best["lambda"])
        coef, ssr, n_sr, n_all = self._ols(y, th, lam)
        p, k = self.p, len(self.dcols)
        c = coef[n_sr:]
        theta = float(c[0])
        b_inf = -c[2] / theta
        lr = {"theta_alt": float(th), "lambda": float(lam), "a0": -c[1] / theta, "b_inf": b_inf,
              "a1": -c[3] / theta, "a2": -c[4] / theta + b_inf,
              "ax": {v: -cv / theta for v, cv in zip(self._xvars(), c[5:])}}
        if keep_profile:
            self.profile = prof
        sr = coef[:n_sr]
        return ECMParams(b=sr[:p], phi=sr[p:2 * p + 1], fi=sr[2 * p + 1:3 * p + 2], g=sr[3 * p + 2:3 * p + 2 + k],
                         theta=theta, lr=lr, sigma=float(np.sqrt(ssr / (len(y) - self.t0 - n_all))),
                         extra={"ssr": ssr, "grid_best": best.to_dict()})

    def fit(self, panel: pd.DataFrame, origin: pd.Period) -> "LogisticECM":
        super().fit(panel, origin)
        self._estimate(self.d[self.ycol].to_numpy(), keep_profile=True)
        return self

    def long_run(self, levels, lr: dict) -> np.ndarray:
        act, co = levels["act"].to_numpy(), levels["co"].to_numpy()
        w = weight(levels["alt"].to_numpy(), lr["theta_alt"], lr["lambda"])
        out = lr["a0"] + lr["b_inf"] * act + w * (lr["a1"] * co + (lr["a2"] - lr["b_inf"]) * act)
        for v, a in lr["ax"].items():
            out = out + a * levels[v].to_numpy()
        return out

    def w_path(self, levels=None) -> pd.Series:
        lv = self.d if levels is None else levels
        return pd.Series(weight(lv["alt"], self.params.lr["theta_alt"], self.params.lr["lambda"]), index=lv.index,
                         name="w")

    def identification(self) -> dict:
        """Perfil plano => theta_alt/lambda no identificados. Se informa el rango relativo de la SCR."""
        pr = self.profile
        rel = (pr["ssr"].max() - pr["ssr"].min()) / pr["ssr"].min()
        by_theta = pr.groupby("theta_alt")["ssr"].min()
        best = pr.loc[pr["ssr"].idxmin()]
        return {"ssr_rel_range": float(rel),
                "theta_profile_rel_range": float((by_theta.max() - by_theta.min()) / by_theta.min()),
                "best_on_theta_edge": bool(best["theta_alt"] in (pr["theta_alt"].min(), pr["theta_alt"].max())),
                "best_on_lambda_edge": bool(best["lambda"] in (pr["lambda"].min(), pr["lambda"].max()))}
