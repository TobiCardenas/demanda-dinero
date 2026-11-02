# Fase 3: por qué falló el modelo en 2026

Tablas completas en [fase3_tablas.md](fase3_tablas.md). Gráficos: [ec_equilibrio_recursivo.png](ec_equilibrio_recursivo.png), [descomposicion.png](descomposicion.png), [modelos_m2.png](modelos_m2.png).

**Qué se evalúa.** La réplica es la F1 (VECM) de cabecera de la Fase 2, que reprodujo el programa de dic-25. Los errores se miden en % (log de saldos reales s.e.), con signo pronóstico − observado. Las horizontes son los de cada programa: nov-25 → mar-26, abr-26 → jul-26 y jul-26 → ago-26. Para el programa de julio se usa h=1 y no h=2, porque el EMAE de sep-26 no está publicado.

## Veredicto

**La hipótesis mejor sostenida es la principal: el equilibrio de largo plazo está mal ubicado y se reestima en exceso. La confianza es moderada para el circulante y baja para los DAV y para el agregado.** Hay que tener en cuenta que el modelo evaluado es nuestra réplica, no el del BCRA, y que hay solo tres orígenes con horizontes que se superponen.

## Evidencia por hipótesis

### 1. Equilibrio desplazado o mal estimado: sostenida
- **El circulante vive lejos de su "equilibrio" y no converge.** La brecha estimada en tiempo pseudo-real está entre −40% y −90% en todo 2024–2026, y en los tres orígenes vale −45%, −44% y −57%. Un equilibrio bien ubicado con velocidad de ajuste negativa no es compatible con una brecha de ese tamaño que dura más de dos años.
- **El propio dato deja de pedir corrección.** La velocidad de ajuste θ del circulante cae de −0,045 (jun-24) a −0,009 (ago-26). El modelo "aprende" que la brecha no se cierra, pero sigue empujando hacia un nivel que el circulante no alcanza.
- **El equilibrio se reestima en exceso, y siempre hacia abajo.** El nivel de equilibrio del circulante para un mismo mes, nov-25, baja 24% entre la estimación de nov-25 y la de ago-26 (12,771 → 12,531 en log). Cada reestimación persigue al dato sin alcanzarlo.
- **Sin el tirón al equilibrio se erra menos.** Con escenario realizado y error en cambios, la corrección de intercepto (k=1) baja el error del circulante de 11,2% a 5,2% en nov-25 y de 6,3% a 2,8% en abr-26. Para el M2 baja de 4,5% a 0,2% en nov-25. La réplica F1 es la peor o casi la peor en 6 de las 9 celdas origen × componente.
- **El sesgo tiene el signo que predice esta hipótesis.** La réplica sobrepronostica en 5 de 6 casos por componente. La brecha negativa empuja el pronóstico hacia arriba y el dato no sube: de nov-25 a mar-26 la réplica proyectaba +5,5% real para el M2 y el observado fue −0,8%.
- **En los DAV, el equilibrio salta de un mes a otro.** La brecha pasa de −24% (nov-25) a +5% (abr-26) y a −30% (jul-26), mientras los DAV casi no se mueven (12,659 → 12,644 → 12,650). El motor es una elasticidad ingreso de largo plazo de alrededor de −10, que no es creíble: con la caída del EMAE de julio (−2,8%), el equilibrio de los DAV sube cerca de 28%.
  - Ese vaivén reproduce el patrón de signos de la base del BCRA de la Fase 1 (sube, baja, sube). Es la explicación más concreta que tenemos de por qué la base cambió de dirección entre programas.
  - En el agregado la réplica reproduce el patrón solo en parte (+5,5%, +0,1%, +0,6%), porque el circulante empuja siempre hacia arriba.

**Límites.**
- Solo un z sale de la banda del 95% (circulante nov-25, z = −2,04).
- La F2 logística no está identificada en ningún origen: siempre cae en el borde de la grilla. Su buen desempeño ocasional en circulante (error de 1,5% en nov-25 y 0,9% en abr-26) no es interpretable, y en DAV nov-25 falla por 17,5%.
- En el circulante, el ECM en diferencias y la caminata aleatoria también le ganan a la réplica. Que estos datos no sostienen un equilibrio útil es claro. Cuál es la mejor alternativa no se puede decidir con tres orígenes: eso es la Fase 4.

### 2. Error de escenario: poco sostenida
- El componente de escenario es chico frente al de modelo en el circulante (+0,5% contra +11,6% en nov-25). En los DAV es comparable: +2,7% en nov-25 y −3,0% en abr-26.
- Casi todo viene de la actividad: el REM pronosticó mal el EMAE. La contribución de `co` es ≈ 0 en los tres orígenes, porque las tasas realizadas siguieron de cerca la trayectoria de TAMAR del REM.
- El escenario no explica los cambios de signo de la base.

### 3. Desvíos explicados por la oferta: no sostenida para el circulante, no testeable para los DAV
- No hubo sorpresa de tasas frente al REM (contribución de `co` ≈ 0). Un desvío por decisiones de liquidez debería pasar por la tasa o por cantidades que este pipeline no observa.
- El circulante se determina por demanda a tasas dadas, y es justo donde el error es más grande.
- Para los DAV no se puede distinguir oferta de demanda con estos datos.

### 4. Revisiones de datos: secundaria para el error del modelo, relevante para medir al BCRA
- En log de saldos reales s.e., la revisión de factores estacionales es ≤ 1% en el mes objetivo y en el origen. Es chica frente a los errores de nov-25 y abr-26, y del mismo orden que los errores mínimos de jul-26.
- En % del PIB, la revisión de julio-26 entre gráficos del BCRA fue de +0,16 pp, alrededor de 2,8% del nivel (Fase 1). Proviene del PIB y de los factores estacionales del agregado, y pesa en cómo se mide el error del BCRA, no en por qué el modelo empuja en la dirección equivocada.
- Esta medición es un proxy: hay un solo snapshot, así que capta solo las revisiones estacionales.

### 5. Ruido: no se puede descartar formalmente, pero no es la mejor explicación
Con tres orígenes y bandas bootstrap, 5 de 6 z quedan dentro de ±1,96. Pero el error tiene signo sistemático (sobrepronóstico) y está asociado a una brecha persistente que el modelo ve y el dato no confirma. Eso es incompatible con ruido puro.

## Qué queda para la Fase 4
- **Candidatos.** Corrección de intercepto, ECM en diferencias, parámetros variables (intercepto de largo plazo como caminata aleatoria, Kalman) y benchmarks (caminata aleatoria con drift, ARIMA). Se evalúan con origen móvil desde que hay 48 meses de datos, y los orígenes de 2026 recién al final.
- **Riesgo de sobreajuste explícito.** Este diagnóstico ya miró los orígenes de 2026. Ninguna especificación de la Fase 4 puede justificarse por estos números; el ranking tiene que salir del pseudo fuera de muestra previo a nov-25.
