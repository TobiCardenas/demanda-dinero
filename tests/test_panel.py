import datetime as dt

import numpy as np
import pandas as pd
import pytest

from src.ingest.common import ROOT, latest_snapshot
from src.transform import validate
from src.transform.panel import monthly_from_daily


def _daily(start, end):
    idx = pd.bdate_range(start, end)
    return pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)


def test_monthly_mean_of_business_days():
    d = _daily("2025-01-01", "2025-03-31")
    m = monthly_from_daily(d, "monthly_mean", asof=dt.date(2025, 5, 10))
    jan = d.loc["2025-01", "x"]
    assert m.loc[pd.Period("2025-01", "M"), "x"] == pytest.approx(jan.mean())


def test_end_of_month_option():
    d = _daily("2025-01-01", "2025-02-28")
    m = monthly_from_daily(d, "end_of_month", asof=dt.date(2025, 5, 10))
    assert m.loc[pd.Period("2025-01", "M"), "x"] == d.loc["2025-01", "x"].iloc[-1]


def test_snapshot_month_and_truncated_months_are_dropped():
    d = _daily("2025-01-01", "2025-03-14")  # marzo cortado a mitad de mes
    m = monthly_from_daily(d, "monthly_mean", asof=dt.date(2025, 5, 10))
    assert np.isnan(m.loc[pd.Period("2025-03", "M"), "x"])
    m2 = monthly_from_daily(_daily("2025-01-01", "2025-02-28"), "monthly_mean", asof=dt.date(2025, 2, 28))
    assert np.isnan(m2.loc[pd.Period("2025-02", "M"), "x"])  # mes del snapshot: incompleto por definición


def test_current_panel_passes_validation():
    if not (ROOT / "data" / "processed" / "panel_monthly.csv").exists():
        pytest.skip("no hay panel; correr python -m src.transform.panel")
    rep = validate.run(latest_snapshot())
    assert rep.errors == [], rep.errors


def test_dav_nr_identity():
    path = ROOT / "data" / "processed" / "daily_bcra.csv"
    if not path.exists():
        pytest.skip("no hay panel")
    d = pd.read_csv(path, index_col=0, parse_dates=True).dropna(subset=["m2_trans_priv"])
    recon = d["circ_public"] + d["cheques_canc"] + d["dav_nr"]
    assert np.allclose(recon, d["m2_trans_priv"])
    assert d.index.min() == pd.Timestamp("2021-01-04")


def test_m2_amp_and_m3_identities():
    path = ROOT / "data" / "processed" / "panel_monthly.csv"
    if not path.exists():
        pytest.skip("no hay panel")
    p = pd.read_csv(path, index_col=0).dropna(subset=["m2_amp"])
    assert np.allclose(p["m2_amp"], p["m2_trans_priv"] + p["fci_psp_saldo"])
    q = pd.read_csv(path, index_col=0).dropna(subset=["m3_priv", "m2_priv"])
    assert (q["m3_priv"] >= q["m2_priv"]).all()


def test_realtime_fill_marks_and_extends_activity():
    from src.transform import model_data as md
    panel = md.load_panel() if (ROOT / "data" / "processed" / "panel_monthly.csv").exists() else None
    if panel is None:
        pytest.skip("no hay panel")
    last_emae = panel["emae_orig"].dropna().index.max()
    origin = panel["m2_trans_priv"].dropna().index.max()
    if origin <= last_emae:
        pytest.skip("no hay meses sin EMAE para completar")
    od = md.build(origin, panel, opts={"realtime_fill": True})
    d = od.data
    assert d.loc[origin, "act_filled"] and not d.loc[last_emae, "act_filled"]
    assert d.loc[:origin, "act"].iloc[-(origin - last_emae).n - 1:].notna().all()
    # Sin la opción, el origen queda sin actividad (comportamiento de las fases 2-4).
    assert pd.isna(md.build(origin, panel).data.loc[origin, "act"])
