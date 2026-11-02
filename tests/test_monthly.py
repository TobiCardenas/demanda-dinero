import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.run_monthly import alarms
from src.transform import freshness


def _panel(last_money="2026-10", last_ipc="2026-09", last_emae="2026-08"):
    idx = pd.period_range("2025-01", "2026-10", freq="M")
    p = pd.DataFrame(index=idx, data={c: 1.0 for c in freshness.SERIES.values()})
    p.loc[p.index > pd.Period(last_money, "M"), "m2_trans_priv"] = np.nan
    p.loc[p.index > pd.Period(last_ipc, "M"), "ipc_headline"] = np.nan
    p.loc[p.index > pd.Period(last_emae, "M"), "emae_orig"] = np.nan
    return p


def _gdp(last="2026Q2"):
    return pd.DataFrame({"gdp_nominal_q": 1.0}, index=pd.period_range("2025Q1", last, freq="Q"))


def _rem(last="2026-09"):
    return pd.DataFrame({"survey": pd.period_range("2026-01", last, freq="M")})


def test_freshness_ok_when_within_limits():
    errs, tab = freshness.check(_panel(), _gdp(), _rem(), dt.date(2026, 11, 18))
    assert errs == [] and tab["ok"].all()


def test_freshness_fails_on_stale_source():
    errs, _ = freshness.check(_panel(last_ipc="2026-07"), _gdp(), _rem(), dt.date(2026, 11, 18))
    assert len(errs) == 1 and "ipc_headline" in errs[0]
    errs, _ = freshness.check(_panel(), _gdp(), _rem(last="2026-07"), dt.date(2026, 11, 18))
    assert any("REM" in e for e in errs)


def _stab(origins, revisions, var="m2"):
    """Estabilidad sintética: y_lp_origin constante y y_lp_prev = valor anterior + revisión."""
    rows, prev = [], 13.0
    for o, r in zip(origins, revisions):
        rows.append({"origin": o, "variable": var, "theta": -0.03, "y_lp_origin": 13.0, "y_lp_prev": prev + r,
                     "ec": -0.1, "realtime": False})
        prev = 13.0
    return pd.DataFrame(rows)


def test_alarm_triggers_on_large_revision_and_positive_theta():
    dev = _stab(pd.period_range("2024-01", "2025-10", freq="M"), [0.01] * 22)
    prev = pd.DataFrame([{"origin": pd.Period("2026-08", "M"), "variable": "m2", "theta": -0.03,
                          "y_lp_origin": 13.0, "y_lp_prev": 13.0, "ec": 0.0, "realtime": True}])
    allst = pd.concat([dev, prev], ignore_index=True)
    small = pd.DataFrame([{"origin": pd.Period("2026-09", "M"), "variable": "m2", "theta": -0.03,
                           "y_lp_origin": 13.0, "y_lp_prev": 13.015, "ec": -0.1}])
    big = small.assign(y_lp_prev=13.05)
    pos_theta = small.assign(theta=0.01)
    assert not alarms(allst, small, 2.0)["alarma"].iloc[0]
    a = alarms(allst, big, 2.0).iloc[0]
    assert a["alarma"] and a["umbral (%)"] == pytest.approx(2.0)
    assert alarms(allst, pos_theta, 2.0)["alarma"].iloc[0]
