# Registro de Defectos — Pruebas de Carga y Rendimiento

Curso: Testing y Validación de Software\
Proyecto: Pruebas de Carga y Rendimiento — Registraduría\
Integrantes: Laura Sofia Rodriguez Gonzalez


------------------------------------------------------------------------

## Formato 1: Lista detallada

## Defecto PERF-01 — Se abre una conexión JDBC nueva en cada operación

- **Capa afectada:** Persistencia (`RegistryRepository.getConnection()`)
- **Caso de prueba:** escenarios `baseline`, `load` y `stress` con `register_voter_k6.js`, comparando el servicio sin pool y con pool.
- **Entrada:** `POST /register` con filas aleatorias de `voters.csv`; 20, 200 y 600 VUs.
- **Resultado esperado:** que cada petición reutilice conexiones en vez de crearlas y destruirlas.
- **Resultado obtenido:** sin pool, cada registro válido abre dos conexiones (`existsById` y `save`). Al agregar HikariCP, el tiempo que el servidor tarda en atender la petición bajó en los tres escenarios:

| Escenario | p95 servidor sin pool | p95 servidor con pool | Cambio | p95 k6 sin pool | p95 k6 con pool | Cambio |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 0,43 ms | 0,31 ms | −27,9 % | 1,89 ms | 1,64 ms | −13,2 % |
| Carga | 0,24 ms | 0,15 ms | −37,5 % | 2,31 ms | 1,93 ms | −16,5 % |
| Estrés | 0,17 ms | 0,13 ms | −23,5 % | 4,10 ms | 3,77 ms | −8,0 % |

### Evidencia

```text
sin-pool / load:  srv_p95_ms=0.24  k6_p95_ms=2.31  pool_activas_max=None
con-pool / load:  srv_p95_ms=0.15  k6_p95_ms=1.93  pool_activas_max=1.0  pool_pendientes_max=0.0
```

### Impacto

Con H2 en memoria abrir una conexión es barato, y aun así se nota. Contra una base de datos real por red (PostgreSQL, MySQL) cada conexión implica un handshake y autenticación, y el costo sería mucho mayor. Las pruebas unitarias y de integración no lo detectan porque con un solo usuario el servicio funciona bien.

### Causa

`DriverManager.getConnection(...)` dentro de `getConnection()`: no hay pool.

### Corrección

Se agregó HikariCP (20 conexiones) en `RegistryConfig`. El pool queda registrado en Actuator (`hikaricp.connections.*`). La propiedad `registry.pool.max-size=0` permite volver al comportamiento anterior para repetir la medición del "antes".

### Estado

Resuelto (validado con una nueva corrida de los tres escenarios)

### Prioridad

Media: no rompía los SLO en este entorno, pero es la principal fuente de desperdicio del servicio.

------------------------------------------------------------------------

## Defecto PERF-02 — La cola de latencia crece bajo estrés

- **Capa afectada:** Cliente / entorno de prueba
- **Caso de prueba:** escenario `stress` (200 → 600 VUs)
- **Resultado esperado:** que el p99 se mantenga cerca del p95, como en baseline.
- **Resultado obtenido:** el p99 pasa de 2,59 ms en baseline a 10,12 ms en estrés (sin pool), y el máximo llega a 69,6 ms. En el servidor, el p99 se queda en 0,73 ms.

### Evidencia

```text
sin-pool / baseline: k6_p95=1.89  k6_p99=2.59   k6_max=15.37  srv_p99=0.84
sin-pool / stress:   k6_p95=4.10  k6_p99=10.12  k6_max=69.61  srv_p99=0.73
con-pool / stress:   k6_p95=3.77  k6_p99=10.05  k6_max=55.48  srv_p99=0.56
```

### Impacto

El SLO se cumple con mucha holgura (p99 < 800 ms), pero la cola se multiplica casi por cuatro. El pool no la mejora: el p99 es prácticamente igual con y sin pool.

### Causa probable

El tiempo extra no está en el servidor (su p99 no sube). Lo más probable es que venga de que k6 y el servicio comparten la misma máquina de GitHub Actions y compiten por CPU cuando hay 600 VUs. No lo pudimos confirmar porque no medimos la CPU de k6.

### Estado

Abierto

### Prioridad

Baja

------------------------------------------------------------------------

## Formato 2: Tabla de seguimiento

| ID | Escenario | Entrada | Resultado esperado | Resultado obtenido | Causa probable | Estado | Prioridad |
|----|-----------|---------|--------------------|--------------------|----------------|--------|-----------|
| PERF-01 | Baseline, carga, estrés | 20 / 200 / 600 VUs | Reutilizar conexiones | p95 del servidor 24–38 % más alto sin pool | Conexión nueva por operación (`DriverManager`) | Resuelto | Media |
| PERF-02 | Estrés | 600 VUs | p99 estable | p99 de 2,59 → 10,12 ms; máx. 69,6 ms | k6 y servicio comparten CPU | Abierto | Baja |

------------------------------------------------------------------------

## Convenciones de Estado

- **Abierto:** defecto identificado sin corrección aplicada.
- **En progreso:** en proceso de corrección.
- **Resuelto:** corregido y validado con nuevas pruebas.
