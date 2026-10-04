"""Arma la tabla comparativa sin pool vs con pool a partir de perf/results/*/server-*.json.

    python perf/comparar.py        # escribe perf/results/comparacion.md y lo muestra

Solo usa la libreria estandar de Python 3.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'perf', 'results')
ESCENARIOS = ['baseline', 'load', 'stress']
SLO_P95, SLO_P99, SLO_ERR = 300, 800, 0.01


def leer(variante, escenario):
    p = os.path.join(RES, variante, f'server-{escenario}.json')
    return json.load(open(p)) if os.path.exists(p) else None


def n(v, dec=1):
    return '-' if v is None else f'{v:,.{dec}f}'


def pct(v):
    return '-' if v is None else f'{v * 100:.2f} %'


def cambio(antes, despues, menor_es_mejor=True):
    if antes in (None, 0) or despues is None:
        return '-'
    d = (despues - antes) / antes * 100
    mejora = d < 0 if menor_es_mejor else d > 0
    return f'{d:+.1f} % ({"mejora" if mejora else "empeora"})'


def cumple(f):
    if f is None:
        return '-'
    ok = f['k6_p95_ms'] < SLO_P95 and f['k6_p99_ms'] < SLO_P99 and f['error_http'] < SLO_ERR \
        and f['negocio_incorrecto'] < SLO_ERR
    return 'Cumple' if ok else 'No cumple'


def main():
    out = ['# Comparación de resultados: sin pool vs con pool (HikariCP)', '',
           'Generado por `perf/comparar.py` a partir de `perf/results/<variante>/server-<escenario>.json`.', '',
           f'SLO: p95 < {SLO_P95} ms, p99 < {SLO_P99} ms, error HTTP < 1 %, resultado de negocio incorrecto < 1 %.', '']

    out += ['## Resumen por corrida', '',
            '| Variante | Escenario | Peticiones | req/s | p95 k6 (ms) | p99 k6 (ms) | p95 servidor (ms) | Error HTTP | Negocio incorrecto | Hilos máx. | SLO |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for v in ('sin-pool', 'con-pool'):
        for e in ESCENARIOS:
            f = leer(v, e)
            if not f:
                continue
            out.append(f"| {v} | {e} | {f['peticiones']:,} | {n(f['rps'])} | {n(f['k6_p95_ms'], 2)} | {n(f['k6_p99_ms'], 2)} | "
                       f"{n(f['srv_p95_ms'], 2)} | {pct(f['error_http'])} | {pct(f['negocio_incorrecto'])} | "
                       f"{n(f['hilos_vivos_max'], 0)} | {cumple(f)} |")

    out += ['', '## Cambio con pool respecto a sin pool', '',
            '| Escenario | Métrica | Sin pool | Con pool | Cambio |', '|---|---|---:|---:|---|']
    for e in ESCENARIOS:
        a, b = leer('sin-pool', e), leer('con-pool', e)
        if not a or not b:
            continue
        for clave, nombre, menor in [('rps', 'Throughput (req/s)', False), ('k6_p95_ms', 'p95 k6 (ms)', True),
                                     ('k6_p99_ms', 'p99 k6 (ms)', True), ('srv_p95_ms', 'p95 servidor (ms)', True),
                                     ('error_http', 'Error HTTP', True)]:
            fa, fb = (pct, pct) if clave == 'error_http' else (lambda x: n(x, 2), lambda x: n(x, 2))
            out.append(f'| {e} | {nombre} | {fa(a[clave])} | {fb(b[clave])} | {cambio(a[clave], b[clave], menor)} |')

    out += ['', '## Comparación contra baseline (misma variante)', '',
            '| Variante | Escenario | p95 k6 (ms) | vs baseline | req/s | vs baseline |', '|---|---|---:|---|---:|---|']
    for v in ('sin-pool', 'con-pool'):
        base = leer(v, 'baseline')
        for e in ESCENARIOS[1:]:
            f = leer(v, e)
            if not base or not f:
                continue
            out.append(f"| {v} | {e} | {n(f['k6_p95_ms'], 2)} | {cambio(base['k6_p95_ms'], f['k6_p95_ms'])} | "
                       f"{n(f['rps'])} | {cambio(base['rps'], f['rps'], False)} |")

    texto = '\n'.join(out) + '\n'
    open(os.path.join(RES, 'comparacion.md'), 'w', encoding='utf8').write(texto)
    print(texto)


if __name__ == '__main__':
    main()
