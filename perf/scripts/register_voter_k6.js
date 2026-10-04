import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

/**
 * =========================================================================
 * ESCENARIO 2: verificación del RESULTADO DE NEGOCIO bajo carga
 * =========================================================================
 *
 * register_person_k6.js mide rendimiento sobre el camino feliz.
 * Este script mide otra cosa: que bajo carga el servicio siga dando la
 * respuesta de negocio CORRECTA, no solo un HTTP 200.
 *
 * Por qué importa: /register devuelve 200 OK tanto para VALID como para
 * UNDERAGE, DEAD, DUPLICATED e INVALID. Una prueba que solo mire el código
 * HTTP reportaría 0% de error aunque el servicio estuviera rechazando el
 * 100% de los registros. Es uno de los falsos verdes más comunes en pruebas
 * de carga sobre APIs REST.
 *
 * El dataset trae la columna 'expected' con el resultado que cada fila debe
 * producir según las reglas de negocio; el script compara contra ella.
 */

/* =========================
 * Configuración por entorno
 * ========================= */
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const DATA_FILE = __ENV.DATA_FILE || null;
const SCENARIO = (__ENV.SCENARIO || 'baseline').toLowerCase();
const TIMEOUT_MS = Number(__ENV.TIMEOUT_MS || 2000);
const SLEEP_MS = Number(__ENV.SLEEP_MS || 100);
// Desplazamiento del rango de ids, para repetir la prueba sin reiniciar el
// servicio. Ver el comentario largo en la funcion principal.
const ID_BASE = Number(__ENV.ID_BASE || 0);
// Carpeta donde handleSummary deja el resumen (p. ej. perf/results/sin-pool).
const RESULTS_DIR = __ENV.RESULTS_DIR || 'perf/results';

/* =========================
 * Métricas personalizadas
 * ========================= */
const registerDuration = new Trend('register_duration');
const registerFailed = new Rate('register_failed'); // resultado != esperado
const statusCount = new Counter('status_count');
const outcomeCount = new Counter('outcome_count'); // VALID / UNDERAGE / DEAD ...

/* =========================
 * Carga de dataset (CSV)
 * ========================= */
function tryOpen(path) {
  try {
    return open(path);
  } catch (_) {
    return null;
  }
}

const voters = new SharedArray('voters', function () {
  let csvText = null;
  if (DATA_FILE) {
    csvText = tryOpen(DATA_FILE);
    if (!csvText) {
      throw new Error("No se pudo abrir DATA_FILE. Verifica la ruta.");
    }
  } else {
    csvText = tryOpen('perf/data/voters.csv') || tryOpen('../data/voters.csv');
    if (!csvText) {
      throw new Error("No se encontro voters.csv. Usa DATA_FILE o ejecuta desde la raiz del repo.");
    }
  }
  const lines = csvText.trim().split(/\r?\n/);
  lines.shift(); // descartar cabecera
  return lines.map(function (l) {
    // CSV: id,name,age,gender,alive,expected
    const parts = l.split(',').map(function (x) { return String(x).trim(); });
    return {
      id: Number(parts[0]),
      name: parts[1],
      age: Number(parts[2]),
      gender: parts[3],
      alive: String(parts[4]).toLowerCase() === 'true',
      expected: parts[5],
    };
  });
});

/* =========================
 * Escenarios disponibles
 * =========================
 * Mismos nombres y mismas formas que register_person_k6.js, para que ambos
 * scripts sean comparables entre si.
 */
const ALL_SCENARIOS = {
  baseline: {
    executor: 'constant-vus',
    vus: 20,
    duration: '5m',
    gracefulStop: '30s',
  },
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 200 },
      { duration: '10m', target: 200 },
      { duration: '2m', target: 0 },
    ],
    gracefulRampDown: '30s',
  },
  stress: {
    executor: 'ramping-vus',
    startVUs: 200,
    stages: [
      { duration: '5m', target: 600 },
      { duration: '3m', target: 600 },
      { duration: '2m', target: 0 },
    ],
    gracefulRampDown: '30s',
  },
  spike: {
    executor: 'ramping-vus',
    startVUs: 50,
    stages: [
      { duration: '1m', target: 300 },
      { duration: '2m', target: 50 },
      { duration: '1m', target: 0 },
    ],
    gracefulRampDown: '30s',
  },
  /**
   * Version corta de 'load' para cada pull request (~3 min): misma forma
   * (rampa, sostener, bajar) a la mitad de VUs. 'load' completo dura 14 min
   * y bloquearia la revision; se ejecuta on-demand.
   */
  load_pr: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '30s', target: 100 },
      { duration: '2m', target: 100 },
      { duration: '30s', target: 0 },
    ],
    gracefulRampDown: '30s',
  },
  soak: {
    executor: 'constant-vus',
    vus: 100,
    duration: '2h',
    gracefulStop: '1m',
  },
  /**
   * Modelo ABIERTO: fija peticiones por segundo, no usuarios concurrentes.
   * Es el modelo correcto cuando el SLO se expresa en throughput ("100 req/s")
   * y no en concurrencia. Compare sus resultados con los de 'baseline'.
   */
  arrival: {
    executor: 'constant-arrival-rate',
    rate: 100,
    timeUnit: '1s',
    duration: '5m',
    preAllocatedVUs: 50,
    maxVUs: 300,
  },
};

function buildOptions() {
  const chosen = ALL_SCENARIOS[SCENARIO];
  if (!chosen) {
    console.warn("SCENARIO no reconocido: " + SCENARIO + ". Usando baseline.");
  }
  return {
    thresholds: {
      http_req_failed: ['rate<0.01'],
      // El tag 'status' de k6 contiene el CODIGO HTTP numerico, no la palabra 'ok'.
      'http_req_duration{status:200}': ['p(95)<300', 'p(99)<800'],
      // <1% de respuestas de negocio distintas de la esperada.
      register_failed: ['rate<0.01'],
    },
    scenarios: { run: chosen || ALL_SCENARIOS['baseline'] },
    // false: necesitamos el cuerpo para validar el resultado de negocio.
    // k6 por defecto no calcula p(99) en el resumen; el SLO lo necesita.
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
    discardResponseBodies: false,
    noConnectionReuse: false,
  };
}

export const options = buildOptions();

/* =========================
 * Iteración principal
 * ========================= */
export default function () {
  const v = voters[Math.floor(Math.random() * voters.length)];

  // Id unico por VU e iteracion: evita que la regla de duplicados contamine
  // la medicion. El multiplicador de __ITER debe ser mayor que el numero de
  // iteraciones que un VU alcanza, o dos VUs colisionan entre si.
  // Cota: con 600 VUs el maximo es 601_000_000, dentro del int de Java (2.147e9).
  //
  // OJO: esto garantiza ids unicos DENTRO de una corrida, no ENTRE corridas.
  // La base H2 vive mientras viva el proceso, asi que si repite la prueba sin
  // reiniciar el servicio, los mismos ids ya estan registrados y todo lo que
  // esperaba VALID devuelve DUPLICATED. Reinicie el servicio entre corridas o
  // desplace el rango con ID_BASE.
  //
  // No se puede resolver metiendo la marca de tiempo en el id: el campo es un
  // int de Java y con 600 VUs ya se consume la tercera parte del rango. El
  // estado de prueba se gestiona reiniciando, no ensanchando el identificador.
  const uniqueId = ID_BASE + (__VU * 1000000) + (__ITER % 1000000);

  const payload = JSON.stringify({
    name: v.name,
    id: uniqueId,
    age: v.age,
    gender: v.gender,
    alive: v.alive,
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: TIMEOUT_MS + 'ms',
    tags: { endpoint: '/register', scenario: SCENARIO },
  };

  const res = http.post(BASE_URL + '/register', payload, params);

  registerDuration.add(res.timings.duration, params.tags);
  statusCount.add(1, { status: String(res.status) });

  const outcome = String(res.body || '').trim().toUpperCase();
  outcomeCount.add(1, { outcome: outcome || 'SIN_CUERPO' });

  // La verificacion clave: el resultado de NEGOCIO es el esperado.
  // Un 200 con el cuerpo equivocado sigue siendo un fallo.
  const ok = check(res, {
    'status 200': function (r) { return r.status === 200; },
    'resultado de negocio esperado': function () { return outcome === v.expected; },
  });

  registerFailed.add(!ok);

  if (!ok && (__ITER % 500 === 0)) {
    console.warn("Esperado=" + v.expected + " obtenido=" + outcome + " status=" + res.status);
    // Este caso concreto casi nunca es un fallo del servicio: es estado que
    // sobrevivio de una corrida anterior. Decirlo aqui ahorra media hora de
    // buscar un cuello de botella que no existe.
    if (v.expected === 'VALID' && outcome === 'DUPLICATED') {
      console.warn(
        "  ^ Los ids ya existian. La base H2 vive mientras viva el proceso, " +
        "asi que una segunda corrida repite los mismos ids. Reinicie el " +
        "servicio, o use --env ID_BASE=700000000 para desplazar el rango."
      );
    }
  }

  if (SLEEP_MS > 0) {
    sleep(SLEEP_MS / 1000.0);
  }
}

/* =========================
 * Resumen
 * ========================= */
export function handleSummary(data) {
  const out = {};
  out['stdout'] = JSON.stringify(
    {
      escenario: SCENARIO,
      peticiones: data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0,
      p95_ms: data.metrics.http_req_duration
        ? Math.round(data.metrics.http_req_duration.values['p(95)'])
        : null,
      resultado_negocio_incorrecto: data.metrics.register_failed
        ? data.metrics.register_failed.values.rate
        : null,
    },
    null,
    2
  );
  out[RESULTS_DIR + '/summary-voters-' + SCENARIO + '.json'] = JSON.stringify(data, null, 2);
  return out;
}
