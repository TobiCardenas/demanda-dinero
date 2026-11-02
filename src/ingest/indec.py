"""INDEC: archivos del FTP (IPC, EMAE) y series de datos.gob.ar (núcleo, PIB, controles cruzados)."""

from __future__ import annotations

import io
import json

import pandas as pd

from .common import Snapshot, SourceError, http_get, load_yaml

MONTHS_ES = {m: i for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}


def ingest(snap: Snapshot) -> None:
    cfg = load_yaml("series.yaml")
    for name, spec in cfg["indec_ftp"].items():
        ext = spec["url"].rsplit(".", 1)[-1]
        content = http_get(spec["url"])
        if content.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
            raise SourceError(f"INDEC {name}: devolvió HTML en lugar de datos ({spec['url']})")
        snap.write(f"indec_{name}.{ext}", content, source=spec["url"])
        print(f"  INDEC {name:14s} {len(content):>9d} bytes")

    dg = cfg["datos_gob"]
    for name, spec in dg["series"].items():
        raw = http_get(dg["base_url"], params={"ids": spec["id"], "format": "json", "metadata": "full", "limit": 5000})
        payload = json.loads(raw)
        if "errors" in payload or not payload.get("data"):
            raise SourceError(f"datos.gob.ar {spec['id']}: {str(payload)[:300]}")
        snap.write(f"datosgob_{name}.json", raw, source=f"{dg['base_url']}?ids={spec['id']}")
        print(f"  datos.gob.ar {name:16s} último={payload['data'][-1][0]}")


def parse_ipc(snap: Snapshot) -> pd.Series:
    raw = snap.path("indec_ipc_divisiones.csv").read_bytes().decode("latin-1")
    df = pd.read_csv(io.StringIO(raw), sep=";", dtype=str)
    sel = df[(df["Codigo"].str.strip() == "0") & (df["Region"].str.strip() == "Nacional")]
    if sel.empty:
        raise SourceError("IPC: no se encontró Nivel General Nacional en el CSV de INDEC")
    idx = pd.PeriodIndex(sel["Periodo"].str.strip(), freq="M")
    vals = sel["Indice_IPC"].str.replace(",", ".", regex=False).astype(float).values
    return pd.Series(vals, index=idx, name="ipc_headline").sort_index()


def parse_emae(snap: Snapshot) -> pd.DataFrame:
    x = pd.read_excel(snap.path("indec_emae.xls"), header=None, engine="xlrd")
    header = x.iloc[2].astype(str)
    if "Original" not in header.iloc[2] or "Desestacionalizada" not in header.iloc[4]:
        raise SourceError(f"EMAE: cambió el formato de columnas: {list(header)}")
    year, out = None, []
    for _, row in x.iloc[5:].iterrows():
        if pd.notna(row[0]) and str(row[0]).strip().isdigit():
            year = int(str(row[0]).strip())
        month = MONTHS_ES.get(str(row[1]).strip().lower()) if pd.notna(row[1]) else None
        if year and month and pd.notna(row[2]):
            out.append((pd.Period(year=year, month=month, freq="M"), float(row[2]), float(row[4])))
    df = pd.DataFrame(out, columns=["period", "emae_orig", "emae_sa"]).set_index("period")
    if df.index.has_duplicates:
        raise SourceError("EMAE: períodos duplicados al parsear el xls")
    return df


def parse_datos_gob(snap: Snapshot, name: str) -> pd.Series:
    payload = json.loads(snap.path(f"datosgob_{name}.json").read_text(encoding="utf-8"))
    freq = "Q" if payload["meta"][0]["frequency"] == "quarter" else "M"
    df = pd.DataFrame(payload["data"], columns=["date", name]).dropna()
    idx = pd.PeriodIndex(pd.to_datetime(df["date"]), freq=freq)
    return pd.Series(df[name].astype(float).values, index=idx, name=name).sort_index()
