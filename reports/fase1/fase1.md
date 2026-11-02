# Fase 1: pronósticos publicados del BCRA

M2 privado transaccional, % del PIB s.e. Cada fila se compara con el observado de su propia vintage.
Caminata aleatoria (CA) = valor del origen en esa vintage. σ implícito = semiancho de la banda del 68%.
Las columnas P(·) incorporan error de lectura uniforme de ±0,02 pp en cada valor leído.

## Por pronóstico

| vintage | origen | destino | h | p50 | obs | error | error CA | z | en 68% | en 95% | dir. BCRA / obs | P(CA mejor) | P(fuera 95%) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ipom_2026Q1 | 2025-11 | 2025-12 | 1 | 5.830 | 5.800 | -0.030 | +0.000 | – | – | – | ↑ / = | 0.82 | – |
| ipom_2026Q1 | 2025-11 | 2026-03 | 4 | 6.030 | 5.650 | -0.380 | -0.150 | -2.00 | no | sí | ↑ / ↓ | 1.00 | 0.49 |
| prog_abr26 | 2026-04 | 2026-05 | 1 | 5.430 | 5.500 | +0.070 | +0.020 | +1.00 | sí | sí | ↓ / ↑ | 1.00 | 0.00 |
| prog_abr26 | 2026-04 | 2026-06 | 2 | 5.400 | 5.525 | +0.125 | +0.045 | +1.09 | no | sí | ↓ / ↑ | 1.00 | 0.00 |
| prog_abr26 | 2026-04 | 2026-07 | 3 | 5.390 | 5.600 | +0.210 | +0.120 | +1.29 | no | sí | ↓ / ↑ | 1.00 | 0.00 |
| prog_jul26 | 2026-07 | 2026-08 | 1 | 5.800 | 5.735 | -0.065 | -0.025 | -0.93 | sí | sí | ↑ / ↓ | 1.00 | 0.00 |
| prog_jul26 | 2026-07 | 2026-09 | 2 | 5.855 | 5.750 | -0.105 | -0.010 | -0.84 | sí | sí | ↑ / ↓ | 1.00 | 0.00 |

## Por vintage

| vintage | origen | N | h máx | MAE | MAE CA | RMSE rel. CA | error h máx | error CA h máx | z h máx | dirección opuesta h máx | P(CA mejor) h máx |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ipom_2026Q1 | 2025-11 | 2 | 4 | 0.205 | 0.075 | 2.54 | -0.380 | -0.150 | -2.00 | sí | 1.00 |
| prog_abr26 | 2026-04 | 3 | 3 | 0.135 | 0.062 | 1.96 | +0.210 | +0.120 | +1.29 | sí | 1.00 |
| prog_jul26 | 2026-07 | 2 | 2 | 0.085 | 0.017 | 4.59 | -0.105 | -0.010 | -0.84 | sí | 1.00 |

## Lectura

- En el horizonte máximo, la CA tuvo menor error absoluto en 3 de 3 vintages. Test de signo unilateral (H0: 50%): p = 0.125. Con N = 3 vintages independientes, el test no puede rechazar al 5% aunque la CA gane en todos.
- Dirección opuesta a la base en el horizonte máximo: 3 de 3 vintages.
- Cobertura observada: 68% → 3/6; 95% → 6/6. Las filas de una misma vintage no son independientes.
- Sesgo: el error medio es -0.025 pp, con 3 filas de 7 con error positivo.

## Revisiones entre vintages (mismo mes, distinto gráfico)

| mes | vintage A | valor A | vintage B | valor B | B − A |
|---|---|---|---|---|---|
| 2026-07 | prog_abr26 | 5.600 | prog_jul26 | 5.760 | +0.160 |

Una revisión de este tamaño se compara directamente con los errores de pronóstico de arriba.
