# Fase 4: candidatos y pseudo fuera de muestra

Tablas completas en [fase4_tablas.md](fase4_tablas.md); gráfico en [rmse_relativo.png](rmse_relativo.png).

**Corrida.**
- Pronósticos archivados en `data/forecasts/pseudo_oos_2026-10-30_20261031T1606.csv`: 45.729 filas, 3.949 ajustes, 0 fallas.
- 67 orígenes mensuales (feb-21 a ago-26), h = 1–6, escenarios ex ante REM y realizado. Semilla 20261030.
- Pseudo tiempo real: X13 truncado en cada origen. Los pesos de ensamble usan el observado de la vintage de cada origen.
- Protocolo fijado antes de correr ([DECISIONS.md](../../DECISIONS.md)).

Métrica principal: RMSE relativo a la caminata aleatoria (RW) de la misma variable, con escenario REM (< 1 = mejor que la RW).

## 1. Ranking en la muestra de desarrollo (objetivo ≤ oct-25)

| Variable | N (h1/h6) | Mejor modelo (rango medio h1–6) | RMSE rel h1 / h3 / h6 | DM vs RW | F1 mínima (cabecera) | F2 logística |
|---|---|---|---|---|---|---|
| Circulante | 56 / 51 | Ensamble F1, promedio simple | 0,65 / 0,63 / 0,73 | h1 p<0,01; h6 p=0,10 | 0,66 / 0,68 / 0,70 | 0,85 / 1,09 / 1,28 |
| M2 privado | 56 / 51 | F1 con depreciación esperada | 1,01 / 0,88 / 0,87 | n.s. | 1,13 / 1,00 / 0,99 | 1,50 / 1,89 / 2,20 |
| M3 privado | 56 / 51 | F1 con depreciación esperada, móvil 60 | 0,86 / 0,70 / 0,81 | n.s. | 1,01 / 0,90 / 0,98 | 1,28 / 1,56 / 2,09 |
| DAV no remunerados | 9 / 4 | ARIMA | 0,98 / 0,89 / 0,74 | n.s. | 1,01 / 1,17 / 1,54 | 1,37 / 1,63 / 2,91 |
| M2 transaccional | 9 / 4 | Corrección de intercepto k=1 | 1,06 / 0,96 / 1,05 | n.s. | 1,00 / 1,16 / 1,89 | 1,00 / 0,93 / 1,30 |

**Lectura de la muestra de desarrollo:**
- **Circulante (2021–oct-25): los ECM lineales funcionan.** Le ganan a la RW entre 30% y 37% en RMSE, con Diebold-Mariano significativo a h=1. Es el único caso con evidencia clara.
- **M2 privado y M3: mejoras chicas y no significativas.** Lo mejor es la F1 con depreciación esperada (12%–30%).
- **DAV y M2 transaccional: nada distingue modelos de la RW.** La muestra de desarrollo tiene 9 orígenes, 4 a h=6, porque la serie empieza en 2021 y el protocolo pide 48 meses.
- **La F2 logística es la peor familia en todas las variables a h ≥ 3.** Es coherente con que no esté identificada (Fases 2 y 3).
- **Correcciones robustas (intercepto, diferencias, TVP).** Le ganan a la RW en el circulante, pero en desarrollo nunca superan a la F1.
- **Ensambles: los pesos óptimos y el promedio simple casi no difieren.** El ensamble de "todos los modelos" no supera al mejor modelo individual. El ensamble F1 (promedio) es el mejor en circulante.
- **Bandas.** Con incertidumbre solo de shocks, la cobertura del 68% de los ECM queda entre 0,25 y 0,50 y la del 95% entre 0,45 y 0,85. Las bandas son demasiado angostas, como se anticipó (es un piso).

**Ranking reproducible.** Rehaciendo `python -m src.evaluate.oos` y `python -m src.report.fase4` se obtiene la misma tabla: hay semilla fija, snapshot inmutable y archivo de pronósticos fechado.

## 2. Hipótesis 6: agregados (muestra de desarrollo)

| Agregado | Revisión media del equilibrio al sumar 1 mes | Revisión máxima | θ medio (desvío) |
|---|---|---|---|
| M3 privado | **2,1%** | 12,8% | −0,025 (0,038) |
| Circulante | 2,3% | 17,0% | −0,090 (0,048) |
| DAV no remunerados | 4,7% | 14,1% | −0,033 (0,006) |
| M2 transaccional | 7,2% | 25,8% | −0,030 (0,007) |
| M2 privado | 10,9% | 165% | −0,051 (0,069) |

- **El M3 privado tiene la relación de largo plazo más estable y es el único agregado amplio donde un modelo con equilibrio le gana a la RW** (0,70 a h3). Va en la dirección de tu hipótesis.
- **El M2 transaccional tiene una de las relaciones menos estables**: su equilibrio se revisa 7% en promedio por cada mes nuevo. La comparación es imperfecta, porque el M2 transaccional solo tiene 10 orígenes de desarrollo (2025) y el M3 tiene 57.
- **El M2 privado es inestable.** Johansen da vectores erráticos en varios orígenes, lo que explica la revisión máxima de 165%.
- **El M2 ampliado no tiene muestra de desarrollo** (la serie de FCI empieza en ago-23). En el test, ningún modelo le gana a su RW.

## 3. Test: objetivo ≥ nov-25 (reportado al final; no cambia nada de lo anterior)

| Variable | RMSE rel h3 del ganador de desarrollo | Mejor en el test (h3) | RW: RMSE h3 |
|---|---|---|---|
| Circulante | Ensamble F1: **1,42**; F1 mínima: **2,32** | ARIMA 0,73; F2 ~0,9 | 3,0% |
| M2 privado | F1 con depreciación esperada: 1,21 | RW | 3,7% |
| M3 privado | F1 con depreciación esperada, móvil: 2,14 | RW | 1,3% |
| DAV no remunerados | ARIMA: 0,95 | F1 mínima 0,83 | 2,9% |
| M2 transaccional | Corrección de intercepto k=1: 1,12 | RW | 2,5% |

N = 11 por horizonte, con orígenes superpuestos.

**El ranking se invierte.** El modelo que mejor anduvo entre 2021 y oct-25 en circulante (la F1 con equilibrio) es el peor desde nov-25: su error a h=3 es 2,3 veces el de la RW. Lo mismo pasa, con menor intensidad, en M2 privado y M3. Esto es lo que se espera si el equilibrio se desplazó alrededor de fines de 2025 (Fase 3). Un modelo que corrige hacia un equilibrio estimado gana mientras el equilibrio es estable y pierde cuando se mueve.

**En los orígenes de los programas (M2 transaccional, cambio real, escenario REM):**

| Origen → objetivo | Observado | F1 mínima | Corrección k=1 | TVP | RW |
|---|---|---|---|---|---|
| nov-25 → mar-26 | −0,3% | +2,5% | **−0,2%** | +0,3% | 0 |
| abr-26 → jul-26 | −1,8% | −1,2% | −0,8% | +0,1% | 0 |
| jul-26 → sep-26 | +0,2% | +1,2% | −0,7% | +0,1% | 0 |

Las alternativas ganan en un origen y pierden en otro. Ninguna corrección le gana a la RW de forma sistemática en el test.

Nota de medición: con nuestro método, el M2 transaccional en % del PIB **sube** 0,14 pp entre nov-25 y mar-26, mientras el BCRA, en su vintage, muestra una baja de 0,15 pp. El signo del "error" del BCRA en % del PIB depende de la vintage del PIB y de los factores estacionales. Es la misma fragilidad que vimos en la Fase 1.

## Veredicto

1. **Ningún candidato elegido con la información disponible antes de nov-25 habría evitado el error de 2026.** El ganador de desarrollo (F1 / ensamble F1) es justamente el que más falla después. Elegir hoy otro modelo mirando el test sería el sobreajuste que el protocolo prohíbe.
2. **La corrección que "habría fallado menos" en promedio es no corregir hacia el equilibrio:** RW, o ECM con intercepto corregido o TVP cuando la brecha es grande. La evidencia es solo del test (N = 11, 3 programas). No alcanza para declararla ganadora; sí alcanza para no usar la F1 sin un control de estabilidad del equilibrio.
3. **Recomendación operativa para el pipeline mensual (Fase 5)**, que no es una especificación nueva:
   - publicar la RW como benchmark obligatorio junto al ensamble F1;
   - monitorear la revisión mensual del equilibrio (tabla 2) y la brecha ec_t. Si la revisión supera el rango histórico de desarrollo (> 2× la media), marcar el pronóstico de los ECM como no confiable.
4. **Hipótesis 6:** el M3 tiene la relación más estable, pero tampoco escapa al quiebre de 2026. El M2 ampliado no se puede evaluar todavía. Queda abierta; cada mes de la Fase 5 suma una observación para el M2 ampliado.
