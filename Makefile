.PHONY: monthly report test ingest

# Corrida mensual completa: ingesta -> ... -> reports/<YYYY-MM>.html
monthly:
	uv run python -m src.run_monthly

# Regenera el reporte del último snapshot sin reestimar
report:
	uv run python -m src.report.build_report

test:
	uv run pytest -q

ingest:
	uv run python -m src.ingest.run
