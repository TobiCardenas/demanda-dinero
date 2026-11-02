# Demanda real de dinero: réplica del modelo BCRA

Réplica de la arquitectura del Apartado técnico 5 del IPOM de dic-2025 (VECM y ECM logística por componentes), evaluación de los pronósticos de 2026 y pipeline mensual.

## Corrida mensual

```bash
make monthly   # o: uv run python -m src.run_monthly
```

Ejecuta ingesta → snapshot → panel y validación → control de frescura → estimación en el origen de tiempo real → pronósticos (ex ante REM y realizado) → ensambles → archivo → evaluación de todo el archivo → `reports/<YYYY-MM>.html`. Si una fuente falla, no valida o está atrasada más de lo admitido (`settings.yaml: freshness`), la corrida termina con código 1. El workflow `.github/workflows/monthly.yml` la corre el día 18 de cada mes, guarda snapshot, pronósticos y reporte en el repo y abre un issue si falla.

**Ver los reportes:** https://tobicardenas.github.io/demanda-dinero/ (índice con el último arriba; lo publica `.github/workflows/pages.yml`). Cada mes, después de publicar, el workflow abre un issue "Reporte de demanda de dinero AAAA-MM disponible" con el resumen (`reports/AAAA-MM_resumen.md`) y el enlace; GitHub lo avisa por email.

## Uso por fase

```bash
uv sync
uv run python -m src.ingest.run          # snapshot inmutable en data/raw/<hoy>/
uv run python -m src.transform.panel     # paneles en data/processed/
uv run python -m src.transform.validate  # falla ante huecos, unidades o discrepancias; reports/fase0/validacion.md
uv run python -m src.report.fase0_plots  # un gráfico por serie en reports/fase0/
uv run python -m src.evaluate.published  # Fase 1
uv run python -m src.report.fase2        # Fase 2 (+ src.report.fase2_diag)
uv run python -m src.report.fase3        # Fase 3
uv run python -m src.report.hipotesis6   # agregados alternativos, descriptivo
uv run python -m src.evaluate.oos        # Fase 4: origen móvil (--workers N, --resume <dir>)
uv run python -m src.evaluate.vintages   # pseudo-vintages s.e. por origen
uv run python -m src.report.fase4        # Fase 4: ranking, agregados y test
uv run pytest
```

`python -m src.ingest.run --amend` agrega al snapshot del día las series del BCRA que falten (por ejemplo, después de corregir un id). Nunca reescribe archivos existentes.

El binario X-13 (`tools/x13/`) no está versionado. Se baja de census.gov (x13as_ascii-v1-1-b62.zip) y la ruta se fija en `config/settings.yaml`.

## Estructura

- `config/series.yaml`: ids verificados de cada serie, con su fuente y la fecha de verificación.
- `config/settings.yaml`: decisiones de modelado (componentes, deflactor, costo de oportunidad, dummies, semillas).
- `DECISIONS.md`: registro de decisiones y hallazgos.
- `data/bcra_forecasts.csv`: pronósticos publicados por el BCRA, leídos a ojo; hay que redigitalizarlos.
