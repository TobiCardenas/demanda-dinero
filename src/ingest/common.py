"""Utilidades de ingesta: configuración, descargas y snapshots inmutables en data/raw/<fecha>/."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
USER_AGENT = "demanda-dinero/0.1 (investigacion academica)"


class SourceError(RuntimeError):
    """Una fuente no respondió o devolvió algo inesperado. La corrida debe detenerse."""


def load_yaml(name: str) -> dict:
    with open(ROOT / "config" / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def http_get(url: str, *, params: dict | None = None, retries: int = 3, timeout: int = 120) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if r.status_code == 200:
                return r.content
            last = f"HTTP {r.status_code}"
            if r.status_code in (404, 410):
                break
        except requests.RequestException as exc:
            last = repr(exc)
        time.sleep(2 * (attempt + 1))
    raise SourceError(f"Fallo al descargar {url} params={params}: {last}")


class Snapshot:
    """Directorio de una descarga. Los archivos se escriben una sola vez y nunca se sobrescriben."""

    def __init__(self, date: dt.date | None = None, root: Path | None = None):
        self.date = date or dt.date.today()
        self.dir = (root or ROOT / "data" / "raw") / self.date.isoformat()
        self.manifest_path = self.dir / "manifest.json"

    def exists(self) -> bool:
        return self.manifest_path.exists()

    def has(self, name: str) -> bool:
        return (self.dir / name).exists()

    def is_complete(self) -> bool:
        return (self.dir / "_COMPLETE").exists()

    def finalize(self) -> None:
        (self.dir / "_COMPLETE").write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    def write(self, name: str, content: bytes, *, source: str, meta: dict | None = None) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / name
        # 'xb' falla si el archivo ya existe: un snapshot nunca se pisa.
        with open(path, "xb") as fh:
            fh.write(content)
        manifest = self.read_manifest()
        manifest[name] = {
            "source": source,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "downloaded_at": dt.datetime.now().isoformat(timespec="seconds"),
            **(meta or {}),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def read_manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {}

    def path(self, name: str) -> Path:
        p = self.dir / name
        if not p.exists():
            raise FileNotFoundError(f"{name} no está en el snapshot {self.dir}")
        return p


def latest_snapshot(root: Path | None = None) -> Snapshot:
    base = root or ROOT / "data" / "raw"
    dates = sorted(p.name for p in base.iterdir() if (p / "_COMPLETE").exists()) if base.exists() else []
    if not dates:
        raise FileNotFoundError("No hay snapshots en data/raw. Correr: python -m src.ingest.run")
    return Snapshot(dt.date.fromisoformat(dates[-1]), root=base)
