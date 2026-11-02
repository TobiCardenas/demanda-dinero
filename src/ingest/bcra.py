"""API de estadísticas monetarias del BCRA (v4.0)."""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from .common import Snapshot, SourceError, http_get, load_yaml

PAGE = 3000


def fetch_series(base_url: str, var_id: int, start: str, end: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        raw = http_get(f"{base_url}/{var_id}", params={"desde": start, "hasta": end, "limit": PAGE, "offset": offset})
        payload = json.loads(raw)
        if payload.get("status") != 200 or not payload.get("results"):
            raise SourceError(f"BCRA id {var_id}: respuesta inesperada {str(payload)[:300]}")
        detail = payload["results"][0]["detalle"]
        rows.extend(detail)
        count = payload["metadata"]["resultset"]["count"]
        offset += len(detail)
        if offset >= count or not detail:
            break
    return rows


def ingest(snap: Snapshot) -> None:
    cfg = load_yaml("series.yaml")["bcra_api"]
    if snap.has("bcra_catalog.json"):
        catalog = snap.path("bcra_catalog.json").read_bytes()
    else:
        catalog = http_get(cfg["catalog_url"])
        snap.write("bcra_catalog.json", catalog, source=cfg["catalog_url"])
    cat = {r["idVariable"]: r for r in json.loads(catalog)["results"]}

    end = dt.date.today().isoformat()
    for name, spec in cfg["series"].items():
        if spec["id"] not in cat:
            raise SourceError(f"El id {spec['id']} ({name}) ya no figura en el catálogo del BCRA")
        fname = _fname(name, spec["id"])
        if snap.has(fname):
            continue
        rows = fetch_series(cfg["base_url"], spec["id"], cfg["start"], end)
        body = json.dumps({"idVariable": spec["id"], "detalle": rows}, ensure_ascii=False).encode()
        snap.write(fname, body, source=f"{cfg['base_url']}/{spec['id']}",
                   meta={"catalog_desc": cat[spec["id"]]["descripcion"].strip(), "n": len(rows)})
        print(f"  BCRA {name:16s} id={spec['id']:<5} n={len(rows):5d} último={rows[0]['fecha'] if rows else '-'}")


def _fname(name: str, var_id: int) -> str:
    # El id va en el nombre: si cambia el id en la configuración, se agrega un archivo nuevo en vez de pisar.
    return f"bcra_{name}_{var_id}.json"


def parse(snap: Snapshot, name: str) -> pd.Series:
    var_id = load_yaml("series.yaml")["bcra_api"]["series"][name]["id"]
    payload = json.loads(snap.path(_fname(name, var_id)).read_text(encoding="utf-8"))
    if payload["idVariable"] != var_id:
        raise SourceError(f"{name}: el archivo tiene id {payload['idVariable']} y la configuración pide {var_id}")
    df = pd.DataFrame(payload["detalle"])
    s = pd.Series(df["valor"].astype(float).values, index=pd.to_datetime(df["fecha"]), name=name)
    s = s.sort_index()
    if s.index.has_duplicates:
        raise SourceError(f"{name}: fechas duplicadas en la respuesta del BCRA")
    return s
