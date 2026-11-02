"""Interfaz común y maquinaria de ECM condicional uniecuacional.

Ecuación de corto plazo (ec. 2 del AT 5), condicional en act y co:
    dy_t = sum_{i=1..p} b_i dy_{t-i} + sum_{j=0..p} phi_j dact_{t-j} + sum_{j=0..p} fi_j dco_{t-j}
           + g'F_t + theta * (y_{t-1} - y_lp_{t-1}) + e_t
La constante va restringida a la relación de largo plazo (b0 = 0): b0 y a0 no se identifican por separado.
Cada familia define y_lp_t = lr(levels_t; params).

Bandas: bootstrap de residuos con reestimación. Para cada simulación se genera una muestra y*
recursivamente con el modelo estimado y residuos remuestreados, se reestima, y se proyecta desde la
historia observada con shocks futuros remuestreados. Los regresores se toman como dados (condicional).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

QUANTILES = [0.025, 0.16, 0.5, 0.84, 0.975]


class Model(ABC):
    name: str

    @abstractmethod
    def fit(self, panel: pd.DataFrame, origin: pd.Period) -> "Model": ...

    @abstractmethod
    def forecast(self, scenario: pd.DataFrame, h: int, n_sims: int) -> pd.DataFrame:
        """Cuantiles 0.025, 0.16, 0.5, 0.84, 0.975 por mes, en log de saldos reales s.e."""


@dataclass
class ECMParams:
    b: np.ndarray            # lags de dy (p)
    phi: np.ndarray          # dact_{t..t-p} (p+1)
    fi: np.ndarray           # dco_{t..t-p} (p+1)
    g: np.ndarray            # dummies
    theta: float             # velocidad de ajuste
    lr: dict                 # parámetros de largo plazo (los interpreta la familia)
    sigma: float
    extra: dict = field(default_factory=dict)


class ConditionalECM(Model):
    """Base para las dos familias. Subclases: _estimate(d) -> ECMParams y long_run(levels, lr) -> y_lp."""

    def __init__(self, component: str, determinants: list[str], sample: dict, p: int | None = None,
                 seed: int = 0, name: str | None = None):
        self.component = component
        self.ycol = f"y_{component}"
        self.determinants = list(determinants)
        self.sample = sample
        self.p_fixed = p
        self.seed = seed
        self.name = name or self.__class__.__name__

    # --- datos ---------------------------------------------------------------------------
    def level_vars(self) -> list[str]:
        return ["act", "co"] + self.determinants

    def _sample(self, panel: pd.DataFrame, origin: pd.Period) -> pd.DataFrame:
        d = panel[panel.index <= origin]  # fit() nunca ve datos posteriores al origen
        cols = [self.ycol] + self.level_vars()
        d = d.dropna(subset=cols)
        d = d.loc[d.index.min():]
        full = pd.period_range(d.index.min(), d.index.max(), freq="M")
        if not full.equals(d.index):
            # Se usa el último tramo continuo.
            gaps = full.difference(d.index)
            d = d[d.index > gaps.max()]
        if "start" in self.sample:
            d = d[d.index >= pd.Period(self.sample["start"], "M") - 1 - self.p_max()]
        if "window" in self.sample:
            d = d.iloc[-(self.sample["window"] + 1 + self.p_max()):]
        return d

    def p_max(self) -> int:
        return 4 if self.p_fixed is None else self.p_fixed

    def dummy_cols(self, d: pd.DataFrame) -> list[str]:
        return [c for c in d.columns if c.startswith("d_") and d[c].iloc[self.p_max() + 1:].abs().sum() > 0]

    @staticmethod
    def sr_design(y: np.ndarray, act: np.ndarray, co: np.ndarray, F: np.ndarray, p: int, t0: int) -> np.ndarray:
        """Regresores de corto plazo para t = t0..T-1 (sin término de corrección)."""
        T = len(y)
        dy, dact, dco = np.diff(y, prepend=np.nan), np.diff(act, prepend=np.nan), np.diff(co, prepend=np.nan)
        cols = [dy[t0 - i:T - i] for i in range(1, p + 1)]
        cols += [dact[t0 - j:T - j] for j in range(0, p + 1)]
        cols += [dco[t0 - j:T - j] for j in range(0, p + 1)]
        X = np.column_stack(cols) if cols else np.empty((T - t0, 0))
        return np.column_stack([X, F[t0:T]]) if F.shape[1] else X

    # --- interfaz --------------------------------------------------------------------------
    def fit(self, panel: pd.DataFrame, origin: pd.Period) -> "ConditionalECM":
        self.origin = origin
        self.d = self._sample(panel, origin)
        if self.d.index.max() != origin:
            raise ValueError(f"{self.name}: el último dato utilizable es {self.d.index.max()}, no {origin}")
        self.dcols = self.dummy_cols(self.d)
        self.p = self.p_fixed if self.p_fixed is not None else self.select_p(self.d)
        # La muestra efectiva arranca siempre en p_max + 1, así no depende del rezago elegido.
        self.t0 = self.p_max() + 1
        self.params = self._estimate(self.d[self.ycol].to_numpy())
        self.resid = self._residuals(self.d[self.ycol].to_numpy(), self.params)
        return self

    def select_p(self, d: pd.DataFrame) -> int:
        from statsmodels.tsa.vector_ar.vecm import select_order

        sel = select_order(d[[self.ycol, "act", "co"]].to_numpy(), maxlags=4, deterministic="ci")
        return int(max(1, min(4, sel.aic)))

    @abstractmethod
    def _estimate(self, y: np.ndarray) -> ECMParams: ...

    def _estimate_boot(self, y: np.ndarray) -> ECMParams:
        """Reestimación dentro del bootstrap; las familias pueden abreviarla."""
        return self._estimate(y)

    @abstractmethod
    def long_run(self, levels: pd.DataFrame | dict, lr: dict) -> np.ndarray: ...

    # --- recursión -------------------------------------------------------------------------
    def _arrays(self, d: pd.DataFrame):
        F = d[self.dcols].to_numpy() if self.dcols else np.empty((len(d), 0))
        return d["act"].to_numpy(), d["co"].to_numpy(), F

    def _residuals(self, y: np.ndarray, prm: ECMParams) -> np.ndarray:
        act, co, F = self._arrays(self.d)
        ylp = self.long_run(self.d, prm.lr)
        X = self.sr_design(y, act, co, F, self.p, self.t0)
        fitted = X @ np.r_[prm.b, prm.phi, prm.fi, prm.g] + prm.theta * (y[self.t0 - 1:-1] - ylp[self.t0 - 1:-1])
        return np.diff(y)[self.t0 - 1:] - fitted

    def _step(self, y_hist, act_hist, co_hist, F_t, ylp_prev, prm: ECMParams, shock: float) -> float:
        p = self.p
        dy = np.diff(y_hist[-(p + 1):])[::-1] if p else np.array([])
        dact = np.diff(act_hist[-(p + 2):])[::-1]
        dco = np.diff(co_hist[-(p + 2):])[::-1]
        val = (dy @ prm.b if p else 0.0) + dact @ prm.phi + dco @ prm.fi + (F_t @ prm.g if len(prm.g) else 0.0)
        return y_hist[-1] + val + prm.theta * (y_hist[-1] - ylp_prev) + shock

    def _path(self, prm: ECMParams, scenario: pd.DataFrame, h: int, shocks: np.ndarray) -> np.ndarray:
        hist = self.d
        sc = scenario.iloc[:h]
        levels = pd.concat([hist[self.level_vars()], sc[self.level_vars()]])
        # La corrección de intercepto (si la hay) desplaza el equilibrio solo al proyectar.
        ylp = self.long_run(levels, prm.lr) + prm.lr.get("shift", 0.0)
        y = list(hist[self.ycol].to_numpy())
        act = list(levels["act"].to_numpy())
        co = list(levels["co"].to_numpy())
        n0 = len(hist)
        F = sc.reindex(columns=self.dcols).fillna(0.0).to_numpy()
        for k in range(h):
            t = n0 + k
            y.append(self._step(np.array(y), np.array(act[:t + 1]), np.array(co[:t + 1]), F[k], ylp[t - 1], prm,
                                shocks[k]))
        return np.array(y[n0:])

    def _simulate_sample(self, prm: ECMParams, rng: np.random.Generator) -> np.ndarray:
        """Muestra y* con residuos remuestreados y regresores observados."""
        y_obs = self.d[self.ycol].to_numpy()
        act, co, F = self._arrays(self.d)
        ylp = self.long_run(self.d, prm.lr)
        e = rng.choice(self.resid - self.resid.mean(), size=len(y_obs))
        y = list(y_obs[:self.t0])
        for t in range(self.t0, len(y_obs)):
            y.append(self._step(np.array(y), act[:t + 1], co[:t + 1], F[t], ylp[t - 1], prm, e[t]))
        return np.array(y)

    def _paths_fixed(self, prm: ECMParams, scenario: pd.DataFrame, h: int, shocks: np.ndarray) -> np.ndarray:
        """Igual que _path pero para muchas simulaciones a la vez (shocks: n_sims x h), con parámetros fijos."""
        hist, sc = self.d, scenario.iloc[:h]
        levels = pd.concat([hist[self.level_vars()], sc[self.level_vars()]])
        ylp = self.long_run(levels, prm.lr) + prm.lr.get("shift", 0.0)
        act, co = levels["act"].to_numpy(), levels["co"].to_numpy()
        F = sc.reindex(columns=self.dcols).fillna(0.0).to_numpy()
        n0, p, n = len(hist), self.p, shocks.shape[0]
        Y = np.empty((n, n0 + h))
        Y[:, :n0] = hist[self.ycol].to_numpy()
        for k in range(h):
            t = n0 + k
            val = sum(prm.b[i] * (Y[:, t - 1 - i] - Y[:, t - 2 - i]) for i in range(p))
            val = val + sum(prm.phi[j] * (act[t - j] - act[t - 1 - j]) + prm.fi[j] * (co[t - j] - co[t - 1 - j])
                            for j in range(p + 1))
            if len(prm.g):
                val = val + F[k] @ prm.g
            Y[:, t] = Y[:, t - 1] + val + prm.theta * (Y[:, t - 1] - ylp[t - 1]) + shocks[:, k]
        return Y[:, n0:]

    def forecast(self, scenario: pd.DataFrame, h: int, n_sims: int, reestimate: bool = True) -> pd.DataFrame:
        """reestimate=False: bandas solo con shocks (parámetros fijos), para el origen móvil de la Fase 4."""
        rng = np.random.default_rng(self.seed)
        e = self.resid - self.resid.mean()
        if not reestimate:
            shocks = rng.choice(e, size=(n_sims, h))
            shocks[0] = rng.choice(e, size=h)
            paths = self._paths_fixed(self.params, scenario, h, shocks)
            point = self._paths_fixed(self.params, scenario, h, np.zeros((1, h)))[0]
            out = pd.DataFrame(np.quantile(paths, QUANTILES, axis=0).T, index=scenario.index[:h],
                               columns=[f"q{q}" for q in QUANTILES])
            out["point"] = point
            self.paths = paths
            return out
        paths = np.empty((n_sims, h))
        for s in range(n_sims):
            prm = self.params
            if s > 0 and reestimate:
                try:
                    prm = self._estimate_boot(self._simulate_sample(self.params, rng))
                    if self.ic_k:
                        prm.lr = {**prm.lr, "shift": self._ic_shift(prm, self.ic_k)}
                except Exception:  # una reestimación fallida no invalida la simulación
                    prm = self.params
            paths[s] = self._path(prm, scenario, h, rng.choice(e, size=h))
        point = self._path(self.params, scenario, h, np.zeros(h))
        idx = scenario.index[:h]
        out = pd.DataFrame(np.quantile(paths, QUANTILES, axis=0).T, index=idx, columns=[f"q{q}" for q in QUANTILES])
        out["point"] = point
        self.paths = paths
        return out

    # --- corrección de intercepto (robust.py) ------------------------------------------------
    ic_k: int | None = None

    def ec_path(self, prm: ECMParams | None = None) -> pd.Series:
        """Brecha ec_t = y_t - y_lp_t en la muestra de estimación (sin corrección de intercepto)."""
        prm = prm or self.params
        return pd.Series(self.d[self.ycol].to_numpy() - self.long_run(self.d, prm.lr), index=self.d.index, name="ec")

    def _ic_shift(self, prm: ECMParams, k: int) -> float:
        return float(self.ec_path(prm).iloc[-k:].mean())

    def apply_intercept_correction(self, k: int) -> "ConditionalECM":
        """El equilibrio se corre en la brecha promedio de los últimos k meses: con k=1 la brecha en el
        origen queda en cero y el ECM deja de empujar hacia el nivel estimado."""
        self.ic_k = k
        self.params.lr = {**self.params.lr, "shift": self._ic_shift(self.params, k)}
        return self

