"""Desestacionalización en tiempo pseudo-real: X13 sobre la serie truncada en el origen.

Si el binario X13 no está, se usa STL y el resultado queda marcado (method='stl_provisional').
Los resultados se cachean en memoria por (nombre, origen, hash de la serie).
"""

from __future__ import annotations

import hashlib
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.ingest.common import ROOT, load_yaml

_CACHE: dict[tuple, pd.Series] = {}


@lru_cache(maxsize=1)
def _x13_path() -> str | None:
    """Ruta del binario: variable de entorno X13_BINARY (p. ej. en GitHub Actions) o settings.yaml."""
    import os

    env = os.environ.get("X13_BINARY")
    p = Path(env) if env else ROOT / load_yaml("settings.yaml")["paths"]["x13_binary"]
    return str(p) if p.exists() else None


def method() -> str:
    cfg = load_yaml("settings.yaml")["seasonal"]["method"]
    return "x13" if cfg == "x13" and _x13_path() else "stl_provisional"


def seasadj_log(log_series: pd.Series, origin: pd.Period | None = None) -> pd.Series:
    """Desestacionaliza una serie en logaritmos usando solo datos <= origin. Devuelve log s.e."""
    s = log_series.dropna()
    if origin is not None:
        s = s[s.index <= origin]
    key = (s.name, str(s.index[-1]), hashlib.md5(s.values.tobytes()).hexdigest())
    if key in _CACHE:
        return _CACHE[key]
    if method() == "x13":
        from statsmodels.tsa.x13 import x13_arima_analysis

        x = pd.Series(np.exp(s.values), index=s.index.to_timestamp())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = x13_arima_analysis(x, x12path=_x13_path(), log=True, outlier=True)
        out = pd.Series(np.log(res.seasadj.values), index=s.index, name=s.name)
    else:
        from statsmodels.tsa.seasonal import STL

        res = STL(pd.Series(s.values, index=s.index.to_timestamp()), period=12, robust=True).fit()
        out = pd.Series(s.values - res.seasonal.values, index=s.index, name=s.name)
    _CACHE[key] = out
    return out
