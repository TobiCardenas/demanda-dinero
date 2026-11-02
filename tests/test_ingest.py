import datetime as dt
import json

import pandas as pd
import pytest

from src.ingest import bcra, indec, medios_pago, rem
from src.ingest.common import Snapshot, SourceError, latest_snapshot, load_yaml


# --- Snapshot inmutable -------------------------------------------------------------------

def test_snapshot_never_overwrites(tmp_path):
    snap = Snapshot(dt.date(2026, 1, 15), root=tmp_path)
    snap.write("a.json", b"1", source="test")
    with pytest.raises(FileExistsError):
        snap.write("a.json", b"2", source="test")
    assert snap.path("a.json").read_bytes() == b"1"
    assert json.loads(snap.manifest_path.read_text())["a.json"]["bytes"] == 1


def test_latest_snapshot_ignores_incomplete(tmp_path):
    old = Snapshot(dt.date(2026, 1, 1), root=tmp_path)
    old.write("x", b"x", source="t")
    old.finalize()
    Snapshot(dt.date(2026, 2, 1), root=tmp_path).write("x", b"x", source="t")  # sin _COMPLETE
    assert latest_snapshot(tmp_path).date == dt.date(2026, 1, 1)


def test_bcra_parse_rejects_id_mismatch(tmp_path, monkeypatch):
    snap = Snapshot(dt.date(2026, 1, 1), root=tmp_path)
    var_id = load_yaml("series.yaml")["bcra_api"]["series"]["circ_public"]["id"]
    body = {"idVariable": 60, "detalle": [{"fecha": "2026-01-02", "valor": 1.0}]}
    snap.write(f"bcra_circ_public_{var_id}.json", json.dumps(body).encode(), source="t")
    with pytest.raises(SourceError):
        bcra.parse(snap, "circ_public")


# --- Configuración ------------------------------------------------------------------------

def test_series_config_documented():
    cfg = load_yaml("series.yaml")
    ids = [s["id"] for s in cfg["bcra_api"]["series"].values()]
    assert len(ids) == len(set(ids))
    for group in (cfg["bcra_api"]["series"], cfg["datos_gob"]["series"], cfg["indec_ftp"], cfg["bcra_xlsx"]):
        for name, spec in group.items():
            assert spec.get("verified"), f"{name} sin fecha de verificación"


def test_currency_is_stock_not_flow():
    # Los ids 60-66 de Series.xlsm son variaciones diarias; el circulante debe ser el saldo (67).
    assert load_yaml("series.yaml")["bcra_api"]["series"]["circ_public"]["id"] == 67


# --- Parsers sobre el último snapshot real -------------------------------------------------

@pytest.fixture(scope="module")
def snap():
    try:
        return latest_snapshot()
    except FileNotFoundError:
        pytest.skip("no hay snapshot; correr python -m src.ingest.run")


def test_parse_ipc(snap):
    ipc = indec.parse_ipc(snap)
    assert ipc.index[0] == pd.Period("2016-12", "M") and ipc.iloc[0] == pytest.approx(100)
    assert ipc.index.is_monotonic_increasing and not ipc.index.has_duplicates


def test_parse_emae(snap):
    emae = indec.parse_emae(snap)
    assert emae.index[0] == pd.Period("2004-01", "M")
    assert pd.period_range(emae.index[0], emae.index[-1], freq="M").equals(emae.index)
    assert emae["emae_sa"].between(50, 400).all()


def test_parse_payments(snap):
    pay = medios_pago.parse(snap)
    assert {"transf_push_ars_monto", "pct_monto", "debit_card_monto"} <= set(pay.columns)
    assert pay["transf_push_ars_monto"].dropna().gt(0).all()


def test_parse_rem(snap):
    r = rem.parse(snap)
    assert r["forecast_date"].min() <= pd.Timestamp("2016-07-01")
    assert r["variable"].str.contains("Precios minoristas").any()
    assert r["variable"].str.contains("cambio", case=False).any()


def test_parse_wallets(snap):
    w = medios_pago.parse_wallets(snap)
    s = w["fci_psp_saldo"].dropna()
    assert s.index.min() == pd.Period("2023-08", "M")
    assert pd.period_range(s.index.min(), s.index.max(), freq="M").equals(s.index)
    assert (s > 0).all() and (w["fci_psp_clientes"].dropna() > 1e6).all()


def test_deposit_ids_pesos_vs_usd():
    # 104 y 106 tienen la misma descripción; 104 son dólares valuados en pesos y 106 el total.
    s = load_yaml("series.yaml")["bcra_api"]["series"]
    assert s["dep_priv_usd_104"]["id"] == 104 and s["dep_priv_total_106"]["id"] == 106
