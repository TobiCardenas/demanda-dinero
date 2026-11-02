# Validación del panel (snapshot 2026-11-02)

Errores: 0 · Advertencias: 2

## Advertencias

- AVISO IPC INDEC vs datos.gob.ar idénticos antes de 2024-11: {'2019-04': '4.3e-04'}
- AVISO IPC var. m/m INDEC vs BCRA id 27 (±0,1 pp) antes de 2024-11: {'2017-01': '0.3pp', '2017-02': '0.4pp'}

## Chequeos

- OK  circ_public: continuo 2016-01..2026-10
- OK  cc_priv: continuo 2016-01..2026-10
- OK  ca_priv: continuo 2016-01..2026-10
- OK  m2_priv: continuo 2016-01..2026-10
- OK  m2_trans_priv: continuo 2021-01..2026-10
- OK  dav_nr: continuo 2021-01..2026-10
- OK  rate_pf30: continuo 2016-01..2026-10
- OK  rate_badlar: continuo 2016-01..2026-10
- OK  fx_a3500: continuo 2016-01..2026-10
- OK  ipc_headline: continuo 2016-12..2026-09
- OK  ipc_core: continuo 2016-12..2026-08
- OK  emae_orig: continuo 2016-01..2026-08
- OK  emae_sa: continuo 2016-01..2026-08
- OK  transf_push_ars_monto: continuo 2017-01..2026-09
- OK  pct_monto: continuo 2021-01..2026-09
- OK  debit_card_monto: continuo 2017-01..2026-08
- OK  m3_priv: continuo 2016-01..2026-10
- OK  fci_psp_saldo: continuo 2023-08..2026-08
- OK  m2_amp: continuo 2023-08..2026-08
- OK  circ_public diario: sin saltos > 7 días corridos
- OK  m2_trans_priv diario: sin saltos > 7 días corridos
- OK  cc_priv diario: sin saltos > 7 días corridos
- OK  ca_priv diario: sin saltos > 7 días corridos
- OK  rate_pf30 diario: sin saltos > 7 días corridos
- OK  circ_public: último 2026-10 = 26,621,728.17 dentro de [1e+06, 1e+09]
- OK  dav_nr: último 2026-10 = 38,270,462.51 dentro de [1e+06, 1e+09]
- OK  m2_trans_priv: último 2026-10 = 64,892,190.68 dentro de [1e+06, 1e+09]
- OK  m2_priv: último 2026-10 = 78,318,157.83 dentro de [1e+06, 1e+09]
- OK  m3_priv: último 2026-10 = 151,682,317.94 dentro de [1e+06, 1e+10]
- OK  fci_psp_saldo: último 2026-08 = 9,038,934.87 dentro de [100000, 1e+09]
- OK  rate_pf30: último 2026-10 = 21.68 dentro de [0.5, 300]
- OK  rate_badlar: último 2026-10 = 22.62 dentro de [0.5, 300]
- OK  ipc_headline: último 2026-09 = 12,514.15 dentro de [100, 1e+07]
- OK  ipc_core: último 2026-08 = 12,445.80 dentro de [100, 1e+07]
- OK  emae_sa: último 2026-08 = 149.89 dentro de [50, 400]
- OK  emae_orig: último 2026-08 = 147.75 dentro de [50, 400]
- OK  circ_public: sin valores negativos
- OK  dav_nr: sin valores negativos
- OK  m2_trans_priv: sin valores negativos
- OK  cc_priv: sin valores negativos
- OK  ca_priv: sin valores negativos
- OK  pf_priv: sin valores negativos
- OK  m3_priv: sin valores negativos
- OK  fci_psp_saldo: sin valores negativos
- OK  DAV no remunerados > 0 todos los días
- OK  M2 transaccional <= M2 privado todos los días (máx exceso -427,709)
- OK  depósitos privados en pesos: 94+95+96+97+98 = 106 - 104 (máx. dif. relativa 2.9e-16)
- OK  M3 privado >= M2 privado todos los días
- INFO M2 transaccional / M2 privado: 0.897 (2021-01-04) -> 0.828 (2026-10-27)
- OK  circulante id 67 vs id 17: máx. dif. relativa 7.66e-06 (2633 días)
- OK  IPC INDEC vs datos.gob.ar idénticos desde 2024-11
- OK  IPC var. m/m INDEC vs BCRA id 27 (±0,1 pp) desde 2024-11
- INFO IPC 2026-09: INDEC 1.9% / BCRA 1.9%
- OK  emae_orig INDEC vs datos.gob.ar, hasta 2024-07: máx. dif. 2.22e-16
- INFO emae_orig: dif. máx. en los últimos 24 meses (revisiones) 5.91e-04
- OK  emae_sa INDEC vs datos.gob.ar, hasta 2024-07: máx. dif. 2.46e-04
- INFO emae_sa: dif. máx. en los últimos 24 meses (revisiones) 1.09e-03
- OK  PIB nominal: último trimestre 2026Q2 (rezago 2 trimestres)

## Últimos datos (cotejar con la publicación oficial)

| Serie | Último mes | Valor | Var. % m/m |
|---|---|---|---|
| circ_public | 2026-10 | 26,621,728.17 | 0.41 |
| dav_nr | 2026-10 | 38,270,462.51 | -0.41 |
| m2_trans_priv | 2026-10 | 64,892,190.68 | -0.08 |
| rate_pf30 | 2026-10 | 21.68 | 1.42 |
| ipc_headline | 2026-09 | 12,514.15 | 1.93 |
| ipc_core | 2026-08 | 12,445.80 | 1.81 |
| emae_sa | 2026-08 | 149.89 | 0.07 |
| transf_push_ars_monto | 2026-09 | 99,746,377,528,133.03 | 3.91 |
| pct_monto | 2026-09 | 3,099,909,487,647.77 | 3.99 |
