"""Saldos reales y costo de oportunidad."""

from __future__ import annotations

import numpy as np
import pandas as pd


def real_balance(nominal: pd.Series, price_index: pd.Series) -> pd.Series:
    """Millones de ARS de dic-2016 (IPC dic-2016 = 100)."""
    return (nominal / price_index * 100).dropna()


def opportunity_cost(tna_pct: pd.Series) -> pd.Series:
    """co = ln(1 + i_m), con i_m = TNA/100 * 30/365 (tasa mensualizada)."""
    return np.log1p(tna_pct / 100 * 30 / 365)


def tna_from_co(co: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
    return np.expm1(co) * 365 / 30 * 100
