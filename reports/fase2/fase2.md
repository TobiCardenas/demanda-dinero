# Fase 2: réplica

Desestacionalización: x13 (pseudo tiempo real, truncada en cada origen). Cabecera: determinantes mínimos, muestra desde 2017 (DAV: desde 2021).

## (a) Gráfico 1: circulante real s.e. a dic-2025 (miles de millones de $ de dic-2016)

| | F1 lineal | F2 no lineal | Observado | Brecha (F1−F2)/obs |
|---|---|---|---|---|
| BCRA (lectura a ojo, $ de 2016) | 275 | 226 | 228 | 21.5% |
| Réplica, cabecera | 276.9 | 279.6 | 223.5 | -1.2% |
| Réplica, promedio de variantes | 239.9 | 238.7 | 223.5 | 0.5% |

- ¿F2 más cerca del observado? Cabecera: no; promedio de variantes: sí.
- **Criterio (a): NO CUMPLE** (F2 más cerca y brecha entre 10% y 40%).

## (b) Programa dic-2025: M2 transaccional, cambio en pp del PIB respecto de nov-25

Nivel en el origen: réplica 5.60% contra BCRA 5,80%.

|                                           |   2025-12 |   2026-01 |   2026-02 |   2026-03 |
|:------------------------------------------|----------:|----------:|----------:|----------:|
| F1_vecm componentes (cabecera)            |     0.064 |     0.13  |     0.193 |     0.249 |
| F1_vecm agregado (cabecera)               |     0.004 |     0.03  |     0.058 |     0.078 |
| F1_vecm componentes (prom. variantes)     |     0.05  |     0.079 |     0.1   |     0.11  |
| F2_logistic componentes (cabecera)        |    -0.029 |    -0.078 |    -0.142 |    -0.223 |
| F2_logistic agregado (cabecera)           |    -0.054 |    -0.074 |    -0.082 |    -0.088 |
| F2_logistic componentes (prom. variantes) |    -0.032 |    -0.084 |    -0.148 |    -0.225 |

BCRA base: dic-25 +0.03, mar-26 +0.23.

- **Criterio (b): CUMPLE** (suba dic→mar: sí; mar-26 a ±0,1 pp del BCRA: sí; réplica F1 +0.249 contra BCRA +0.23).

Supuestos del escenario REM:

- co: rate_pf30 = REM Tasa de interés (TAMAR) x (rate_pf30 / rate_tamar en el origen = 0.928)
- alt: sin pronóstico REM; se extrapola el cambio medio de 12 meses (+0.0086 log/mes)
