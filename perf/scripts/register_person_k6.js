
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

/**
 * =========================
 * Configuración por entorno
 * =========================
 */
const BASE_URL   = __ENV.BASE_URL || 'http://localhost:8080';
const DATA_FILE  = __ENV.DATA_FILE || null; // si no viene, el script intentará rutas por defecto
const SCENARIO   = (__ENV.SCENARIO || 'baseline').toLowerCase();
const TIMEOUT_MS = Number(__ENV.TIMEOUT_MS || 2000);
const SLEEP_MS   = Number(__ENV.SLEEP_MS || 0); // micro-pausa opcional entre iteraciones
const RESULTS_DIR = __ENV.RESULTS_DIR || 'perf/results'; // carpeta del resumen

/**
 * =========================
 * Métricas personalizadas
 * =========================
 */
const registerDuration = new Trend('register_duration');     // duración de /register
const registerFailed   = new Rate('register_failed');        // check fallido
const statusCount      = new Counter('status_count');        // contador de respuestas por código

/**
 * =========================
 * Carga de dataset (CSV)
 * =========================
 * El script intenta, en orden:
 * - __ENV.DATA_FILE (si se definió)
 * - 'perf/data/persons.csv' (ejecución desde la raíz del repo)
 * - '../data/persons.csv' (si se ejecuta dentro de perf/scripts)
 */
function tryOpen(path) {
  try {
    return open(path);
  } catch (_) {
    return null;
  }
}

const persons = new SharedArray('persons', function () {
  let csvText = null;
  if (DATA_FILE) {
    csvText = tryOpen(DATA_FILE);
    if (!csvText) {
      throw new Error(`No se pudo abrir DATA_FILE='${DATA_FILE}'. Verifica la ruta.`);
    }
  } else {
    csvText = tryOpen('perf/data/persons.csv') || tryOpen('../data/persons.csv');
    if (!csvText) {
      throw new Error("No se encontró persons.csv. Usa __ENV.DATA_FILE o ejecuta desde la raíz del repo.");
    }
  }
  const lines = csvText.trim().split(/\r?\n/);
  const header = lines.shift(); // descartar cabecera
  return lines.map((l) => {
    // CSV simple: id,name,age,gender,alive
    const parts = l.split(',');
    const [id, name, age, gender, alive] = parts.map((x) => String(x).trim());
    return { id: Number(id), name, age: Number(age), gender, alive: alive.toLowerCase() === 'true' };
  });
});

/**
 * =========================
 * Escenarios disponibles
 * =========================
 * Pueden activarse por __ENV.SCENARIO
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
      { duration: '1m', target: 300 }, // pico rápido
      { duration: '2m', target: 50 },  // recuperación
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
  regression: {
    // Ejecución corta pensada para comparar builds (antes/después)
    executor: 'constant-vus',
    vus: 20,
    duration: '5m',
    gracefulStop: '30s',
  },
};

// Construcción dinámica de options según SCENARIO
function buildOptions() {
  const chosen = ALL_SCENARIOS[SCENARIO];
  if (!chosen) {
    console.warn(`SCENARIO='${SCENARIO}' no reconocido. Usando 'baseline'.`);
  }
  return {
    thresholds: {
      http_req_failed: ['rate<0.01'],             // <1% de fallos HTTP globales
      'http_req_duration{status:200}': ['p(95)<300', 'p(99)<800'], // SLO sugeridos
      register_failed: ['rate<0.01'],             // <1% de fallos de validación
    },
    scenarios: {
      run: chosen || ALL_SCENARIOS['baseline'],
    },
    // k6 por defecto no calcula p(99) en el resumen; el SLO lo necesita.
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
    discardResponseBodies: false,
    noConnectionReuse: false,
  };
}

export const options = buildOptions();

/**
 * =========================
 * Utilidades
 * =========================
 */
function buildUniqueId(baseId) {
  // Genera IDs únicos por iteración combinando base del CSV, VU e iteración
  // Formula: __VU * 1_000_000 + (__ITER % 1_000_000)
  //
  // NO se usa baseId como prefijo: al sumarle el bloque del VU los rangos de
  // dos baseId distintos se solapan y vuelven a colisionar.
  // Cota: con 600 VUs el maximo es 601_000_000, holgadamente dentro del int
  // de Java (2_147_483_647) que espera PersonDTO.id.
  return (__VU * 1000000) + (__ITER % 1000000);
}

function nextPayload() {
  const p = persons[Math.floor(Math.random() * persons.length)];
  const uniqueId = buildUniqueId(p.id);
  return JSON.stringify({
    name: p.name,
    id: uniqueId,
    age: p.age,
    gender: p.gender,
    alive: p.alive,
  });
}

/**
 * =========================
 * Iteración principal
 * =========================
 */
export default function () {
  const payload = nextPayload();
  const params = {
    headers: { 'Content-Type': 'application/json' },
    timeout: `${TIMEOUT_MS}ms`,
    // Etiquetas opcionales: útiles para filtrar métricas
    tags: { endpoint: '/register', scenario: SCENARIO },
  };

  const res = http.post(`${BASE_URL}/register`, payload, params);

  // Métricas
  registerDuration.add(res.timings.duration, params.tags);
  statusCount.add(1, { status: String(res.status) });

  // Normalizamos el body para validación robusta
  const bodyText = String(res.body || '').trim().toUpperCase();

  const ok = check(res, {
    'status 200': (r) => r.status === 200,
    // Igualdad exacta, no includes(): 'INVALID_AGE'.includes('VALID') es true,
    // asi que includes() dejaria pasar un rechazo como si fuera un registro.
    // trim() y toUpperCase() ya toleran espacios y mayusculas.
    'body VALID': (_) => bodyText === 'VALID',
  });

  registerFailed.add(!ok);

  // Log puntual para diagnóstico (1 de cada 1000 iteraciones por VU)
  if (!ok && (__ITER % 1000 === 0)) {
    console.error(`[ERR][${SCENARIO}] status=${res.status} body='${String(res.body).slice(0, 160)}'`);
  }

  if (SLEEP_MS > 0) {
    sleep(SLEEP_MS / 1000.0);
  }
}

/**
 * =========================
 * Resumen de salida
 * =========================
 * k6 permite devolver un objeto con rutas de archivos (relativas al cwd)
 * para guardar un resumen de resultados.
 */
export function handleSummary(data) {
  // Nombre de archivo según escenario
  const scen = SCENARIO || 'baseline';
  const path = `${RESULTS_DIR}/summary-${scen}.json`;
  return {
    [path]: JSON.stringify(data, null, 2),
  };
}
