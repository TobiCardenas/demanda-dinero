"""Descarga todas las fuentes a un snapshot nuevo: python -m src.ingest.run"""

from __future__ import annotations

import sys

from . import bcra, futuros, indec, medios_pago, rem
from .common import Snapshot, SourceError


def main(argv: list[str]) -> int:
    snap = Snapshot()
    if "--amend" in argv:
        # Agrega al snapshot de hoy las series del BCRA que falten (p. ej. tras corregir un id).
        # Nunca reescribe archivos existentes; las descargas nuevas quedan con su hora en el manifest.
        if not snap.is_complete():
            print("ERROR: --amend solo aplica sobre un snapshot completo.", file=sys.stderr)
            return 1
        try:
            bcra.ingest(snap)
        except SourceError as exc:
            print(f"\nERROR DE FUENTE: {exc}", file=sys.stderr)
            return 1
        return 0
    if snap.is_complete():
        print(f"Ya existe el snapshot completo {snap.dir}. No se sobrescribe; se usa tal cual.")
        return 0
    if snap.exists():
        print(f"ERROR: {snap.dir} existe pero está incompleto (sin _COMPLETE). Revisarlo y borrarlo a mano.",
              file=sys.stderr)
        return 1
    print(f"Snapshot {snap.dir}")
    try:
        for mod in (bcra, indec, medios_pago, rem, futuros):
            mod.ingest(snap)
    except SourceError as exc:
        print(f"\nERROR DE FUENTE: {exc}\nEl snapshot {snap.dir} quedó incompleto: revisarlo y borrarlo a mano.",
              file=sys.stderr)
        return 1
    snap.finalize()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
