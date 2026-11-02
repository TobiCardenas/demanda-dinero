"""Informe mensual de pagos minoristas del BCRA (planilla de series)."""

from __future__ import annotations

import datetime as dt
import io

import openpyxl
import pandas as pd

from .common import Snapshot, SourceError, http_get, load_yaml

# (hoja, fila de encabezado, texto que identifica la columna de "Cantidad"; la siguiente es "Monto")
COLUMNS = {
    "transf_push_ars": ("Transferencias de fondos", 1, 'Transferencias inmediatas "push"'),
    "transf_pull": ("Transferencias de fondos", 1, 'Transferencias inmediatas "pull"'),
    "pct": ("Transferencias de fondos", 1, "Pagos con transferencia interoperables"),
    "debit_card": ("Tarjetas", 0, "Tarjetas de débito"),
    "credit_card": ("Tarjetas", 0, "Tarjetas de crédito"),
}


def ingest(snap: Snapshot, max_back: int = 5) -> None:
    spec = load_yaml("series.yaml")["bcra_xlsx"]["pagos_minoristas"]
    month = dt.date.today().replace(day=1)
    tried = []
    for _ in range(max_back):
        url = spec["url_pattern"].format(yyyy=month.year, mm=f"{month.month:02d}")
        tried.append(url)
        try:
            content = http_get(url, retries=1)
        except SourceError:
            month = (month - dt.timedelta(days=1)).replace(day=1)
            continue
        snap.write("bcra_pagos_minoristas.xlsx", content, source=url, meta={"edition": month.strftime("%Y-%m")})
        print(f"  Pagos minoristas: edición {month:%Y-%m}")
        return
    raise SourceError("No se encontró la planilla de pagos minoristas. Probadas:\n  " + "\n  ".join(tried))


def _find_col(header_row: tuple, label: str) -> int:
    for j, v in enumerate(header_row):
        if v is not None and str(v).strip().startswith(label):
            return j
    raise SourceError(f"Pagos minoristas: no se encontró la columna '{label}'")


def parse(snap: Snapshot) -> pd.DataFrame:
    wb = openpyxl.load_workbook(io.BytesIO(snap.path("bcra_pagos_minoristas.xlsx").read_bytes()),
                                read_only=True, data_only=True)
    sheets = {name: list(wb[name].iter_rows(values_only=True)) for name in {c[0] for c in COLUMNS.values()}}
    frames = []
    for key, (sheet, hrow, label) in COLUMNS.items():
        rows = sheets[sheet]
        j = _find_col(rows[hrow], label)
        data = [(r[0], r[j], r[j + 1]) for r in rows[hrow + 1:] if isinstance(r[0], dt.datetime)]
        df = pd.DataFrame(data, columns=["date", f"{key}_cant", f"{key}_monto"])
        df.index = pd.PeriodIndex(pd.to_datetime(df.pop("date")), freq="M")
        frames.append(df.apply(pd.to_numeric, errors="coerce"))
    return pd.concat(frames, axis=1).sort_index()


WALLET_SHEET = "Cuentas de pago y fondos invert"


def parse_wallets(snap: Snapshot) -> pd.DataFrame:
    """Saldos en cuentas de pago (CVU) y en FCI invertidos a través de PSP (billeteras), en millones de ARS.

    Dos bloques en la hoja: cuentas de pago (fecha fin de mes, cantidad, saldo) y 'Saldos en fondos comunes
    (RI PSPCP)' (fecha inicio de mes, clientes, saldo). Ambos son stocks a fin de mes según la publicación."""
    wb = openpyxl.load_workbook(io.BytesIO(snap.path("bcra_pagos_minoristas.xlsx").read_bytes()),
                                read_only=True, data_only=True)
    rows = list(wb[WALLET_SHEET].iter_rows(values_only=True))
    if not (str(rows[0][1]).startswith("Cuentas de pago") and "fondos comunes" in str(rows[0][5])
            and rows[1][2] == "Saldo" and rows[1][6] == "Saldo"):
        raise SourceError(f"Pagos minoristas: cambió el formato de la hoja '{WALLET_SHEET}': {rows[:2]}")
    cvu, fci = {}, {}
    for r in rows[2:]:
        if isinstance(r[0], dt.datetime) and r[2] is not None:
            cvu[pd.Period(r[0], "M")] = (r[1], r[2])
        if len(r) > 6 and isinstance(r[4], dt.datetime) and r[6] is not None:
            fci[pd.Period(r[4], "M")] = (r[5], r[6])
    out = pd.DataFrame({
        "cvu_saldo": pd.Series({k: v[1] / 1e6 for k, v in cvu.items()}),
        "cvu_cuentas": pd.Series({k: v[0] for k, v in cvu.items()}),
        "fci_psp_saldo": pd.Series({k: v[1] / 1e6 for k, v in fci.items()}),
        "fci_psp_clientes": pd.Series({k: v[0] for k, v in fci.items()}),
    }).astype(float).sort_index()
    out.index = pd.PeriodIndex(out.index, freq="M")
    return out
