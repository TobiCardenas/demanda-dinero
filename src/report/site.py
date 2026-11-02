"""Sitio estático para GitHub Pages: python -m src.report.site [directorio de salida, por defecto _site]

Copia los reportes mensuales (reports/AAAA-MM.html) y arma un índice con el último arriba.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from src.ingest.common import ROOT
from src.report.build_report import CSS

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    reports = sorted((p for p in (ROOT / "reports").glob("*.html") if re.fullmatch(r"\d{4}-\d{2}", p.stem)),
                     reverse=True)
    for p in reports:
        shutil.copy2(p, out / p.name)
    items = "".join(f"<li><a href='{p.name}'>{MONTHS[int(p.stem[5:]) - 1].capitalize()} {p.stem[:4]}</a>"
                    + (" <span class='muted'>(último)</span>" if i == 0 else "") + "</li>"
                    for i, p in enumerate(reports))
    latest = (f"<p><a href='{reports[0].name}'><strong>Ver el último reporte →</strong></a></p>" if reports
              else "<p class='muted'>Todavía no hay reportes.</p>")
    (out / "index.html").write_text(
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Demanda de dinero</title><style>{CSS}</style></head><body><main>"
        "<h1>Demanda real de dinero: reportes mensuales</h1>"
        "<p class='muted'>Pronóstico a 6 meses del M2 transaccional privado y sus componentes, brecha al equilibrio, "
        "errores acumulados y comparación con el último programa del BCRA. Se actualiza el día 18 de cada mes.</p>"
        f"{latest}<h2>Todos los reportes</h2><ul>{items}</ul>"
        "<p class='muted'>Metodología y decisiones: "
        "<a href='https://github.com/TobiCardenas/demanda-dinero/blob/main/DECISIONS.md'>DECISIONS.md</a>.</p>"
        "</main></body></html>", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"))
