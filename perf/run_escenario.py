"""Ejecuta un escenario de k6 y recoge, al mismo tiempo, las metricas del SERVIDOR.

Uso (desde la RAIZ del repositorio, con el jar ya construido):

    python perf/run_escenario.py sin-pool baseline
    python perf/run_escenario.py con-pool load
    python perf/run_escenario.py todos            # baseline, load y stress, sin y con pool

Que hace en cada corrida:
  1. Arranca el servicio recien construido (base H2 vacia). La variante
     'sin-pool' pasa --registry.pool.max-size=0; 'con-pool' usa HikariCP (20).
  2. Lo calienta 20 s con 50 VUs (JIT y clases cargadas) en un rango de ids aparte.
  3. Corre perf/scripts/register_voter_k6.js con el escenario pedido.
  4. Cada 5 s consulta Actuator: hilos vivos, hilos ocupados de Tomcat, CPU,
     conexiones del pool y el p95 que reporta el servidor.
  5. Al final calcula el p50/p95/p99 del servidor sobre TODA la corrida a partir
     del histograma de /actuator/prometheus y lo guarda junto al resumen de k6.

Salida en perf/results/<variante>/:
  summary-voters-<escenario>.json   resumen completo de k6 (handleSummary)
  server-<escenario>.json           cliente vs servidor, en una sola fila
  timeline-<escenario>.csv          muestras de Actuator cada 5 s
  k6-<escenario>.log                salida de consola de k6

Solo usa la libreria estandar de Python 3.
"""
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JAR = os.path.join(ROOT, 'registraduria', 'target', 'registraduria-1.0-SNAPSHOT.jar')
SCRIPT = os.path.join('perf', 'scripts', 'register_voter_k6.js')
BASE = 'http://localhost:8080'
VARIANTES = {'sin-pool': ['--registry.pool.max-size=0'], 'con-pool': ['--registry.pool.max-size=20']}
ESCENARIOS = ['baseline', 'load', 'stress']
WARMUP_ID_BASE = 1_900_000_000  # rango de ids del calentamiento, lejos de la prueba


def get(path, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.read().decode('utf8')


def metric(name, tag=None):
    """Valor de /actuator/metrics/<name> (o None si no existe)."""
    try:
        d = json.loads(get('/actuator/metrics/' + name + ('?tag=' + tag if tag else '')))
        return {m['statistic']: m['value'] for m in d['measurements']}
    except Exception:
        return None


BUCKET = re.compile(r'^http_server_requests_seconds_bucket\{(.*?)\} ([0-9.eE+]+)$')
QUANT = re.compile(r'^http_server_requests_seconds\{(.*?)\} ([0-9.eE+NaN]+)$')


def prometheus():
    """Histograma acumulado de /register y p95 instantaneo que publica el servidor."""
    buckets, p95 = {}, None
    for line in get('/actuator/prometheus', 60).splitlines():
        m = BUCKET.match(line)
        if m and 'uri="/register"' in m.group(1):
            le = re.search(r'le="([^"]+)"', m.group(1)).group(1)
            le = float('inf') if le == '+Inf' else float(le)
            buckets[le] = buckets.get(le, 0) + float(m.group(2))
            continue
        m = QUANT.match(line)
        if m and 'uri="/register"' in m.group(1) and 'quantile="0.95"' in m.group(1):
            v = float(m.group(2))
            p95 = v if p95 is None else max(p95, v)
    return buckets, p95


def percentil(antes, despues, q):
    """Percentil (ms) de las peticiones ocurridas entre dos lecturas del histograma."""
    les = sorted(despues)
    delta = [(le, despues[le] - antes.get(le, 0)) for le in les]
    if not delta or delta[-1][1] <= 0:
        return None
    objetivo = q * delta[-1][1]
    prev_le, prev_c = 0.0, 0.0
    for le, c in delta:
        if c >= objetivo:
            if le == float('inf'):
                return prev_le * 1000
            frac = (objetivo - prev_c) / (c - prev_c) if c > prev_c else 1
            return (prev_le + frac * (le - prev_le)) * 1000
        prev_le, prev_c = le, c
    return None


def arrancar(variante, log_path):
    if not os.path.exists(JAR):
        raise SystemExit('No existe ' + JAR + '. Ejecute antes: cd registraduria && mvn -DskipTests package')
    log = open(log_path, 'w')
    p = subprocess.Popen(['java', '-Xms1g', '-Xmx1g', '-jar', JAR, '--server.tomcat.mbeanregistry.enabled=true']
                         + VARIANTES[variante], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            if '"UP"' in get('/actuator/health', 2):
                return p, log
        except Exception:
            pass
        if p.poll() is not None:
            raise SystemExit('El servicio termino al arrancar. Revise ' + log_path)
        time.sleep(1)
    p.kill()
    raise SystemExit('El servicio no arranco en 120 s. Revise ' + log_path)


def detener(p, log):
    p.terminate()
    try:
        p.wait(20)
    except subprocess.TimeoutExpired:
        p.kill()
    log.close()


def k6(escenario, out_dir, extra=None, log_path=None):
    cmd = ['k6', 'run', '--no-color', '--env', 'BASE_URL=' + BASE, '--env', 'SCENARIO=' + escenario,
           '--env', 'RESULTS_DIR=' + out_dir] + (extra or []) + [SCRIPT]
    with open(log_path or os.devnull, 'w') as f:
        return subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def correr(variante, escenario):
    out_rel = os.path.join('perf', 'results', variante).replace('\\', '/')
    out = os.path.join(ROOT, out_rel)
    os.makedirs(out, exist_ok=True)
    print(f'== {variante} / {escenario}', flush=True)
    srv, srv_log = arrancar(variante, os.path.join(out, f'server-{escenario}.log'))
    try:
        # Calentamiento: 20 s, 50 VUs, ids en un rango aparte. No se guarda.
        os.makedirs(os.path.join(ROOT, 'perf', 'results', '.warmup'), exist_ok=True)
        k6('baseline', os.path.join('perf', 'results', '.warmup'),
           ['--vus', '50', '--duration', '20s', '--env', f'ID_BASE={WARMUP_ID_BASE}'])

        muestras, parar = [], threading.Event()

        def muestrear():
            t0 = time.time()
            while not parar.wait(5):
                fila = {'t_s': round(time.time() - t0)}
                for clave, nombre, tag in [
                    ('hilos_vivos', 'jvm.threads.live', None),
                    ('tomcat_ocupados', 'tomcat.threads.busy', None),
                    ('cpu_proceso', 'process.cpu.usage', None),
                    ('pool_activas', 'hikaricp.connections.active', None),
                    ('pool_pendientes', 'hikaricp.connections.pending', None),
                ]:
                    m = metric(nombre, tag)
                    fila[clave] = round(m['VALUE'], 3) if m and 'VALUE' in m else None
                try:
                    _, p95 = prometheus()
                    fila['srv_p95_ms'] = round(p95 * 1000, 2) if p95 is not None else None
                except Exception:
                    fila['srv_p95_ms'] = None
                muestras.append(fila)

        antes, _ = prometheus()
        hilo = threading.Thread(target=muestrear, daemon=True)
        hilo.start()
        inicio = time.time()
        codigo = k6(escenario, out_rel, log_path=os.path.join(out, f'k6-{escenario}.log'))
        parar.set()
        hilo.join()
        despues, _ = prometheus()
    finally:
        detener(srv, srv_log)

    with open(os.path.join(out, f'timeline-{escenario}.csv'), 'w', newline='') as f:
        if muestras:
            w = csv.DictWriter(f, fieldnames=list(muestras[0].keys()))
            w.writeheader()
            w.writerows(muestras)

    m = json.load(open(os.path.join(out, f'summary-voters-{escenario}.json')))['metrics']
    d = m['http_req_duration']['values']
    maximo = lambda k: max((s[k] for s in muestras if s.get(k) is not None), default=None)
    fila = {
        'variante': variante, 'escenario': escenario, 'k6_exit': codigo,
        'duracion_s': round(time.time() - inicio),
        'peticiones': m['http_reqs']['values']['count'],
        'rps': round(m['http_reqs']['values']['rate'], 1),
        'k6_avg_ms': round(d['avg'], 2), 'k6_p50_ms': round(d['med'], 2), 'k6_p90_ms': round(d['p(90)'], 2),
        'k6_p95_ms': round(d['p(95)'], 2), 'k6_p99_ms': round(d['p(99)'], 2), 'k6_max_ms': round(d['max'], 2),
        'error_http': m['http_req_failed']['values']['rate'],
        'negocio_incorrecto': m['register_failed']['values']['rate'],
        'vus_max': m.get('vus_max', {}).get('values', {}).get('value'),
        'srv_p50_ms': percentil(antes, despues, 0.50),
        'srv_p95_ms': percentil(antes, despues, 0.95),
        'srv_p99_ms': percentil(antes, despues, 0.99),
        'srv_p95_pico_ms': maximo('srv_p95_ms'),
        'hilos_vivos_max': maximo('hilos_vivos'),
        'tomcat_ocupados_max': maximo('tomcat_ocupados'),
        'cpu_proceso_max': maximo('cpu_proceso'),
        'pool_activas_max': maximo('pool_activas'),
        'pool_pendientes_max': maximo('pool_pendientes'),
    }
    for k in ('srv_p50_ms', 'srv_p95_ms', 'srv_p99_ms'):
        if fila[k] is not None:
            fila[k] = round(fila[k], 2)
    json.dump(fila, open(os.path.join(out, f'server-{escenario}.json'), 'w'), indent=2)
    print('   ' + '  '.join(f'{k}={v}' for k, v in fila.items() if k not in ('variante', 'escenario')), flush=True)
    return fila


def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'todos':
        for v in VARIANTES:
            for e in ESCENARIOS:
                correr(v, e)
    elif len(sys.argv) == 3 and sys.argv[1] in VARIANTES:
        fila = correr(sys.argv[1], sys.argv[2])
        # Se propaga el codigo de k6: 99 = algun threshold (SLO) no se cumplio.
        # Es lo que hace fallar el paso en CI (quality gate).
        sys.exit(fila['k6_exit'])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
