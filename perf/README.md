# Pruebas de rendimiento de la Registraduría — entrega del equipo

Equipo: [Nombre del equipo] · Integrantes: [Integrantes]

Esta carpeta tiene todo lo necesario para repetir nuestras mediciones: scripts de k6, datos de prueba, el script que corre cada escenario junto con las métricas del servidor y los resultados que obtuvimos. El análisis completo está en la Wiki del repositorio.

## Qué se prueba

Un solo endpoint, `POST /register`, que registra un votante y responde en texto plano el resultado de negocio (`VALID`, `UNDERAGE`, `DEAD`, `INVALID_AGE`, `DUPLICATED`, `INVALID`). Siempre responde `200`, así que no basta con mirar el código HTTP: el script compara cada respuesta con la columna `expected` de `perf/data/voters.csv`.

## SLA / SLO

| Métrica | Objetivo | Dónde se valida |
|---|---|---|
| p95 de latencia | < 300 ms | threshold `http_req_duration{status:200}` |
| p99 de latencia | < 800 ms | threshold `http_req_duration{status:200}` |
| Error HTTP | < 1 % | threshold `http_req_failed` |
| Resultado de negocio incorrecto | < 1 % | threshold `register_failed` |
| Throughput de referencia | ≥ 100 req/s | se revisa en el análisis (no es gate) |

Si cualquier threshold falla, k6 termina con código 99. Eso es lo que hace fallar el pipeline.

## Escenarios que ejecutamos

| Escenario | Modelo | Forma | Duración |
|---|---|---|---|
| `baseline` | cerrado, VUs constantes | 20 VUs | 5 min |
| `load` | cerrado, rampa | 0 → 200 VUs (2 min), 200 VUs (10 min), 200 → 0 (2 min) | 14 min |
| `stress` | cerrado, rampa | 200 → 600 VUs (5 min), 600 VUs (3 min), 600 → 0 (2 min) | 10 min |
| `load_pr` | cerrado, rampa | 0 → 100 VUs (30 s), 100 VUs (2 min), 100 → 0 (30 s) | 3 min (solo CI) |

Los escenarios `spike`, `soak` y `arrival` siguen disponibles en el script y se pueden lanzar on-demand desde GitHub Actions.

## Parametrización y correlación en el script

- **Datos variables:** cada iteración toma una fila al azar de `voters.csv` (512 filas, seis clases de equivalencia), así que el servicio no recibe siempre la misma petición.
- **Ids dinámicos:** el id se calcula por VU e iteración (`ID_BASE + VU·1.000.000 + iteración`) para que la regla de duplicados no contamine la medición.
- **Asserts:** se valida el código `200` y que el cuerpo sea exactamente el resultado esperado de esa fila.

## Cómo ejecutar

Requisitos: JDK 17+, Maven, k6 y Python 3. Los comandos van desde la **raíz del repositorio**.

```bash
# 1. Construir el servicio
cd registraduria && mvn -DskipTests clean package && cd ..

# 2. Un escenario (levanta el servicio, lo calienta, corre k6 y mide el servidor)
python perf/run_escenario.py sin-pool baseline
python perf/run_escenario.py con-pool load

# 3. La batería completa (baseline, load y stress, sin y con pool; ~1 hora)
python perf/run_escenario.py todos

# 4. Tabla comparativa
python perf/comparar.py
```

`sin-pool` arranca el servicio con `--registry.pool.max-size=0` (una conexión nueva por operación, como venía el taller). `con-pool` usa HikariCP con 20 conexiones, que ahora es el valor por defecto.

También se puede correr k6 a mano, con el servicio ya arriba:

```bash
k6 run --env BASE_URL=http://localhost:8080 --env SCENARIO=load perf/scripts/register_voter_k6.js
```

## Qué queda en `perf/results/`

| Archivo | Contenido |
|---|---|
| `<variante>/summary-voters-<escenario>.json` | Resumen completo de k6 (`handleSummary`) |
| `<variante>/server-<escenario>.json` | Una fila con cliente y servidor juntos: p95 de k6, p95 de Actuator, hilos, CPU, pool |
| `<variante>/timeline-<escenario>.csv` | Muestras de Actuator cada 5 s durante la corrida |
| `comparacion.md` | Tablas sin pool vs con pool y contra baseline |

## Cómo leer los resultados

1. Primero errores y p95. Si no se cumplen, no tiene sentido mirar lo demás.
2. Después, el p95 de k6 contra el p95 del servidor (`srv_p95_ms`). Si el servidor dice pocos milisegundos y k6 dice cientos, el tiempo se está yendo en cola, no en el código.
3. Por último, hilos y pool: si los hilos de Tomcat llegan al máximo o hay conexiones pendientes, ahí está el cuello de botella.
