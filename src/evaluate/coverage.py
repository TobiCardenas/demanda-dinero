"""Cobertura, PIT y CRPS (normal con mu = q0.5 y sigma = (q0.84 - q0.16) / 2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def crps_normal(y, mu, sigma):
    z = (y - mu) / sigma
    return sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def density_metrics(df: pd.DataFrame) -> pd.DataFrame:
    d = df.dropna(subset=["obs", "q0.5"]).copy()
    sigma = ((d["q0.84"] - d["q0.16"]) / 2).clip(lower=1e-8)
    d["in68"] = (d["obs"] >= d["q0.16"]) & (d["obs"] <= d["q0.84"])
    d["in95"] = (d["obs"] >= d["q0.025"]) & (d["obs"] <= d["q0.975"])
    d["pit"] = norm.cdf((d["obs"] - d["q0.5"]) / sigma)
    d["crps"] = 100 * crps_normal(d["obs"], d["q0.5"], sigma)
    g = d.groupby(["variable", "scenario", "model", "h"])
    return g.agg(cov68=("in68", "mean"), cov95=("in95", "mean"), crps=("crps", "mean"),
                 pit_mean=("pit", "mean"), pit_sd=("pit", "std")).reset_index()
