# Revisión del modelo titular

Protocolo fijado antes de calcular (DECISIONS.md, 2026-11-18). RMSE relativo a «igual que hoy» (< 1 = mejor), escenario REM, filas donde existen todos los candidatos.

## Muestra de desarrollo (objetivo ≤ oct-25): decide

|    |   criterio (prom. variables y h) |   peor variable |   m2 (prom. h) |   circ (prom. h) |   dav (prom. h) | descripción             |
|:---|---------------------------------:|----------------:|---------------:|-----------------:|----------------:|:------------------------|
| R0 |                            1.028 |           1.306 |          1.306 |            0.644 |           1.136 | ensamble F1 (actual)    |
| R1 |                            1     |           1     |          1     |            1     |           1     | igual que hoy (RW)      |
| R2 |                            1.047 |           1.306 |          1.306 |            0.675 |           1.159 | semáforo en tiempo real |
| R3 |                            1.256 |           1.661 |          1.661 |            0.687 |           1.42  | ensamble de todos       |
| R4 |                            0.984 |           1.139 |          1.139 |            0.756 |           1.059 | 50/50 ensamble F1 y RW  |
| R5 |                            1.051 |           1.298 |          1.298 |            0.711 |           1.144 | pesos inversos al ECM   |

**Elegido por la regla: R1 — igual que hoy (RW).**

N por variable y horizonte (desarrollo):

| variable   |   1 |   2 |   3 |   4 |   5 |   6 |
|:-----------|----:|----:|----:|----:|----:|----:|
| circ       |  53 |  52 |  51 |  50 |  49 |  48 |
| dav        |   6 |   5 |   4 |   3 |   2 |   1 |
| m2         |   6 |   5 |   4 |   3 |   2 |   1 |

## Test (objetivo ≥ nov-25): se reporta, no decide

|    |   criterio (prom. variables y h) |   peor variable |   m2 (prom. h) |   circ (prom. h) |   dav (prom. h) | descripción             |
|:---|---------------------------------:|----------------:|---------------:|-----------------:|----------------:|:------------------------|
| R0 |                            1.23  |           1.426 |          1.186 |            1.426 |           1.077 | ensamble F1 (actual)    |
| R1 |                            1     |           1     |          1     |            1     |           1     | igual que hoy (RW)      |
| R2 |                            1.183 |           1.438 |          1     |            1.438 |           1.109 | semáforo en tiempo real |
| R3 |                            1.272 |           1.346 |          1.346 |            1.343 |           1.128 | ensamble de todos       |
| R4 |                            1.09  |           1.168 |          1.078 |            1.168 |           1.024 | 50/50 ensamble F1 y RW  |
| R5 |                            1.108 |           1.238 |          1.06  |            1.238 |           1.028 | pesos inversos al ECM   |

N (test):

| variable   |   1 |   2 |   3 |   4 |   5 |   6 |
|:-----------|----:|----:|----:|----:|----:|----:|
| circ       |  11 |  12 |  12 |  12 |  12 |  12 |
| dav        |  11 |  12 |  12 |  12 |  12 |  12 |
| m2         |  11 |  12 |  12 |  12 |  12 |  12 |

## Cuándo la regla R2 (semáforo) habría pasado a «igual que hoy»

- m2: 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04, 2026-05, 2026-06, 2026-07, 2026-08
- circ: 2022-02, 2022-03, 2022-04, 2022-05, 2022-06, 2026-02, 2026-03, 2026-04, 2026-05, 2026-06, 2026-07, 2026-08
- dav: 2025-07, 2025-08, 2025-09
