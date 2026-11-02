# Decisiones de especificación

Cada entrada: fecha, decisión, motivo. Si una decisión se tomó mirando los orígenes del BCRA de 2026, se indica.

## 2026-10-30 · Fase 0

**Ubicación y entorno.** Repo nuevo en `projects/demanda-dinero` (la carpeta original era una extensión de Chrome sin relación). Python 3.13 con `uv` 0.13.6 y dependencias bloqueadas en `uv.lock`. X-13ARIMA-SEATS b62 (Census, build Windows ascii) en `tools/x13/`. Corre emulado en ARM64 y se verificó con datos simulados.

**Depreciación esperada: REM, no futuros.** No hay acceso programático a A3 Mercados (respuesta del usuario). Se usa la mediana del REM; `src/ingest/futuros.py` deja el hueco explícito.

**Definición de M2 privado transaccional.** Se toma del glosario del IMM de jul-2026: circulante en poder del público + cheques cancelatorios en pesos + depósitos a la vista no remunerados en pesos del sector privado no financiero. Se usa la serie BCRA 197 (Series.xlsm).

**DAV no remunerados = 197 − 67 − 69**, calculado con datos diarios antes de promediar. No existe una serie publicada de DAV no remunerados.

**Ids 67/69 y no 60/62.** En Series.xlsm los ids 60–66 son variaciones diarias y los 67–73 son saldos, con la misma descripción en el catálogo. La primera corrida usó 60/62 por error y la validación lo detectó (circulante negativo). Esos archivos siguen en el snapshot 2026-10-30 como evidencia y no se usan. El id 67 coincide con el 17 (Principales Variables) hasta el redondeo.

**El M2 transaccional existe solo desde ene-2021.** La variante de muestra "desde 2017" no es posible para DAV no remunerados ni para el agregado sin reconstruir la serie hacia atrás. M2 transaccional / M2 privado pasa de 0,897 (ene-21) a 0,827 (oct-26). **PENDIENTE de decisión del usuario** (ver resumen de Fase 0). El circulante sí está desde 2016.

**IPC.** La fuente primaria es el CSV de INDEC (`serie_ipc_divisiones.csv`, Codigo 0, Nacional), que llega a sep-26. datos.gob.ar va un mes atrasado. El núcleo sale de datos.gob.ar porque INDEC no publica un CSV propio. Base dic-2016 = 100, sin empalme hacia atrás: las muestras arrancan en 2017.

**EMAE.** La fuente primaria es el xls de INDEC (llega a ago-26). datos.gob.ar va un mes atrasado y queda solo como control cruzado.

**PIB s.e.** Se usa `3.2_OGP_D_2004_T_17`. La API lo describe como "Oferta global total", pero en el CSV fuente es la columna `oferta_global_pib`.

**Agregación mensual: promedio de días hábiles.** Se anulan el mes del snapshot y todo mes cuyo último dato quede a más de 4 días del fin de mes.

**Dummies de quiebre candidatas** (en `settings.yaml`): ASPO 2020-03/06, salto cambiario dic-2023 y salida del cepo abr-2025. Se definieron antes de producir cualquier pronóstico. Su uso en cada modelo se decide en la Fase 2.

**Tolerancias de validación.** El salto máximo entre días hábiles es de 7 días (Semana Santa 2024). Dos discrepancias viejas entre canales de publicación quedan como aviso y no como error: IPC abr-2019 (INDEC 213,05 contra datos.gob.ar 212,96) y la inflación del BCRA de ene/feb-2017 (otro índice). En los últimos 24 meses el control es estricto.

**No se ingesta la caución.** No está en la API del BCRA y era solo una alternativa.

## 2026-10-30 · Fase 1

**Convenciones de evaluación de los pronósticos publicados.**
- σ implícito = semiancho de la banda del 68%; si falta, banda del 95% / 1,96. Supone normalidad.
- Caminata aleatoria = valor del origen en la misma vintage.
- Cada fila se evalúa contra el observado de su propia vintage.
- El error de lectura se modela como uniforme ±0,02 pp e independiente entre valores leídos (20.000 sorteos, semilla 20261030).

Estas convenciones se fijaron antes de ver los resultados y no dependen de ellos.

### Hallazgo: el ajuste estacional no reproduce al BCRA
X13 automático (log, outliers) sobre el M2 transaccional real 2021-01..2026-09 da −0,55% m/m s.e. en jul-26. El IMM de jul-2026 publica +1,8%. Sin desestacionalizar, la variación real de julio fue +4,69%, similar a julios previos (2021: +4,9%; 2025: +4,9%). La diferencia está en el factor estacional de julio: el nuestro salta ~5,3% contra ~2,9% implícito en el BCRA. No es un error de datos, pero condiciona toda comparación en % del PIB s.e. y en niveles s.e. contra el BCRA. Hay que tratarlo en la Fase 1–2 sin calibrar mirando 2026.

## 2026-10-30 · Fase 2

Decisiones del usuario: `alt` = montos (push + pagos con transferencia) sobre EMAE × IPC. Para los DAV y el M2 transaccional, las muestras arrancan en 2021 (sin reconstrucción hacia atrás).

Las siguientes decisiones se fijaron **antes** de producir pronósticos:
- **`alt`.** Las push excluyen los pagos con transferencia (nota 2 del informe de pagos minoristas), así que sumarlas no duplica. Antes del QR interoperable (fines de 2021), la serie de pagos con transferencia consolida el "Pago Electrónico Inmediato": hay un cambio de cobertura. Se desestacionaliza con X13 truncado y se estandariza con la media y el desvío de la muestra hasta el origen.
- **Dummies: impulsos solo en la dinámica de corto plazo** (ASPO 2020-03/06, devaluación 2023-12/2024-01, salida del cepo 2025-04). Un escalón en el largo plazo es la hipótesis de equilibrio desplazado: es candidata para las fases 3-4, no se impone acá.
- **Constante restringida al largo plazo (b0 = 0).** b0 y a0 no se identifican por separado. La Familia 1 usa Johansen con `deterministic="ci"`.
- **Familia 1: vector de Johansen con rango 1 impuesto**, más una ECM uniecuacional condicional en act y co (corrientes y p rezagos) estimada por MCO. El rezago sale del AIC del VAR [y, act, co] (máx. 4). La muestra efectiva arranca siempre en p_max + 1, para que no dependa del rezago elegido.
- **Familia 2: MCNL concentrado.** Dados (θ_alt, λ), la ec. 2 es lineal. Se usa una grilla de 17 θ (P10–P90) × 10 λ (0,5 a 20) y después Nelder-Mead acotado: θ dentro del rango de alt, λ en [0,1; 50].
- **Bootstrap de residuos con reestimación**, regresores dados. En la F2, cada simulación reoptimiza localmente desde el estimador puntual.
- **Base = trayectoria central determinística** (shocks nulos). La mediana del bootstrap se reporta aparte. Motivo: los criterios no deben depender del ruido de simulación.
- **Variante de cabecera**: determinantes mínimos, muestra desde 2017 (DAV y M2: desde 2021). Todas las demás se reportan.
- **Escenario REM (test b).**
  - Inflación: la mensual del REM.
  - co: plazo fijo = TAMAR del REM × (plazo fijo / TAMAR en el origen).
  - Actividad: PIB trimestral s.e. del REM, repartido geométricamente en los meses.
  - alt: sin pronóstico, se extrapola el cambio medio de 12 meses.
  - Depreciación esperada: trayectoria de tipo de cambio del REM.
- **Escenario realizado.** Los cambios de los regresores desestacionalizados con la última vintage se aplican al nivel truncado del origen.
- **Pseudo tiempo real sin rezagos de publicación.** Se usan todos los datos con fecha ≤ origen, incluido el EMAE, que en tiempo real llega ~50 días tarde. Eso favorece levemente a los modelos.
- **% del PIB.** Los trimestrales nominales de INDEC están anualizados (promedio de 2025 = PIB anual). Método en `src/transform/ratios.py`. Solo se usan trimestres cerrados ≤ origen.

### Diagnóstico de la Fase 2 (mirando el Gráfico 1 y el programa dic-25; ninguna alternativa se adoptó)
`reports/fase2/diagnostico.md` cambia un supuesto por vez: alt (cantidades, montos + débito), co (BADLAR, inflación esperada del REM) y deflactor núcleo. Con la variante de cabecera y pronósticos puntuales:
- **La F2 no se identifica con datos hasta dic-2024 bajo ningún supuesto.** El óptimo cae en el borde de la grilla (θ_alt en el máximo o mínimo de alt, λ en el mínimo) y el perfil en θ es plano (rango relativo de la SCR 0,4–2,5%). Con λ chico, w es casi lineal en alt y la F2 colapsa a la F1: la brecha F1−F2 a dic-25 queda entre −1,4% y +1,7%, contra 21% del BCRA.
- **La F1 lineal reproduce el nivel del BCRA**: 276,9 contra ~275, con observado 223,5 contra ~228.
- **La elasticidad ingreso de la F1 es negativa** (−0,32) en la cabecera. Solo con el deflactor núcleo es positiva (+0,10).
- **(b) La F1 de cabecera reproduce el programa**: +0,064 pp a dic-25 y +0,249 pp a mar-26, contra +0,03 y +0,23 del BCRA. El circulante real sube 9,3% y los DAV 3,0%. La F2 da −0,22 pp: dirección opuesta.

## 2026-10-30 · Fase 3

- **Corrección de intercepto.** El equilibrio estimado se desplaza en la brecha promedio de los últimos k meses (k ∈ {1, 3}). Con k=1 la brecha en el origen queda en cero. Es la interpretación de "ec se reinicia al desvío observado promedio". En el bootstrap el desplazamiento se recalcula con los parámetros reestimados.
- **ECM en diferencias.** Misma dinámica de corto plazo con θ = 0, reestimada.
- **Revisión.** Hay un solo snapshot, así que la "vintage contemporánea" se aproxima con X13 sobre la serie truncada en el mes objetivo. Capta solo revisiones de factores estacionales.
- **Horizonte del escenario realizado: hasta ago-26.** El EMAE de sep-26 no está publicado. La descomposición del programa de jul-26 se hace a h=1.
- **Atribución del escenario.** Se cambia un regresor por vez (REM en lugar de realizado) con el resto realizado. Las contribuciones suman el total porque el modelo es casi lineal en los regresores.
- **Advertencia de sobreajuste.** La Fase 3 miró los orígenes de 2026 por diseño. Ninguna especificación de la Fase 4 puede elegirse por estos resultados; si alguna coincide con lo que ganó acá, hay que justificarla con el pseudo fuera de muestra previo a nov-25.

## 2026-10-30 · Hipótesis 6: cambio estructural en el agregado (propuesta del usuario)

**Hipótesis.** Con el auge de las billeteras virtuales, una parte creciente de los saldos transaccionales se guarda en instrumentos remunerados que el M2 transaccional excluye por definición: FCI money market a través de billeteras, cuentas remuneradas. Si es así, la "caída de demanda" de 2025–26 es en parte un problema de cobertura de la variable y no de demanda.

**Evidencia descriptiva previa a cualquier modelo** (chequeo exploratorio, no está en el pipeline):
- Los saldos en FCI a través de billeteras (hoja "Cuentas de pago y fondos invert" del informe de pagos minoristas) pasan de 3,5% a 13,9% del M2 transaccional entre ago-23 y ago-26. En términos reales se multiplican por 3,4.
- Los depósitos a la vista remunerados dentro del M2 privado caen en términos reales desde 2024.

**Compromiso previo (fijado antes de estimar modelos con estos agregados).** La Fase 4 compara cuatro variables dependientes con los mismos modelos y el mismo protocolo:
1. M2 transaccional (el del BCRA): componentes y agregado.
2. M2 privado = circulante + cheques + cuentas corrientes + cajas de ahorro privadas en pesos.
3. M3 privado = circulante + cheques + depósitos privados en pesos (definición del glosario del IMM).
4. M2 ampliado = M2 transaccional + saldos en FCI a través de billeteras.
   - La serie de FCI arranca en ago-2023, así que no admite estimar una relación de largo plazo propia ni X13 propio para los orígenes anteriores a mediados de 2026. Se desestacionaliza solo el M2 transaccional y se suman los FCI sin ajuste.
   - Es un stock a fin de mes; el M2 es un promedio mensual de saldos diarios. La inconsistencia se documenta y no se corrige.
   - Puede haber doble conteo si los FCI depositan en cuentas remuneradas que el BCRA clasifica como sector privado no financiero (no verificado). El M2 transaccional las excluye, así que el doble conteo sería con el M2 privado, no con el M2 ampliado.

Criterios de comparación, fijados ahora:
- estabilidad recursiva de la relación de largo plazo: deriva del equilibrio estimado para un mes fijo y deriva de θ;
- error fuera de muestra con origen móvil **hasta oct-25**.

Los orígenes nov-25, abr-26 y jul-26 se reportan aparte y no deciden. Para el M2 ampliado solo es posible la comparación descriptiva y la de modelos sin largo plazo (en diferencias, caminata aleatoria), por la longitud de la serie.

**Implementación (2026-10-30).**
- Se ingestan los ids 96, 97, 98 (depósitos privados en pesos) y, solo como control, el 104 y el 106. Los dos tienen la misma descripción en el catálogo, pero el 104 son los depósitos en dólares valuados en pesos y el 106 el total. La identidad 94+95+96+97+98 = 106 − 104 se valida a diario.
- Los saldos de FCI vía billeteras y de cuentas de pago salen de la hoja "Cuentas de pago y fondos invert" de la planilla de pagos minoristas (ya estaba en el snapshot).
- Los datos de modelado incorporan `y_m2priv`, `y_m3` (X13 propio) y `y_m2amp` (M2 transaccional s.e. + FCI reales sin ajustar).
- **Lectura descriptiva** (`reports/hipotesis6/`, sin modelos). Entre nov-25 y ago-26, en términos reales s.e.: M2 transaccional −3,9%, M2 ampliado −1,7%, M3 privado −1,7%, M2 privado −7,8%, EMAE −0,6%. Los agregados que incluyen instrumentos remunerados fuera del M2 caen menos. El M2 privado cae más, porque los DAV remunerados se achican. No se adoptó ninguna especificación a partir de esto.

## 2026-10-30 · Fase 4: protocolo (fijado antes de correr)

**Orígenes y muestras.**
- Origen móvil mensual desde el primer mes con ≥ 48 meses de muestra efectiva hasta jul-26: circulante, M2 privado y M3 privado desde 2021-02; DAV y M2 transaccional desde 2025-01.
- Horizontes 1–6. Pseudo tiempo real: datos actuales truncados y X13 sobre la serie truncada en cada origen.
- **Muestra de desarrollo:** pronósticos con mes objetivo ≤ oct-25. Ranking, selección y pesos de ensamble usan solo esta muestra.
- **Test:** los orígenes de los programas (nov-25, abr-26, jul-26), más todos los pronósticos con objetivo ≥ nov-25. Se reportan al final y no deciden nada.
- La consecuencia de esto: para los DAV y el M2 transaccional, la muestra de desarrollo tiene orígenes ene–sep-25 solamente (N chico, se reporta).

**Escenarios.**
- Primario: **ex ante REM**, el pronóstico que se habría publicado.
- Secundario: realizado (error de modelo puro). Llega hasta ago-26, que es el último EMAE publicado.

**Modelos por variable.**
- F1 VECM {mínimo, depreciación esperada, alt lineal} × muestras {larga, móvil de 60 meses}. Las muestras son 2017 para circulante, M2 privado y M3, y 2021 para DAV y M2. Para DAV y M2 la móvil coincide con la larga hasta 2026, así que se usa solo la larga.
- F2 logística {mínimo, depreciación esperada} × las mismas muestras.
- Corrección de intercepto k=1 y k=3 sobre la F1 mínima, y ECM en diferencias.
- **TVP:** `UnobservedComponents` con nivel como caminata aleatoria, exógenas act y co, y AR(1) en el error. Es "la relación de largo plazo con intercepto como caminata aleatoria".
- Benchmarks: caminata aleatoria, caminata con drift de 12 meses, ARIMA(p,1,q) con p, q ≤ 2 y drift elegido por AIC.
- M2 ampliado: solo caminata, caminata con drift, ARIMA y ECM en diferencias, en orígenes con ≥ 24 meses de serie. Por construcción no tiene muestra de desarrollo: es descriptivo.

**Bandas en el origen móvil: solo shocks** (bootstrap de residuos con parámetros fijos, 200 simulaciones). La reestimación por simulación de la F2 es inviable en costo de cómputo. Las bandas quedan más angostas que con incertidumbre paramétrica, y la cobertura medida es un piso.

**Ensambles.**
- Grupos: F1 (sus variantes), F2 (sus variantes) y "todos" (ECM, robustos y benchmarks).
- En cada origen se eligen dentro del grupo los 3 modelos de menor ECM (error cuadrático medio) a h=1–3 sobre los pronósticos con objetivo en los 12 meses previos al origen. El escenario de evaluación es el mismo que el del pronóstico.
- Dos esquemas, que se reportan ambos sin elegir:
  - pesos ≥ 0 que suman 1 y minimizan ese ECM (réplica de la nota 48);
  - promedio simple de los 3.
- Los cuantiles se combinan con los mismos pesos.

**Métricas por h.**
- MAE y RMSE relativos a la caminata aleatoria.
- Acierto direccional del cambio respecto del origen.
- Cobertura del 68% y del 95%.
- PIT y CRPS, suponiendo normal con μ = q0,5 y σ = (q0,84 − q0,16)/2.
- Diebold-Mariano con corrección de Harvey-Leybourne-Newbold contra la caminata aleatoria, con pérdida cuadrática.
- Siempre con N.

**Agregados (hipótesis 6).**
- Estabilidad: revisión media absoluta del equilibrio del mes anterior al sumar una observación, |y_lp,o(o−1) − y_lp,o−1(o−1)|, y desvío de θ entre orígenes (F1 mínima, muestra de desarrollo).
- Error relativo a la caminata aleatoria de cada agregado.

## 2026-11-02 · Fase 4: ejecución y resultados

- **Implementación.**
  - Con parámetros fijos, la simulación de bandas se vectorizó (`_paths_fixed`). Tiene un test de igualdad exacta contra el bucle original, y el método no cambia.
  - El runner guarda un checkpoint por origen (`--resume`), porque dos sesiones se cortaron a mitad de corrida.
  - BLAS a 1 hilo por proceso.
- **Mínimo de 48 observaciones para X13 en `model_data.build`.** Con 36, X13 falla en DAV y M2 en los orígenes de 2024. No afecta a ningún pronóstico evaluado: esas variables arrancan en ene-25 por protocolo.
- **Archivo.** `data/forecasts/pseudo_oos_2026-10-30_20261031T1606.csv` (+ `_estabilidad`, `_fallas` vacío). Pseudo-vintages en `data/processed/pseudo_vintages.csv`.
- **Resultado** (reports/fase4/fase4.md).
  - En desarrollo (objetivo ≤ oct-25), la F1 y el ensamble F1 dominan en circulante (RMSE rel ≈ 0,65, DM p<0,01 a h1). La F2 es la peor familia.
  - En el test (≥ nov-25) el ranking se invierte y la RW o el ARIMA ganan.
  - **No se adopta ninguna especificación a partir del test.** La recomendación para la Fase 5 es de monitoreo (RW obligatoria y alarma de inestabilidad del equilibrio), no un cambio de modelo.
- **Error mío corregido antes de publicar.** La tabla de orígenes del BCRA tenía una columna "pp PIB pronosticado" que restaba el ratio de la RW en el mes objetivo en lugar del ratio en el origen. Se eliminó; el cálculo correcto en % del PIB queda para el reporte mensual.

## 2026-11-02 · Fase 5: pipeline mensual (decisiones previas a la primera corrida en tiempo real)

- **Origen en tiempo real** = último mes con dinero (promedio mensual completo) e IPC publicados. Con la corrida el día 18, eso suele ser el mes anterior.
- **Relleno de regresores (marcado en el reporte).** El EMAE llega 1–2 meses después del origen. La actividad faltante se completa con el PIB trimestral s.e. del REM más reciente relevado hasta el origen, repartido geométricamente en los meses. Si a `alt` le falta EMAE o pagos, se completa con su cambio medio de 12 meses. Es la misma regla que ya usa el escenario REM. Cada mes completado así figura en el reporte y en el archivo (`act_filled`).
- **Modelos y escenarios.** Los mismos de la Fase 4 (`oos.model_specs`): bandas de solo shocks, escenarios ex ante REM y realizado (el realizado solo si hay EMAE posterior al origen). Ensambles con el protocolo de la Fase 4, usando como errores pasados todo el archivo (pseudo y tiempo real) con objetivo en los 12 meses previos.
- **Archivo.** Cada corrida escribe `data/forecasts/realtime_<fecha>.csv` en un archivo nuevo, con `realtime=true`; si ya existe, falla. Las corridas de una misma fecha reusan el snapshot del día.
- **Frescura.** La corrida falla si una fuente tiene más rezago que el admitido (`settings.yaml: freshness`). No sigue con datos viejos sin avisar.
- **Alarma de inestabilidad.** Se marca cuando la revisión del equilibrio del mes anterior supera 2 veces la media de desarrollo de la Fase 4 para esa variable, o cuando θ ≥ 0.
- **Benchmark obligatorio.** La caminata aleatoria se publica siempre al lado del ensamble F1 (recomendación de la Fase 4).

**Implementación de la Fase 5 (2026-11-02).**
- **Primera corrida en tiempo real:** snapshot 2026-11-02, origen sep-26 (actividad de sep-26 completada con el REM de sep-26), 630 pronósticos en `data/forecasts/realtime_2026-11-02.csv`. Reporte en `reports/2026-11.html`.
- **Ensambles de la Fase 4 archivados** en un archivo nuevo, `pseudo_oos_..._ensambles.csv` (antes estaban solo en `reports/fase4/`), para que el reporte muestre el historial del modelo de cabecera.
- **X13 en Linux.** `X13_BINARY` sobrescribe la ruta de `settings.yaml`. El workflow instala el binario b62 de Census para Linux (`x13as_ascii`).
- **Segunda corrida el mismo día:** falla con código 1 sin escribir nada. El reporte se puede regenerar desde el contexto guardado con `python -m src.report.build_report`.
- **Umbral de la alarma del M2 privado.** Queda alto (21,8%) porque la media de revisiones de desarrollo incluye un vector de Johansen errático (revisión máxima de 165%). No se corrige: es la regla fijada antes de correr.
