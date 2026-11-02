import numpy as np
import pandas as pd
import pytest

from src.evaluate import published as pub


def _row(**kw):
    base = dict(source="IPOM", chart="x", vintage_label="v1", origin_month=pd.Period("2026-01", "M"),
                origin_value=5.0, target_month=pd.Period("2026-03", "M"), p50=5.2, lo68=5.1, hi68=5.3,
                lo95=5.0, hi95=5.4, observed_same_vintage=4.9, read_method="eyeball", h=2)
    base.update(kw)
    return pd.Series(base)


def test_errors_z_and_direction():
    r = pub.evaluate_row(_row())
    assert r["error"] == pytest.approx(-0.3)
    assert r["error_rw"] == pytest.approx(-0.1)
    assert r["sigma_implied"] == pytest.approx(0.1)
    assert r["z"] == pytest.approx(-3.0)
    assert r["in68"] is False and r["in95"] is False
    assert r["opposite"] and r["dir_hit"] is False


def test_sigma_falls_back_to_95_band():
    r = _row(lo68=np.nan, hi68=np.nan, lo95=5.2 - pub.Z95 * 0.1, hi95=5.2 + pub.Z95 * 0.1)
    assert pub.sigma_from_bands(r) == pytest.approx(0.1)


def test_flat_observed_has_no_direction_hit():
    r = pub.evaluate_row(_row(observed_same_vintage=5.0))
    assert r["dir_observed"] == 0 and r["dir_hit"] is None and not r["opposite"]


def test_read_uncertainty_extremes():
    rng = np.random.default_rng(0)
    clear = pub.read_uncertainty(_row(observed_same_vintage=4.5), rng)  # muy lejos: CA mejor siempre
    assert clear["p_rw_better"] == 1.0 and clear["p_outside95"] == 1.0
    tie = pub.read_uncertainty(_row(observed_same_vintage=5.1, p50=5.2, origin_value=5.0), rng)
    assert 0.3 < tie["p_rw_better"] < 0.7  # equidistante: depende de la lectura


def test_revisions_detects_same_month_in_two_vintages():
    rows = [_row(vintage_label="a", target_month=pd.Period("2026-03", "M"), observed_same_vintage=5.6),
            _row(vintage_label="b", origin_month=pd.Period("2026-03", "M"), origin_value=5.76,
                 target_month=pd.Period("2026-04", "M"), h=1)]
    ev = pub.evaluate(pd.DataFrame(rows))
    rev = pub.revisions(ev)
    hit = rev[rev["month"] == pd.Period("2026-03", "M")]
    assert len(hit) == 1 and hit["revision"].iloc[0] == pytest.approx(0.16)


def test_published_csv_loads_with_horizons():
    df = pub.load()
    assert (df["h"] >= 1).all()
    assert set(df["vintage_label"]) == {"ipom_2026Q1", "prog_abr26", "prog_jul26"}
