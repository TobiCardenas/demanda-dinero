"""Familia 1: VECM (ecs. 1-3 del AT 5).

Relación de largo plazo: Johansen sobre [y, act, co, X...] con constante restringida al vector de
cointegración (deterministic='ci'), rezagos por AIC (máx. 4) y rango 1 impuesto. La traza de Johansen
se guarda y se reporta, pero no decide el rango (T chico).

Pronóstico condicional: con el vector de cointegración de Johansen se estima por MCO la ECM
uniecuacional de y condicional en act, co (corrientes y rezagadas) y dummies. Es la variante
"ECM de un solo paso equivalente" del plan; se usa porque el escenario fija act y co.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

from .base import ConditionalECM, ECMParams


class VECMModel(ConditionalECM):
    family = "F1_vecm"

    def _estimate(self, y: np.ndarray) -> ECMParams:
        d = self.d
        z_rest = d[self.level_vars()].to_numpy()
        Z = np.column_stack([y, z_rest])
        res = VECM(Z, k_ar_diff=self.p, coint_rank=1, deterministic="ci").fit()
        beta = res.beta[:, 0] / res.beta[0, 0]
        const = float(np.ravel(res.det_coef_coint)[0]) / res.beta[0, 0]
        lr = {"vars": self.level_vars(), "beta_rest": beta[1:], "const": const}
        ylp = self.long_run(d, lr)
        act, co, F = self._arrays(d)
        X = self.sr_design(y, act, co, F, self.p, self.t0)
        ec = (y - ylp)[self.t0 - 1:-1]
        target = np.diff(y)[self.t0 - 1:]
        coef, *_ = np.linalg.lstsq(np.column_stack([X, ec]), target, rcond=None)
        p, k = self.p, len(self.dcols)
        resid = target - np.column_stack([X, ec]) @ coef
        return ECMParams(b=coef[:p], phi=coef[p:2 * p + 1], fi=coef[2 * p + 1:3 * p + 2],
                         g=coef[3 * p + 2:3 * p + 2 + k], theta=float(coef[-1]), lr=lr,
                         sigma=float(resid.std(ddof=X.shape[1] + 1)))

    def long_run(self, levels, lr: dict) -> np.ndarray:
        # ec = y + beta_rest'z + c  =>  y_lp = -(beta_rest'z + c)
        return -(levels[lr["vars"]].to_numpy() @ lr["beta_rest"] + lr["const"])

    def structural(self) -> dict:
        """Coeficientes de la ec. 1: y_lp = a0 + a1*co + a2*act + ai*X."""
        lr = self.params.lr
        out = {"a0": -lr["const"]}
        for v, b in zip(lr["vars"], lr["beta_rest"]):
            out[{"act": "a2_act", "co": "a1_co"}.get(v, f"a_{v}")] = -b
        out["theta"] = self.params.theta
        return out

    def johansen_trace(self) -> dict:
        jt = coint_johansen(self.d[[self.ycol] + self.level_vars()].to_numpy(), det_order=0, k_ar_diff=self.p)
        return {"trace_r0": float(jt.lr1[0]), "cv95_r0": float(jt.cvt[0, 1]),
                "trace_r1": float(jt.lr1[1]), "cv95_r1": float(jt.cvt[1, 1])}
