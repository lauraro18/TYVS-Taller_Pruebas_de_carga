# Comparación de resultados: sin pool vs con pool (HikariCP)

Generado por `perf/comparar.py` a partir de `perf/results/<variante>/server-<escenario>.json`.

SLO: p95 < 300 ms, p99 < 800 ms, error HTTP < 1 %, resultado de negocio incorrecto < 1 %.

## Resumen por corrida

| Variante | Escenario | Peticiones | req/s | p95 k6 (ms) | p99 k6 (ms) | p95 servidor (ms) | Error HTTP | Negocio incorrecto | Hilos máx. | SLO |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| sin-pool | baseline | 58,849 | 196.1 | 1.89 | 2.59 | 0.43 | 0.00 % | 0.00 % | 61 | Cumple |
| sin-pool | load | 1,417,247 | 1,687.1 | 2.31 | 3.75 | 0.24 | 0.00 % | 0.00 % | 100 | Cumple |
| sin-pool | stress | 2,581,317 | 4,301.6 | 4.10 | 10.12 | 0.17 | 0.00 % | 0.00 % | 173 | Cumple |
| con-pool | baseline | 59,040 | 196.8 | 1.64 | 2.29 | 0.31 | 0.00 % | 0.00 % | 63 | Cumple |
| con-pool | load | 1,419,388 | 1,689.7 | 1.93 | 3.06 | 0.15 | 0.00 % | 0.00 % | 95 | Cumple |
| con-pool | stress | 2,583,177 | 4,305.2 | 3.77 | 10.05 | 0.13 | 0.00 % | 0.00 % | 171 | Cumple |

## Cambio con pool respecto a sin pool

| Escenario | Métrica | Sin pool | Con pool | Cambio |
|---|---|---:|---:|---|
| baseline | Throughput (req/s) | 196.10 | 196.80 | +0.4 % (mejora) |
| baseline | p95 k6 (ms) | 1.89 | 1.64 | -13.2 % (mejora) |
| baseline | p99 k6 (ms) | 2.59 | 2.29 | -11.6 % (mejora) |
| baseline | p95 servidor (ms) | 0.43 | 0.31 | -27.9 % (mejora) |
| baseline | Error HTTP | 0.00 % | 0.00 % | - |
| load | Throughput (req/s) | 1,687.10 | 1,689.70 | +0.2 % (mejora) |
| load | p95 k6 (ms) | 2.31 | 1.93 | -16.5 % (mejora) |
| load | p99 k6 (ms) | 3.75 | 3.06 | -18.4 % (mejora) |
| load | p95 servidor (ms) | 0.24 | 0.15 | -37.5 % (mejora) |
| load | Error HTTP | 0.00 % | 0.00 % | - |
| stress | Throughput (req/s) | 4,301.60 | 4,305.20 | +0.1 % (mejora) |
| stress | p95 k6 (ms) | 4.10 | 3.77 | -8.0 % (mejora) |
| stress | p99 k6 (ms) | 10.12 | 10.05 | -0.7 % (mejora) |
| stress | p95 servidor (ms) | 0.17 | 0.13 | -23.5 % (mejora) |
| stress | Error HTTP | 0.00 % | 0.00 % | - |

## Comparación contra baseline (misma variante)

| Variante | Escenario | p95 k6 (ms) | vs baseline | req/s | vs baseline |
|---|---|---:|---|---:|---|
| sin-pool | load | 2.31 | +22.2 % (empeora) | 1,687.1 | +760.3 % (mejora) |
| sin-pool | stress | 4.10 | +116.9 % (empeora) | 4,301.6 | +2093.6 % (mejora) |
| con-pool | load | 1.93 | +17.7 % (empeora) | 1,689.7 | +758.6 % (mejora) |
| con-pool | stress | 3.77 | +129.9 % (empeora) | 4,305.2 | +2087.6 % (mejora) |
