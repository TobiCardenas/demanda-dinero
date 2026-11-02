import numpy as np
import pandas as pd
import pytest

from src.transform.ratios import monthly_nominal_gdp_sa, pct_gdp


def _gdp():
    q = pd.period_range("2024Q1", "2025Q2", freq="Q")
    real_sa = pd.Series([100, 101, 102, 103, 104, 105.0], index=q)
    defl = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5], index=q)
    return pd.DataFrame({"gdp_nominal_q": real_sa * defl * 1.02, "gdp_real_q": real_sa * 1.02,
                         "gdp_real_sa_q": real_sa, "gdp_deflator_q": defl})


def test_monthly_average_matches_quarterly_sa():
    gdp = _gdp()
    months = pd.period_range("2024-01", "2025-09", freq="M")
    act = pd.Series(np.log(np.linspace(100, 106, len(months))), index=months)
    log_p = pd.Series(np.linspace(0, 0.5, len(months)), index=months)
    m = monthly_nominal_gdp_sa(act, log_p, pd.Period("2025-09", "M"), gdp)
    target = gdp["gdp_real_sa_q"] * gdp["gdp_nominal_q"] / gdp["gdp_real_q"]
    for q, v in target.items():
        mm = pd.period_range(q.asfreq("M", "start"), q.asfreq("M", "end"), freq="M")
        assert m[mm].mean() == pytest.approx(v, rel=1e-10)
    assert m.index.max() == pd.Period("2025-09", "M")  # extiende más allá del último trimestre


def test_quarters_after_origin_are_ignored():
    gdp = _gdp()
    months = pd.period_range("2024-01", "2025-06", freq="M")
    act = pd.Series(np.log(np.full(len(months), 100.0)), index=months)
    log_p = pd.Series(0.0, index=months)
    a = monthly_nominal_gdp_sa(act, log_p, pd.Period("2025-02", "M"), gdp)
    gdp2 = gdp.copy()
    gdp2.loc[pd.Period("2025Q1", "Q"):, :] *= 50  # trimestres no cerrados al origen
    b = monthly_nominal_gdp_sa(act, log_p, pd.Period("2025-02", "M"), gdp2)
    pd.testing.assert_series_equal(a, b)


def test_pct_gdp_units():
    idx = pd.period_range("2025-01", periods=2, freq="M")
    out = pct_gdp(pd.Series([50.0, 50.0], index=idx), pd.Series(np.log([200.0, 200.0]), index=idx),
                  pd.Series([1000.0, 2000.0], index=idx))
    assert list(out) == pytest.approx([10.0, 5.0])  # 50 * 200/100 = 100 nominal
