# Roadmap SIBU 3.0

**Estado de este documento:** vivo. Se actualiza al cerrar cada bloque, nunca describe como
implementado algo que solo está diseñado. Reemplaza cualquier lista informal de "qué falta"
mencionada en el chat: esta es la referencia.

**Autorización de alcance:** a partir de `PROYECTO.md` sección 0.1 (2026-09-12), el propietario
autorizó formalmente evolucionar el alcance funcional más allá de `compra 0100 → TCP →
0110` (baseline académico, cerrado y sin reescribir). Este documento es la referencia viva de
qué fase está en qué estado:

| Fase | Estado |
|---|---|
| A — Variables dinámicas | **IMPLEMENTADA** |
| D0 — cobertura de `host_simulado/cli.py` | **IMPLEMENTADA** |
| B — Modelo multi-MTI, subfase B1 (núcleo genérico) | **IMPLEMENTADA** en `feature/multi-mti-b1-core-generico` (sin mergear a `main`, en revisión) |
| B — Modelo multi-MTI, subfase B2 (Echo 0800/0810, primer segundo flujo real) | **IMPLEMENTADA**, integrada a `main` (ver B3-B6 abajo) |
| B — Modelo multi-MTI, subfase B3 (Escenarios/suites/CLI Multi-MTI, Echo con ciclo completo) | **IMPLEMENTADA**, integrada a `main` |
| B — Modelo multi-MTI, subfase B4 (0200/0210 compra financiera real) | **IMPLEMENTADA**, integrada a `main` (merge `1998491`) |
| B — Modelo multi-MTI, subfase B5 (editor común de operaciones con tarjeta) | **IMPLEMENTADA**, integrada a `main` (merge `07b69f3`) |
| B — Modelo multi-MTI, subfase B6 (modelo conceptual de operación derivada/reverso, SIN 0400/0410) | **IMPLEMENTADA**, integrada a `main` (merge `7c034ed`) |
| B — Modelo multi-MTI, subfase B7 (reverso interactivo real, 0400/0410) | **IMPLEMENTADA**, integrada a `main` (merge `6a31ce3`) |
| C — Secuencias transaccionales, subfase C1 (infraestructura mínima: 0200 → 0400 dependiente) | **IMPLEMENTADA**, integrada a `main` (merge `989991e`) |
| C — Secuencias transaccionales, subfase C2 (contexto y variables entre pasos: `{{step.<id>...}}`) | **IMPLEMENTADA**, integrada a `main` (merge `04372ba`) |
| B — Modelo multi-MTI, subfase B8 (aviso de reverso, 0420/0430) | **IMPLEMENTADA**, integrada a `main` (merge `9a7dd32`) |
| C — Secuencias transaccionales, subfase C3 (política de continuación STOP/CONTINUE, expectativas dinámicas, retry mínimo seguro) | **IMPLEMENTADA**, integrada a `main` (merge `a7be884`) |
| D — Host Simulator 2.0, subfase D1 (motor de reglas declarativas, persistencia SQLite, UI) | **IMPLEMENTADA**, integrada a `main` (merge `fc69dbd`) |
| D — Host Simulator 2.0, subfase D2 (reglas con estado limitado: `max_aplicaciones`, atomicidad real) | **IMPLEMENTADA** en `feature/host-simulator-d2-stateful-rules` (commits `906593d`/`9353499`/`d32ce30`/`640d627`/`34dba88`/`ea118e7`, sin mergear a `main`, en revisión) |
| D — Host Simulator 2.0, subfase D1 (motor de reglas declarativas, persistencia SQLite, UI) | **IMPLEMENTADA** en `feature/host-simulator-d1-rules-engine` (commits `8fcbb36`/`791fa6b`/`39c4215`/`f6da670`/`d4538f9`/`4a498bf`, sin mergear a `main`, en revisión) |
| D1-D3, E, F, G, H, I | **PLANIFICADO** o **INVESTIGACIÓN** (ver detalle en la sección de cada fase) |

**Origen:** jornada de trabajo autónoma del 2026-09-11/12, coordinada por el agente principal con
10 agentes especializados (investigación/diseño, sin escritura de código salvo lo que el
coordinador integró explícitamente). Los reportes completos de los 10 agentes viven en el
historial de la sesión; este documento consolida sus hallazgos, resuelve contradicciones entre
ellos, y los traduce a un plan ejecutable en bloques pequeños.

**Regla de este documento:** todo hallazgo cita su origen (código real, prueba real, agente,
documentación pública). Lo que es hipótesis se marca `HIPÓTESIS` explícitamente. Nunca se
describe una funcionalidad futura como si ya existiera.

---

## 1. Matriz maestra de hallazgos

IDs estables por dominio: `ARCH-*` (arquitectura/multi-MTI/secuencias), `SEC-*` (seguridad),
`UX-*` (producto/UI), `PERF-*` (performance), `PROD-*` (productización), `QA-*` (calidad de
tests). Severidad ≠ prioridad de implementación: una severidad P0 puede corresponder a una
funcionalidad que todavía no existe (riesgo latente), no a un defecto activo hoy.

| ID | Hallazgo | Agente(s) | Severidad | Impacto | Propuesta | Dependencias | Decisión |
|---|---|---|---|---|---|---|---|
| ARCH-001 | `CAMPOS_SENSIBLES` es un `frozenset` fijo por número de campo (`{"2","35"}`), no por procedencia del valor. Un campo no-sensible (DE42, DE43, o un campo propietario de un MTI futuro) puede transportar un PAN/Track sin que ninguna guardia lo detecte. | Seguridad (auditoría post Core 2.0) | **P0** (riesgo latente — no hay incidente hoy, sí una vía abierta para uno futuro) | Si Fase A (variables) o Fase B (multi-MTI) llegaran a exponer una variable `{{card.pan}}` sin restricción, o un MTI nuevo repitiera el PAN bajo otro número de campo, el enmascarado actual no lo cubre. | Antes de exponer cualquier variable que toque datos de tarjeta más allá de `card.pan_enmascarado` (ya excluido por diseño en ARCH-006), o de declarar `CAMPOS_SENSIBLES` para un MTI nuevo, evaluar `campos_sensibles(mti, perfil)` como función en vez de constante global. | Bloquea: exponer `{{card.*}}` no enmascarado en Fase A2; declarar políticas de MTI nuevo en Fase B sin revisar esta función. | Aceptado como riesgo documentado; no se actúa hasta que Fase A2 o Fase B lo activen de verdad. |
| ARCH-002 | `_registrar` en `Orquestador` construye una `Ejecucion` asumiendo siempre `card_id`/`monto`/`moneda`. Un MTI sin tarjeta (0800 network management) no tiene forma de pasar por el mismo `_registrar` sin decidir qué significan esos campos para ese caso. | Multi-MTI | P2 | Bloquea a Fase B solo cuando se intente implementar 0800/0810 (Fase B, subfase tardía); no bloquea 0200/0400. | Dejar la decisión para cuando exista un MTI sin tarjeta real que lo necesite (Fase B3+); no diseñar una `Ejecucion` genérica "por si acaso". | Depende de que el proyecto decida ampliar alcance a un MTI sin tarjeta (fuera del alcance actual de `PROYECTO.md`). | Diferido explícitamente — no se resuelve en Fase B1/B2. |
| ARCH-003 | El diseño de Variables (Fase A) asumía que `domain/armado.py::valores_efectivos_editables` necesitaría modificarse para NO resolver expresiones al congelar un escenario. Verificado en código real: no hace falta ningún cambio, porque `validar_campos_manuales` (la función que `valores_efectivos_editables` reutiliza) solo valida `origen` del campo, nunca la forma del valor — así que una expresión `"{{stan}}"` ya pasa intacta sin ningún cambio de código. | Arquitectura de variables (diseño) vs. auditoría de Fase A (código real) | — (contradicción de supuesto, no de hallazgo) | Ninguno: el resultado final es el mismo que el diseño pedía, por una razón distinta a la que el diseño anticipaba. | Ninguna acción de código; documentado para que un futuro lector no intente "corregir" algo que ya funciona. | — | Resuelta: verificado con `test_valores_efectivos_editables_congela_la_expresion_sin_resolverla` en `tests/test_variables.py`. |
| ARCH-004 | El plan de fases sugiere Secuencias (Fase C) después de Multi-MTI (Fase B). El propio diseño de Secuencias declara que su **entrega mínima** no necesita ningún MTI nuevo: usa dos pasos 0100→0100, y el mecanismo de dependencias/captura es agnóstico al MTI concreto (delega en `Escenario.mti`, que ya existe como campo de texto libre). | Secuencias | — (hallazgo de secuenciación, no de riesgo) | Permite paralelizar: la infraestructura base de Secuencias (tablas, `PasoSecuencia`, motor de dependencias) puede construirse y probarse ANTES de que Multi-MTI aporte un segundo MTI real. Solo el caso de uso "con valor real" (0100→0200→0420) necesita ambas fases completas. | Ninguna: Fase C1 (infraestructura) no depende de Fase B. Fase C2+ (secuencias con MTIs reales) sí depende de Fase B. | El orden preferido A→B→C se mantiene para el caso de uso final, pero **C1 puede adelantarse en paralelo a B** si conviene por capacidad de trabajo disponible. | Se documenta la opción; no se decide adelantar todavía (ver sección 6). |
| ARCH-005 | El diseño de Multi-MTI para RN-3 (correlación) confirma que `validacion._mti_de_respuesta` (tercer dígito 0→1) y `campos_de_correlacion` (derivado del perfil) **ya son genéricos** y funcionan sin cambios para 0200/0210, 0400/0410, 0800/0810. Solo 0800 (sin DE39) y los reversos (correlación cruzada entre dos mensajes distintos, no dentro del mismo intercambio) necesitan una `EstrategiaCorrelacion` nueva. | Multi-MTI | — | Reduce el riesgo percibido de "romper RN-3" al ampliar MTIs: la mayoría de los casos no la tocan. | Extraer `EstrategiaCorrelacion` como interfaz solo cuando el primer MTI que la necesite (reverso) esté en desarrollo real — no antes. | Fase B, subfase de reversos (tardía, ver sección 6). | Diferido a su subfase correspondiente. |
| ARCH-006 | El diseño de variables (Fase A, completo) deliberadamente **no expone `{{card.pan}}`** (PAN completo) como variable de catálogo, aunque el contexto de resolución interno sí tenga acceso a la tarjeta completa (igual que `armar_compra` ya lo tiene hoy para DE2). Solo estaba prevista `{{card.pan_enmascarado}}` para una entrega futura. | Arquitectura de variables | — (mitigación ya incorporada al diseño, confirma que ARCH-001 está contemplado para variables) | Cierra por diseño la vía de fuga que ARCH-001/SEC-001 señalan, específicamente para el mecanismo de variables — pero NO para multi-MTI ni para host simulator, que son superficies distintas. | Ninguna acción nueva: ya es la decisión tomada. Mantenerla al implementar Fase A2 (namespaces `card.*`/`terminal.*`). | Fase A2. | Confirmado como parte del contrato de diseño para A2. |
| SEC-001 | (Duplica ARCH-001, mismo hallazgo, origen independiente: la auditoría de seguridad llegó a la misma conclusión sin conocer el documento de arquitectura de variables.) | Seguridad | P0 (riesgo latente) | — | — | — | Fusionado con ARCH-001; ambos agentes coincidieron sin coordinación previa, lo que refuerza la validez del hallazgo. |
| SEC-002 | El guardián de PAN (`test_ningun_archivo_versionable_contiene_un_pan_completo`) no distingue "12-19 dígitos consecutivos que son un monto formateado" de "un PAN real". Se disparó como falso positivo durante la implementación de Fase A (un literal de prueba de `{{amount}}`). | Auditoría de Fase A (hallazgo propio, no de un agente de investigación) | P3 | Fricción de desarrollo (falso positivo), no un riesgo de seguridad real: el guardián sigue funcionando correctamente para su propósito (detectar PAN real). | Ya corregido en la prueba afectada (comparar contra `formatear_monto()` en vez de un literal). No se toca el guardián: es correcto que sea estricto. | — | Resuelto en el commit de auditoría de Fase A. |
| QA-001 | Duplicación de dobles de `RepositorioTarjetas`/`RepositorioDestinos`/`RepositorioEscenarios` entre `tests/test_web.py` y `tests/test_vista_previa.py` (y otros). | Calidad de tests | P3 | Mantenimiento: dos lugares que actualizar en sincronía si el puerto cambia. | Mover un doble mínimo a `conftest.py`, parametrizable. | Ninguna. | Backlog de limpieza, no bloquea ninguna fase. |
| QA-002 | `adapters/host_simulado/cli.py` (entry point `sibu-host-demo`) no tiene ningún test dedicado — único gap de cobertura real encontrado en 1101 tests. | Calidad de tests | P2 | Si Fase D (Host Simulator 2.0) toca `cli.py` para agregar `--reglas`, se modificaría un archivo sin red de pruebas propia. | Agregar un test de `_argumentos()` (análogo a `test_ci_esperar_host.py`) ANTES de tocar `cli.py` en Fase D. | Bloquea el inicio seguro de Fase D (subfase de CLI). | Pendiente — se resuelve como primer paso de Fase D, no antes por sí solo. |
| QA-003 | Suite completa (1101 tests tras Fase A) corre en ~100s con SQLite real en casi todos los tests; decisión ya documentada y justificada en `conftest.py`, no un problema. | Calidad de tests | — | Ninguno — confirmado, no es un hallazgo accionable. | Ninguna. | — | Sin acción. |
| UX-001 | El veredicto PASS/FAIL (`pieza_evaluacion`) aparece DEBAJO de la tabla puramente descriptiva de comparación de protocolo, en `resultado.html`/`detalle.html`. Invierte la jerarquía de importancia para una herramienta de QA. | UX | P1 (fricción real, no bloqueante) | Un usuario nuevo lee primero lo secundario. | Invertir el orden de las dos líneas en ambas plantillas (cambio de una línea, sin tocar `presentacion.py`). | Ninguna. | Backlog de UI, bajo riesgo — candidato a bloque pequeño independiente de cualquier fase funcional. |
| UX-002 | La numeración "1→2→3" del recorrido de compra no coincide con el orden visual de lectura (el aside con los pasos 1 y 3 se dibuja a la derecha del paso 2). | UX | P1 | Confunde a un usuario nuevo siguiendo la numeración. | Renombrar a rótulos no ordinales, o quitar el `order` CSS. | Ninguna. | Backlog de UI. |
| UX-003..011 | Ver reporte completo del agente de UX (9 hallazgos P1/P2 adicionales: densidad de tabla de historial, columna "Tarjeta" mezclando conceptos, vista previa que puede desactualizarse sin aviso, etc.) | UX | P1-P2 | Fricción de uso, ninguno bloqueante. | Ver reporte completo (no reproducido aquí por espacio). | Ninguna. | Backlog de UI — candidato a un bloque de pulido de interfaz independiente, no ligado a ninguna fase funcional de este roadmap. |
| PERF-001 | El cuello de botella real de un futuro motor de carga NO es el generador de STAN (`UPDATE...RETURNING` atómico, ya concurrency-safe) ni el transporte TCP (una conexión por mensaje, sin pool, ya aceptable para el MVP) — es `RepositorioEjecucionesSQLite.guardar`, que hace `commit()` por fila en la ruta caliente. | Performance | P1 (para cuando exista Fase F) | A TPS altos, la latencia observada mediría la persistencia, no el switch bajo prueba — invalidaría la métrica de TPS real. | En Fase F, no persistir cada transacción de carga en la ruta caliente: acumular en memoria y volcar en lotes o al cierre. | Bloquea a Fase F si se ignora: el diseño del motor de carga debe partir de este hallazgo, no descubrirlo después de implementar. | Incorporado como requisito de diseño de Fase F (sección 6). |
| PERF-002 | El STAN de 6 dígitos (`STAN_MAXIMO`) se recicla en corridas largas/alto TPS — no es un defecto, es una propiedad documentada del campo 11. | Performance | P3 | Ninguno funcional; el reporte de una corrida de carga debe mencionarlo si detecta STANs repetidos en la ventana. | Documentar en el reporte de Fase F cuando exista. | Fase F. | Nota para el diseño de Fase F, no acción hoy. |
| PROD-001 | La arquitectura de puertos (`domain/puertos.py` como `Protocol`) ya permite migrar SQLite→PostgreSQL sin tocar `domain/` ni `application/` — verificado leyendo el código, no supuesto. | Productización | — (fortaleza confirmada, no riesgo) | Reduce el riesgo percibido de Fase I: la migración de motor de base de datos es aditiva (un adaptador nuevo), no un refactor de dominio. | Ninguna acción hoy — Fase I sigue siendo la última fase, sin trabajo de código todavía. | Ninguna. | Confirma que Fase I, cuando llegue, es de bajo riesgo arquitectónico (no de bajo esfuerzo de producto: auth/roles/audit log sí son trabajo real). |
| PROD-002 | Ninguna tabla tiene columna de propietario/tenant; ningún puerto recibe un "contexto de quién pregunta"; no hay capa de autenticación en absoluto. | Productización | P3 (correcto para el alcance actual, no un defecto) | Cualquier escalón de multi-usuario real requiere este trabajo primero. | No implementar — el alcance actual (`PROYECTO.md`) es explícitamente single-user. | Bloquea el inicio de Fase I. | Confirmado: quedarse en el escalón actual; Fase I es investigación, no implementación, hasta que el alcance del proyecto cambie explícitamente. |

---

## 2. Mapa de capacidades (fotografía funcional actual)

Clasificación: **IMPLEMENTADO** (código real, probado) · **PARCIAL** (existe algo, incompleto o
no conectado) · **DISEÑADO** (documento de diseño de un agente, cero código) · **NO
IMPLEMENTADO**.

### ISO / Mensajería

| Capacidad | Estado | Evidencia |
|---|---|---|
| Constructor gobernado por perfil | IMPLEMENTADO | `domain/armado.py::armar_compra`, `profiles/generico.py::PerfilDeMarca` |
| Bitmap | IMPLEMENTADO | `adapters/iso8583/codec.py::bitmap_hex` |
| Campos opcionales | IMPLEMENTADO | 5 opcionales (18/25/32/42/43), `PoliticaCamposMti.opcionales` |
| Preview (vista previa) | IMPLEMENTADO | `application/vista_previa.py` |
| RAW/HEX seguro reconstruido | IMPLEMENTADO | `adapters/iso8583/codec.py::raw_hex_seguro`, guard `MensajeSinEnmascararError` |
| Variables dinámicas (built-in, campos editables) | IMPLEMENTADO (alcance mínimo) | `domain/variables.py`, integrado en orquestador y vista previa (Fase A, ver sección 5) |
| Variables en campos opcionales | NO IMPLEMENTADO | `validar_forma_de_opcionales` rechaza expresiones sin resolver (verificado, sección 5) |
| Variables con namespace (`card.*`, `terminal.*`) / `{{previous.*}}` | DISEÑADO | Documento de Agente 1 (arquitectura de variables) |
| Track 1 | PARCIAL | `domain/tracks.py` deriva la representación lógica; ningún perfil declara DE45; nada la invoca |
| Track 2 | PARCIAL | Igual que Track 1, vía DE35 (no declarado en ningún perfil) |
| Múltiples MTI | DISEÑADO | Documento de Agente 2 (multi-MTI); hoy solo 0100/0110 |
| Field 55 (EMV/TLV) | NO IMPLEMENTADO | Sin código, sin diseño propio en esta jornada (ver Fase G) |
| EMV (ARQC/TC, SDA/DDA) | NO IMPLEMENTADO | — |
| PIN | PARCIAL | `TarjetaPrueba.pin_block_laboratorio`: campo con forma de PIN Block, explícitamente no criptográficamente válido; sin DE52 en ningún perfil |
| MAC | NO IMPLEMENTADO | — |

### QA

| Capacidad | Estado | Evidencia |
|---|---|---|
| Escenarios | IMPLEMENTADO | `application/escenarios.py` |
| Expected vs Actual | IMPLEMENTADO | `domain/expectativas.py`, `EstadoEvaluacion` |
| Suites | IMPLEMENTADO | `application/corredor_suites.py` |
| Corridas | IMPLEMENTADO | `domain/comparacion_corridas.py`, tablas `corridas_suite` |
| Comparación de corridas | IMPLEMENTADO | `application/comparacion_corridas.py::ServicioComparacionCorridas` |
| Reintento (selectivo, de fallidos) | IMPLEMENTADO | `application/corredor_suites.py::reintentar_fallidos` |
| Variables | IMPLEMENTADO (alcance mínimo) | Ver ISO/Mensajería arriba |
| Secuencias multi-paso | DISEÑADO | Documento de Agente 3 (secuencias transaccionales) |
| Data-driven testing (variables + datos externos parametrizando un escenario) | NO IMPLEMENTADO | Ningún mecanismo de fuente de datos externa (CSV, etc.) diseñado ni implementado |
| Scheduler (ejecución programada de suites) | NO IMPLEMENTADO | `sibu-run-suite` es invocación manual/CI, no hay cron ni programación interna |

### Simulación

| Capacidad | Estado | Evidencia |
|---|---|---|
| Host demo | IMPLEMENTADO | `adapters/host_simulado/servidor.py` |
| Reglas dinámicas (declarativas, por contenido de solicitud) | DISEÑADO | Documento de Agente 4 (Host Simulator 2.0) |
| Server | IMPLEMENTADO | `HostSimulado` sobre `asyncio.start_server` |
| Client | IMPLEMENTADO | `adapters/transporte/tcp.py::TransporteTcp` |
| Proxy | NO IMPLEMENTADO | Sin diseño propio en esta jornada |
| Errores inducidos (rechazo, malformado, cierre abrupto) | PARCIAL | Código fijo (`campos_alterados`, `responder=False`) hoy; declarativo por regla es DISEÑADO, no implementado |
| Delays | PARCIAL | El host puede no responder (timeout global); un delay configurable por regla es DISEÑADO |
| Timeouts | IMPLEMENTADO (lado cliente) | `TiempoAgotado`, RN-2 en `application/orquestador.py` |

### Performance

| Capacidad | Estado | Evidencia |
|---|---|---|
| Concurrencia | NO IMPLEMENTADO (motor de carga) | El transporte y el orquestador ya son `async`, reutilizables, pero no existe ningún orquestador de carga |
| TPS | NO IMPLEMENTADO | — |
| Ramp-up/down | NO IMPLEMENTADO | — |
| Percentiles | NO IMPLEMENTADO | Solo se persiste `latencia_ms` cruda por ejecución; ningún cálculo agregado existe hoy |
| Dashboards de carga | NO IMPLEMENTADO | — |
| Diseño del motor de carga | DISEÑADO | Documento de Agente 9 (Performance/Load Engine) |

### Producto

| Capacidad | Estado | Evidencia |
|---|---|---|
| CLI | IMPLEMENTADO | `cli.py` (`sibu-run-suite`, códigos de salida documentados) |
| CI | IMPLEMENTADO | `.github/workflows/ci-suite-demo.yml` |
| Export | IMPLEMENTADO | `application/exportacion_corridas.py` (JSON/CSV) |
| Usuarios | NO IMPLEMENTADO | Sin autenticación en absoluto |
| Roles | NO IMPLEMENTADO | — |
| Organizaciones | NO IMPLEMENTADO | — |
| Audit log | NO IMPLEMENTADO | Sin actor que registrar (no hay login) |
| Docker | NO IMPLEMENTADO | Mencionado en `CLAUDE.md` como mecanismo de distribución futuro, nunca requerido para desarrollar |
| PostgreSQL | NO IMPLEMENTADO (arquitectónicamente listo) | `domain/puertos.py` como `Protocol` ya lo permitiría sin tocar dominio (PROD-001) |
| On-prem | NO IMPLEMENTADO | Corre hoy como proceso local; on-prem real solo cambia despliegue, no código |
| SaaS | NO IMPLEMENTADO | Fuera de alcance explícito |

---

## 3. Comparación competitiva (consolidado del benchmark)

Fuente: Agente 8 (Benchmark competitivo), únicamente información pública (ver lista de fuentes
al final de esta sección). Donde no hay evidencia pública suficiente, se marca explícitamente
`No verificable públicamente` en vez de asumir.

| Capacidad | Sibu | VTS/V.I.P. (Visa) | ISO8583Studio | jPOS/ecosistema | Otros (neaPay, isosim, JMeter-ISO8583) | Gap |
|---|---|---|---|---|---|---|
| Message builder gobernado por perfil | IMPLEMENTADO | No verificable públicamente | Sí (binario/JSON/XML/KV/YAML) | Sí (packagers XML / specs YAML) | Sí (neaPay: ISO8583/XML/JSON/ISO20022/SWIFT/TLV/CSV) | Ninguno relevante al alcance actual |
| Bitmap visible | IMPLEMENTADO | No verificable públicamente | Sí | Estándar | Estándar | Ninguno |
| RAW/HEX con enmascarado forzado | IMPLEMENTADO (diferencial) | No verificable públicamente | Vista hex, sin evidencia de enmascarado forzado equivalente | No documentado | No documentado | Sibu por delante — no hay evidencia pública de un guard equivalente |
| Variables/datos dinámicos por campo | IMPLEMENTADO (alcance mínimo) | Mención pública de "uso de variables", sin detalle de spec | No verificable públicamente | jPOS-EE: scripting BeanShell por campo (`!campo`) | No verificable públicamente | jPOS usa scripting de propósito general; Sibu usa una tabla cerrada de variables — decisión de diseño, no carencia (ver ARCH-006) |
| Secuencias / flujos multi-MTI | DISEÑADO | No verificable públicamente | No verificable públicamente | jPOS-EE corre suites con múltiples send/receive | isosim guarda "test cases" | Gap real, en diseño (Fase C) |
| Host simulator con reglas condicionales | PARCIAL | No verificable públicamente | Sí (host simulator dedicado) | isosim permite reglas vía UI/standalone | — | Gap real, en diseño (Fase D) |
| Modo proxy | NO IMPLEMENTADO | No verificable públicamente | Sí | No verificable públicamente | neaPay: client/server/proxy | Gap real, sin caso de uso urgente para el alcance actual |
| Regresión: suites + comparación histórica | IMPLEMENTADO (diferencial) | No verificable públicamente | No verificable públicamente | No verificable públicamente | neaPay: regresión automática pass/fail, sin evidencia de comparación corrida-contra-corrida equivalente | Sibu por delante en este punto específico |
| Integración CI | IMPLEMENTADO | No verificable públicamente | No verificable públicamente | — | neaPay: Azure/AWS/Bitbucket; JMeter-ISO8583 en cualquier pipeline con JMeter | Ninguno relevante |
| Load testing | NO IMPLEMENTADO (diseñado) | No verificable públicamente | Con motor de carga | JMeter-ISO8583 plugin | bassrehab/ISO8583-Simulator (150-180k TPS reportado), neaPay (1000+ TPS) | Gap grande, correctamente diferido a Fase F |
| EMV | NO IMPLEMENTADO | No verificable públicamente | Sí (ARQC/TC, SDA/DDA, ATR) | — | bassrehab/ISO8583-Simulator: soporte de Field 55 | Gap grande, fuera de alcance actual (Fase G, muy tardía) |
| Cripto/HSM | NO IMPLEMENTADO | No verificable públicamente | Sí (PIN/MAC/DUKPT/TR-31/AES/3DES/RSA) | — | — | Gap grande, deliberadamente fuera de alcance por ahora (Fase H) |

**Fuentes públicas** (Agente 8): community.developer.visa.com, scribd.com (VTS User Guide,
mención general), en.wikipedia.org/wiki/ISO_8583, neapay.com (3 páginas), iso8583.studio,
github.com/hpkaushik121/Iso8583studio, jpos.org y su repositorio (`jPOS`/`jPOS-EE`),
github.com/tilln/jmeter-iso8583, github.com/bassrehab/ISO8583-Simulator,
github.com/rkbalgi/isosim, github.com/rkbalgi/keedoh, github.com/adelbs/ISO8583,
github.com/fedorov-iv/iso-test-tool, github.com/moov-io/iso8583-connection,
openhub.net/p/isoapui8583.

---

## 4. Identidad funcional de SibuTestLab

> **SibuTestLab es un laboratorio ISO 8583 orientado a QA de pagos: permite construir,
> inspeccionar, simular y someter a regresión histórica transacciones 0100/0110 con trazabilidad
> completa de cada campo, sin depender de especificaciones propietarias de marca ni de
> herramientas comerciales cerradas.**

Esta definición decide, explícitamente:

- **Entra:** construcción gobernada por perfil, inspección campo a campo (isoscopio), variables
  para reducir repetición manual, simulación de host configurable, regresión con historial
  comparable entre corridas, CLI apto para CI.
- **No entra (por ahora):** todo lo que exige una especificación de marca real (EMV, cripto de
  producción, catálogos Visa/Mastercard), todo lo que convierte el proyecto en una plataforma
  multiusuario/SaaS antes de que el alcance académico lo pida, y cualquier motor de scripting de
  propósito general (Sibu resuelve variabilidad con una tabla cerrada, no con un lenguaje).

---

## 5. Estado de Fase A — Variables dinámicas

**Clasificación: COMPLETA**, para el alcance declarado. Integrada a `main` (commit de merge
`1c8c95c` sobre `14bcf86`, rama `feature/variables-dinamicas-fase-a` conservada para
trazabilidad de auditoría — no borrada).

### Auditoría realizada antes de integrar

Preguntas respondidas contra el código real (no contra el diseño en abstracto):

1. **¿La gramática es suficientemente cerrada?** Sí: `^\{\{\s*[a-z][a-z0-9_]*\s*\}\}$`, sin
   paréntesis, comillas, puntos ni barras. Verificado con `TestPayloadsAdversariales` en
   `tests/test_variables.py`.
2. **¿Puede aparecer template injection?** No: no hay motor de plantillas de terceros, la
   resolución es un `dict[str, Callable]` cerrado (`_VARIABLES_BUILTIN`), nunca `eval`/`exec`.
3. **¿Puede acceder a environment/filesystem?** No: `ContextoResolucion` es un dataclass cerrado
   con exactamente 3 campos (`monto`, `stan`, `momento`); ninguna variable built-in lee
   `os.environ` ni abre archivos.
4. **¿La resolución es determinista?** Sí: función pura sobre el contexto recibido, sin reloj
   propio, sin generador de STAN propio (los recibe).
5. **¿Dónde se resuelve cada variable?** Exactamente en dos puntos:
   `application/orquestador.py::ejecutar_compra` (antes de `armar_compra`, con el STAN/momento
   reales) y `application/vista_previa.py::construir` (con `STAN_MARCADOR`).
6. **¿Qué significa preview vs. ejecución para `{{stan}}`?** En preview resuelve contra el
   marcador `000000` y se marca `es_valor_definitivo=False`; en ejecución real resuelve contra el
   STAN real de esa transacción, verificado con
   `test_orquestador_resuelve_stan_dinamico_igual_al_stan_real`.
7. **¿Qué queda persistido?** La ejecución persiste el valor YA RESUELTO (como cualquier otro
   campo). Un escenario guardado persiste la EXPRESIÓN sin resolver (verificado con
   `test_valores_efectivos_editables_congela_la_expresion_sin_resolverla`).
8. **¿El histórico puede explicar qué valor terminó resolviéndose?** Parcialmente: la ejecución
   muestra el valor resuelto dentro del mensaje transmitido (isoscopio), pero no hay un campo
   explícito "esto vino de `{{stan}}`" en el historial — limitación conocida, no bloqueante para
   el alcance actual (el valor resuelto ES visible, solo no está anotado como derivado).
9. **¿Qué pasa ante variable desconocida?** `VariableDesconocida`, con el nombre en el mensaje.
10. **¿Qué pasa con expresiones parciales?** `ExpresionMalformada` — nunca se trata como literal
    ni se interpola parcialmente (`ABC{{stan}}`, `{{stan}}XYZ`, `{{stan` sin cerrar, `{{}}`
    vacío, todos rechazados explícitamente).
11. **¿Qué pasa si un campo mezcla literal + variable?** Se rechaza (`ExpresionMalformada`): la
    gramática decide explícitamente que "todo el campo es una expresión o no lo es", nunca una
    interpolación parcial dentro de un literal mayor.

### Límite de alcance verificado (no supuesto)

- Variables funcionan en campos **editables** (3/22/37/41/49) sin problema.
- Variables en campos **opcionales** (18/25/32/42/43) hoy se **rechazan** en la capa web
  (`validar_forma_de_opcionales` valida la forma del valor SIN resolver, antes de que la
  resolución entre en juego). Extender a opcionales es trabajo de una entrega posterior, no de
  esta.
- Namespaces (`card.*`, `terminal.*`), variables de usuario y `{{previous.*}}` funcional:
  explícitamente fuera de esta entrega (ver Fase A2, sección 6).

### Tests y verificación final

`tests/test_variables.py`: 37 casos. Suite completa: 1101 passed, 2 skipped (1103 recolectados).
Guardia de PAN en verde. `git diff --check` limpio. `HEAD == origin/main` confirmado tras push.

---

## 6. Roadmap de fases

Cada fase indica objetivo, valor funcional, prerrequisitos, riesgos, criterio de aceptación y qué
NO se implementa en esa fase. Las fases no son una promesa de calendario: son bloques ejecutables
en el orden de menor riesgo/mayor valor, sujeto a reordenarse si la evidencia (como ARCH-004) lo
justifica.

### Fase A — Variables dinámicas · **COMPLETA** (built-ins, campos editables)

Ver sección 5. Subfase pendiente, no iniciada:

**Fase A2 — Namespaces y variables no-editables**
- Objetivo: `{{card.pan_enmascarado}}`, `{{terminal.id}}`, extender a campos opcionales.
- Prerrequisito: ninguno técnico bloqueante; decisión de producto de si vale la pena antes de
  Fase C (Secuencias también quiere leer del resultado de un paso anterior, un contrato afín).
- Riesgo: namespaces con punto amplían la gramática — debe seguir siendo una tabla cerrada, nunca
  un lenguaje de plantillas (ver ARCH-006, ya resuelto en el diseño original de Agente 1).
- Criterio de aceptación: gramática con puntos sigue rechazando cualquier cosa que no calce
  exactamente; suite verde; ninguna variable nueva expone el PAN completo.
- NO se implementa: `{{previous.*}}` funcional (eso es Fase C), aritmética, filtros.

### Fase B — Modelo multi-MTI

**Objetivo:** desacoplar el núcleo de "compra 0100" exclusivamente, sin duplicar
`armar_compra`/`armar_retiro`/`armar_reverso`/... como funciones paralelas que repitan la misma
infraestructura.

**Autorización de alcance:** formalizada en `PROYECTO.md` sección 0.1 (2026-09-12, ver también
`CLAUDE.md`). El prerrequisito bloqueante de esta fase (decisión explícita de ampliar alcance)
está resuelto.

**Diseño original** (Agente 2, jornada del 2026-09-11/12, sin código): introducir
`ClaveOperacion = (mti, codigo_proceso_prefijo | None)` como tercer eje ortogonal a
`MetadatoCampo` (forma) y `PoliticaCamposMti` (gobierno).

**Revisado y CORREGIDO contra el código real en B1.1 (2026-09-12, 4 agentes de solo lectura):**
`ClaveOperacion` **no se implementó** — no está justificado por el código actual. Evidencia:
`CODIGO_PROCESO_COMPRA` es hoy un valor por defecto de un campo editable (DE3), no parte de
ninguna clave de política; `PerfilDeMarca.politica(mti)`/`PoliticaCamposMti` **ya son genéricos**
(reciben `mti` como parámetro libre, `politica_por_mti` ya es un mapa extensible) sin necesitar
ningún eje nuevo. Introducir `ClaveOperacion` sin un segundo caso real que lo necesite hubiera
sido la abstracción prematura que el propio diseño original advertía evitar en otras partes.
Este es un ejemplo documentado de "usar el diseño de los agentes como referencia, no como
mandato": la investigación de código real (B1.1) primó sobre el documento de diseño previo.

**B1 — implementado** (rama `feature/multi-mti-b1-core-generico`, ver sección 5 para el
checkpoint completo): extraído `Orquestador._ejecutar` genérico (RN-4, codec, transporte,
RN-3/RN-1, registro), que no conoce `DatosCompra` ni `armar_compra` — recibe un `MensajeIso` ya
armado más `card_id`/`monto` para trazabilidad. `ejecutar_compra` queda como el único llamador,
concentrando lo específico de compra (tarjeta, variables, `armar_compra`). `domain/armado.py`
**no se tocó**: `armar_compra` sigue siendo legítimamente específico de compra (deriva DE2/DE14/
DE4), generalizarlo hubiera sido el antipatrón "mega builder". `domain/validacion.py::
mti_de_respuesta` (antes privada) se expuso como pública porque ahora tiene un segundo llamador
real fuera del módulo — el único símbolo de esta jornada que se renombró, con justificación
puntual, no un rename masivo.

**Subfases restantes** (orden sujeto a revisión — B1 demostró que el diseño original necesitaba
corrección antes de implementarse, así que B2 debe volver a verificarse contra código antes de
escribirse, no asumirse):

| Subfase | Objetivo | Depende de | Riesgo |
|---|---|---|---|
| B1 | Núcleo genérico del Orquestador | — | **COMPLETO**, ver checkpoint sección 5 |
| B2 | Primer MTI adicional real: Echo 0800/0810 (sin tarjeta, sin monto) | B1 | **COMPLETO** |
| B3 | Escenarios/suites/CLI genéricos para Multi-MTI; Echo gana el ciclo completo (escenario/suite/reintento/export) | B2 | **COMPLETO** |
| B4 | 0200/0210 compra financiera real (primer MTI con tarjeta y monto además de 0100) | B3 | **COMPLETO**, integrado a `main` (`1998491`) |
| B5 | Editor común de operaciones con tarjeta (`OperacionIso`, unifica Autorización/Compra financiera) | B4 | **COMPLETO**, integrado a `main` (`07b69f3`) |
| B6 | Modelo conceptual de operación derivada (origen→derivada, futuro reverso), SIN 0400/0410 todavía | B5 | **COMPLETO**, integrado a `main` (`7c034ed`), ver reporte de checkpoint (sección 8) |
| B7 | Reverso interactivo real (0400/0410), iniciado desde Historial sobre una 0200 aprobada | B6 | **COMPLETO**, integrado a `main` (`6a31ce3`), ver reporte de checkpoint (sección 9) |
| B8 | Aviso de reverso real (0420/0430), segunda operación derivada, iniciado desde Historial sobre una 0200 aprobada; primera secuencia `0200 → 0420` real usando el motor de C1/C2 | B7, C1, C2 | **COMPLETO** en rama, ver reporte de checkpoint (sección 12) |

**Nota (2026-09-13):** la numeración original de subfases (B2=0800, B3=0200 con variantes de
DE3, B4=reversos) se ajustó contra la ejecución real: B2 pasó a ser Echo puro, B3 absorbió el
trabajo de escenarios/suites/CLI genéricos que el diseño original no había separado, B4 fue
0200 financiera, B5 se agregó (no estaba en el diseño original: unificar el editor antes de que
un tercer MTI con tarjeta duplicara la misma UI), y B6 tomó el lugar que el diseño original le
daba a "B4 — reversos", pero limitado deliberadamente al modelo conceptual (origen→derivada),
sin construir 0400/0410 todavía — ver sección 8.

**Criterio de aceptación de cada subfase:** suite verde, cero cambio de comportamiento para
0100/0110 existente, escenarios/suites/historial de compra sin migración de esquema (verificado
en B1.1 contra el esquema real, no asumido: `escenarios.mti` y `ejecuciones.mti_solicitud`/
`mti_respuesta` ya son `TEXT` libre sin `CHECK`/`FK`).

**Hallazgo pendiente para B2 (no corregido en B1, deliberadamente — fuera del alcance de "núcleo
del Orquestador"):** `application/escenarios.py` valida expectativas contra el literal
`MTI_RESPUESTA_COMPRA` en 3 lugares, en vez de derivarlo de `self._mti` (que ya es inyectable).
Mientras `ServicioEscenarios` solo se use con compra, esto es inocuo; B2 (el primer MTI real con
escenarios) debe corregirlo antes de admitir escenarios de un MTI distinto de compra.

**Hallazgo menor, no bloqueante:** `domain/modelos.py::Escenario.a_datos_compra()` es código
vestigial — ningún llamador lo invoca (`ejecutor_escenarios.py` reconstruye `DatosCompra` a mano
en su lugar). No se tocó en B1 (evitar scope creep); candidato a limpieza en B2 o antes, sin
prisa.

**Nota arquitectónica de seguridad — condición de entrada explícita para B2 (ARCH-001/SEC-001,
investigada en B1.1, agente de solo lectura dedicado):**

`CAMPOS_SENSIBLES` (`domain/modelos.py:23`, `frozenset({"2","35"})`) es hoy la **única** fuente
operativa de "qué campo es sensible" — consultada directamente por 6+ módulos (`codec.py`,
`expectativas.py`, `validacion.py`, `serializacion.py`, `presentacion.py`, `modelos.py` mismo).
`MetadatoCampo.sensible` (`domain/campos_iso.py:45`) existe con la forma correcta pero está
**inerte**: en `profiles/generico.py` todas las instancias pasan `sensible=False` literal, y
ningún módulo lo lee para ninguna decisión de seguridad — los campos 2/35 ni siquiera tienen
`MetadatoCampo` propio (son `derivados`, nunca editables). Esto NO es un defecto activo hoy
(los guardias de seguridad ya son agnósticos de MTI, no dependen de que exista un segundo perfil)
y **B1 no lo empeora** (no se introdujo ningún perfil/MTI nuevo). Pero es la condición de entrada
explícita antes de exponer un perfil arbitrario en B2+: la sensibilidad debe pasar a gobernarse
por metadata del perfil (`MetadatoCampo.sensible`, poblado de verdad y leído por los 6+ módulos
que hoy importan la constante global), no por una constante de dominio que asume un único perfil.
Un test de "sincronización" entre ambas fuentes sería cosmético mientras `MetadatoCampo.sensible`
no tenga ningún consumidor real — se pospone a cuando B2 haga esa migración.

**Actualización (B2, 2026-09-13): resuelto PARCIALMENTE, corrección mínima sin debilitar ninguna
guardia existente.** Se agregó `profiles/generico.py::METADATOS_SENSIBLES` — una declaración
explícita, por campo, de qué transporta datos sensibles (hoy solo DE2/PAN; DE35 no tiene entrada
en `ESPECIFICACION_GENERICA` en absoluto, así que no hay nada que declarar todavía para Track 2) —
más una prueba nueva (`test_todo_campo_declarado_sensible_tiene_autoridad_en_camposensibles`) que
falla si algún campo declarado `sensible=True` ahí llegara a faltar en `CAMPOS_SENSIBLES`. Esto
le da a la metadata una autoridad real y verificada: ya no es un campo inerte, es la fuente
declarativa contra la que se contrasta el enforcement.

**Lo que NO se hizo, deliberadamente, y queda como deuda explícita para B3:** los 6+ consumidores
de `CAMPOS_SENSIBLES` (`codec.py`, `expectativas.py`, `validacion.py`, `serializacion.py`,
`presentacion.py`, `modelos.py`) siguen leyendo la constante global de `domain/modelos.py`, no
`METADATOS_SENSIBLES` directamente — en particular, `MensajeIso.enmascarado()` no recibe un
`perfil` como parámetro hoy, y agregarlo sería un cambio de firma que toca código de seguridad
crítico en muchos call sites a la vez. Esa migración completa (perfil→sensibilidad real en cada
guardia) es la que de verdad cerraría ARCH-001/SEC-001 para un perfil arbitrario en B3+; lo hecho
en B2 es la base declarativa y la prueba de regresión, no la migración completa. Ninguna guardia
existente se tocó ni se debilitó.

**NO se implementa en Fase B:** ningún catálogo de "tipos de operación" con nombres de negocio
(retiro, transferencia) como enum de dominio — eso sería inventar semántica de marca, prohibido
por `CLAUDE.md`. Ningún MTI nuevo expuesto desde la UI todavía.

### Fase C — Secuencias

**Objetivo:** escenarios compuestos (paso 1 → captura → paso 2 → ...), reutilizando el motor de
variables (Fase A) para el contrato de contexto entre pasos.

**Diseño ya disponible** (Agente 3, sin código): `Secuencia`/`PasoSecuencia` como nivel de
agrupación por ENCIMA de `Escenario` (nunca lo reemplaza); `depende_de`/`captura` con validación
de ciclos por comparación de `orden` (más simple que un DAG general, suficiente porque los pasos
ya son una lista ordenada); reutiliza `EstadoItemCorrida`/`calcular_resultado_global` tal cual,
sin inventar un enum nuevo de estados.

**Nota de secuenciación (ARCH-004):** la infraestructura base (C1) no requiere que Fase B esté
completa — el propio diseño usa dos pasos 0100→0100 para su entrega mínima. Solo el caso de uso
con valor de negocio real (0100→0200→0420) requiere Fase B completa. Puede evaluarse adelantar C1
en paralelo a B si conviene por capacidad disponible.

**Subfases:**

| Subfase | Objetivo | Depende de | Estado |
|---|---|---|---|
| C1 | Infraestructura mínima: `Secuencia`/`PasoSecuencia`, `ContextoSecuencia`, tablas nuevas, secuencia de 2 pasos DEPENDIENTES, sin CONTINUE_ON_FAILURE, sin retries, sin timeout de secuencia | Fase B (B6/B7 ya completas) | **COMPLETO**, integrado a `main` (`989991e`) |
| C2 | Variables entre pasos (`{{step.<id>.request\|response.deNN}}`, `{{step.<id>.execution_id}}`) | C1 | **COMPLETO**, integrado a `main` (`04372ba`) |
| C3 | Política de continuación (STOP/CONTINUE) ante ERROR/FAIL QA, expectativas dinámicas, retry mínimo seguro (exclusivo de Echo) | C1, C2, B8 | **COMPLETO** en rama, ver reporte de checkpoint (sección 13) |
| C4 | Comparación de corridas de secuencia (equivalente a `comparacion_corridas.py`) | C1, al menos una corrida real que comparar | Planificado |

**Nota (B8, 2026-09-14):** el motor de C1/C2 ya soporta una segunda operación derivada (aviso de
reverso, 0420/0430) dentro de un paso derivado -`PasoSecuencia.operacion_derivada`-, probada con
una secuencia real `0200 → 0420`. Esto NO era una subfase de Fase C separada: fue una extensión
mínima del mismo mecanismo de C1 (`_ejecutar_paso_derivado` pasó de invocar un único método fijo
del `Orquestador` a despachar entre dos, según el campo nuevo), sin tocar `ContextoSecuencia` ni
el motor de variables de C2. Ver checkpoint B8, sección 12.

**Actualización (C1, 2026-09-13): implementada, revisada contra el código real -no contra el
diseño original de Agente 3-.** Decisión de orden del propietario: C1 se hizo **después** de B7
(reverso interactivo real), no antes ni en paralelo -al contrario de lo que ARCH-004 permitía-,
porque B6/B7 ya alcanzaban para demostrar el primer caso de uso real (compra financiera →
reverso) sin necesitar secuencias todavía; C1 automatiza ese mismo caso, no lo inventa.

Diferencias reales contra el diseño de Agente 3: **no se implementó `ContextoPaso` genérico ni
`depende_de`/`captura`** -en su lugar, `PasoSecuencia.origen_tipo` (`independiente`/`derivado`) +
`origen_paso_orden`, y `ContextoSecuencia` con una API mínima (`registrar`/`ejecucion_id_de`),
suficiente para el único caso real de C1 (un paso deriva de la ejecución de otro vía
`ejecucion_origen_id`/`ReferenciaEjecucion`, B6/B7 reutilizados tal cual). Las tablas nuevas se
llaman `secuencias_transaccionales`/`secuencia_transaccional_pasos`/`corridas_secuencia`/
`corrida_secuencia_pasos` -no `secuencias`/`secuencia_pasos`- porque `secuencias` ya es el nombre
de la tabla del contador de STAN, sin ninguna relación con este concepto (hallazgo del Agente B
de la investigación de C1, evitado antes de escribir el DDL). `EstadoItemCorrida`/
`calcular_resultado_global` SÍ se reutilizaron como vocabulario -no la clase entera-: se creó
`EstadoPasoSecuencia` (mismos PASS/FAIL/ERROR/SIN_EXPECTATIVAS/NO_EJECUTADO + `BLOQUEADO`, el
único estado nuevo) y `calcular_resultado_global_secuencia`, que devuelve el mismo
`ResultadoGlobalSuite` de siempre. Detalle completo del checkpoint en la sección 10.

**Riesgo documentado:** un campo capturado (`captura`) debe validarse contra `CAMPOS_SENSIBLES`
al guardar la secuencia — mismo criterio que ya usa `campos_permitidos_expectativa` — para que
ningún dato de tarjeta quede expuesto a interpolación entre pasos (relacionado con ARCH-001).

**NO se implementa en Fase C:** ramas condicionales (if/else entre pasos), paralelismo entre
pasos de un mismo flujo, ni un DSL completo de scripting.

### Fase D — Host Simulator 2.0

**Objetivo:** reglas declarativas por contenido de solicitud, en vez de un único comportamiento
global fijo.

**Diseño previo** (Agente 4, jornada anterior, sin código): motor de reglas en YAML, sin
persistencia ni UI en ninguna subfase. **Superado explícitamente por el propietario al abrir D1**
(2026-09-14): D1 pasó a incluir modelo + matching + persistencia SQLite + UI + integración con
`HostSimulado`, en un solo bloque -ver checkpoint D1, sección 14, punto B, para el detalle de la
decisión-. Las subfases D2/D3 de abajo quedan como estaban, sin tocar todavía.

**Prerrequisito bloqueante (D0):** QA-002 (agregar test dedicado para `adapters/host_simulado/
cli.py` antes de modificarlo) — **CERRADO**, ver tabla de fases arriba (`D0 — cobertura de
host_simulado/cli.py`, IMPLEMENTADA).

**Subfases:**

| Subfase | Objetivo | Depende de |
|---|---|---|
| D0 | Cerrar QA-002: test de `_argumentos()` de `cli.py`, sin ningún cambio de comportamiento | Ninguno — puede hacerse ya, independiente de esta fase |
| D1 | Modelo de reglas (`domain/reglas_host.py`), matching, persistencia SQLite, integración con `HostSimulado`, UI, migración de la regla sintética existente | D0 |
| D2 | Estado limitado por regla (`max_aplicaciones`/contador de aplicaciones, atomicidad real), integración con el retry de C3 sin doubles | D1 |
| D3 | `visto_antes` (duplicados, con estado más general) y los modos de falla que todavía no requieren estado y no se cubrieron en D1/D2 (`bytes_invalidos`, remapeo de campo en `copiar`, regex/rangos combinados si hay necesidad demostrable) | D2 |

**Confirmado por el diseño:** ninguno de los 5 fallos simulados requiere cambios en el lado
cliente — `TiempoAgotado`, `FalloDeTransmision`, `ErrorDeDecodificacion`→`INVALIDA`, `RECHAZADA`
vía catálogo ya cubren los 5 casos.

**NO se implementó en D1:** regex/rangos combinados, prioridad por especificidad, remapeo de
campo en `copiar`, reglas con estado (`visto_antes`/contadores), respuesta ISO malformada
arbitraria, proxy, load, EMV, crypto -ver checkpoint sección 14 para el detalle completo-.

### Fase E — Client / Server / Proxy

**Objetivo:** modo proxy (observación/captura entre un cliente real y un switch), con las mismas
garantías de seguridad que ya aplica el resto del proyecto (nunca PAN completo fuera del ámbito
transaccional).

**Estado:** sin diseño propio producido en esta jornada (ningún agente lo cubrió en detalle más
allá de mencionarlo como gap competitivo, sección 3). Requiere un documento de diseño dedicado
antes de cualquier código — mismo criterio que las fases anteriores.

**NO se implementa hasta tener ese diseño.**

### Fase F — Performance Lab

**Objetivo:** motor de carga (TPS, concurrencia, ramp-up/down, percentiles).

**Diseño ya disponible** (Agente 9, sin código): reutiliza `Orquestador.ejecutar_compra` y
`Composicion.orquestador` sin modificarlos; concurrencia vía `asyncio.Semaphore` + pacing simple
(`asyncio.sleep(1/tps)` para la primera entrega, token bucket completo después); percentiles
calculados en memoria (ordenar una vez, indexar por posición), nunca vía SQL agregado.

**Requisito de diseño incorporado de PERF-001 (bloqueante):** no persistir cada transacción de
carga en la ruta caliente vía `RepositorioEjecucionesSQLite.guardar` (commit por fila) — acumular
en memoria y volcar en lotes o al cierre, o aceptar explícitamente el techo de TPS que impone
SQLite si se decide persistir por transacción.

**Prerrequisito:** transporte y tipos de mensaje maduros (al menos Fase B en un estado estable) —
un motor de carga sobre un núcleo todavía cambiando de forma no mide nada estable.

**Primera entrega mínima propuesta por el diseño:** comando `sibu-carga run --tps N --duracion
S --escenario ID`, sin ramp-up/down, un semáforo de concurrencia fija, un solo escenario/mix fijo,
resultados en memoria, reporte final con avg/min/max/p50/p90/p95/p99.

**NO se implementa en la primera entrega:** pool de conexiones TCP reutilizables (no hace falta
para el MVP), ramp-up/ramp-down, transaction mix ponderado, persistencia por lotes, UI web.

### Fase G — EMV / Field 55

**Objetivo:** TLV parser/builder para DE55. Sin criptografía todavía (eso es Fase H).

**Estado:** sin diseño propio producido en esta jornada. Requiere documento de diseño dedicado.

### Fase H — Crypto / HSM

**Objetivo:** PIN block real, MAC, DUKPT/TR-31. Mucho después de G.

**Estado:** sin diseño. `TarjetaPrueba.pin_block_laboratorio` (PARCIAL, ver sección 2) es
explícitamente NO criptográficamente válido — Fase H empezaría desde cero en este aspecto, no
extendiendo ese campo.

### Fase I — Productización

**Objetivo:** Docker, PostgreSQL, usuarios, organizaciones, roles, secretos, audit log, on-prem,
SaaS.

**Diseño ya disponible** (Agente 10, sin código): tabla completa de 9 escalones (single-user
local → multi-user → on-prem → Docker → PostgreSQL → organizaciones/roles → secretos → audit log
→ SaaS), con la recomendación explícita de **quedarse en el escalón actual (single-user local)**
para el alcance de este proyecto académico, y usar el documento únicamente como evidencia de "hoja
de ruta y retorno".

**Confirmado (PROD-001):** la arquitectura de puertos ya permite migrar a PostgreSQL sin tocar
`domain/`/`application/` — un adaptador nuevo en `adapters/persistence/`, nunca un refactor.

**NO se implementa nada de Fase I** salvo que el alcance del proyecto cambie explícitamente (fuera
del criterio de este roadmap).

---

## 7. Próximo bloque exacto

**Decisión del propietario (2026-09-13):** Fase C (Secuencias) NO se adelanta antes de un
reverso manual — B6 ya permite construir una operación derivada a partir de una ejecución
histórica concreta, y eso alcanza para un reverso **interactivo**, iniciado por una persona desde
Historial. Secuencias sigue siendo necesaria más adelante, mas no como prerrequisito de B7.
Orden aprobado: B6 → **B7 (reverso interactivo 0400/0410, completo — ver sección 9)** → Fase C
(secuencias/contexto entre pasos) → 0420/0430 y automatización de reversos (B8, ver sección 6).

**Próximo bloque:** **C2 (propuesta) — Variables entre pasos (`{{step.N.campo}}`) y
CONTINUE_ON_FAILURE/retries/timeout de paso**, o alternativamente **0420/0430 sobre el motor de
secuencias ya construido (C1, sección 10)** — ambas opciones están disponibles; la decisión de
cuál seguir es del propietario (ver sección 10.N).

Alternativa independiente: **D0 — cerrar QA-002** (test dedicado para
`adapters/host_simulado/cli.py`).

## 8. Checkpoint B6 — Modelo de operación derivada (reversos, sin 0400/0410)

**Estado: COMPLETO para el alcance acordado.** Rama `feature/multi-mti-b6-reversal-model`,
commits `53964b5` (B6.1 persistencia), `736dccd` (B6.2 elegibilidad + referencia segura),
`c9b68e9` (B6.3 UI de historial). Sin mergear a `main`, pendiente de aprobación del propietario.

**A. Punto de partida:** B5 integrado a `main` en el merge `07b69f3`, suite verde (1245
passed, 2 skipped) antes de abrir B6.

**B. Investigación previa al diseño (4 agentes de solo lectura, sin código):** Agente A (dominio
ISO 8583 público: un reverso correlaciona con el original por DE11/DE37/DE38/DE90, monto y
terminal — nunca solo por STAN, que puede repetirse entre lotes/días); Agente B (auditoría de
`ejecuciones`/FKs/snapshots/corridas: ninguna tabla tenía relación origen→derivada, `escenario_id`
ya establecía el precedente de "puntero de navegación, no fuente de datos" que B6 reutilizó);
Agente C (coexistencia con Secuencias futuras: la abstracción debía ser reusable para
`{{previous.*}}` sin comprometerse a esa sintaxis todavía); Agente D (qué es seguro heredar de una
ejecución: nunca PAN/Track1/Track2/RAW, sólo snapshot whitelisted).

**C. Modelo elegido:** `Ejecucion.ejecucion_origen_id: int | None`, autorreferencial, nullable,
1 origen → N derivadas (sin restricción de unicidad). Se prefirió sobre alternativas (tabla de
relación aparte, o correlacionar por STAN/RRN) porque el propio RN-3 ya demuestra que STAN/RRN no
son estables como identidad — ver punto H.

**D. Persistencia:** migración aditiva (`ALTER TABLE ejecuciones ADD COLUMN
ejecucion_origen_id INTEGER REFERENCES ejecuciones(id)`, sin índice — mismo criterio que las demás
columnas migradas, para no romper `inicializar()` contra bases viejas). Se detectó y corrigió un
bug real: el rebuild legado `_migrar_ejecuciones_card_id_nullable` (para bases anteriores a B2)
tenía una lista de columnas y un DDL de tabla temporal hardcodeados que no incluían la columna
nueva, así que en una base suficientemente vieja el rebuild borraba silenciosamente lo que la
migración de B6 acababa de agregar — corregido antes de integrar. Aplicada además contra la base
real de desarrollo (no solo fixtures): backup `sibutestlab8583.db.bak-preB6-20260913-140615`,
62 filas antes y después, `PRAGMA foreign_key_check` vacío, migración re-ejecutada una segunda vez
para confirmar idempotencia.

**E. Elegibilidad (`domain/elegibilidad_reverso.py::puede_generar_operacion_derivada`):** hoy
`True` únicamente para 0200 (compra financiera) en estado `APROBADA`. Justificación por MTI: 0100
(autorización, sin movimiento de fondos) queda deliberadamente fuera — un reverso existe para
deshacer un cargo, y 0100 no mueve fondos en este laboratorio; Echo 0800 no transporta tarjeta ni
monto, no aplica. Justificación por estado: una 0200 **rechazada** (DE39=51 u otro) no movió
fondos, así que no hay nada que revertir — regla explícita, documentada como comportamiento del
perfil genérico de laboratorio, sin afirmar nada sobre el comportamiento de una marca real.

**F. Snapshot seguro (`application/referencia_ejecucion.py::ReferenciaEjecucion`):** construida
exclusivamente a partir de `DetalleEjecucion` (el snapshot ya persistido) — la firma de
`referencia_desde_detalle` tiene un solo parámetro, verificado con `inspect.signature` en test,
precisamente para que no pueda colarse una lectura en vivo del escenario o el perfil vigente
(punto 5 del checkpoint). Campos de respuesta whitelisted: `CAMPOS_REFERENCIA_RESPUESTA =
{"37","38"}` (DE37/DE38); nunca copia el mensaje completo.

**G. Seguridad:** `tests/test_referencia_ejecucion.py` incluye una prueba adversarial que
concatena todos los valores de la referencia (incluidos los campos whitelisted) y confirma que el
PAN real jamás aparece como substring; `card_id` se usa en vez del PAN. `elegibilidad_reverso.py`
no recibe ni perfil ni catálogo — es una función pura sobre `Ejecucion`.

**H. RN-3 vs. el nuevo enlace histórico — dos conceptos separados, sin mezclar:**
  - **(A) Correlación de RN-3** (`domain/validacion.py`, `ARCH-005`): compara la solicitud contra
    su propia respuesta **dentro del mismo intercambio** (mismo STAN, mismo campo 11, evaluada
    antes que RN-1) — sigue intacta, B6 no la tocó.
  - **(B) Relación origen↔derivada** (`ejecucion_origen_id`, nuevo en B6): conecta **dos
    ejecuciones distintas en el tiempo**, nunca dentro de un mismo intercambio, y explícitamente
    NO depende de STAN/RRN (que pueden repetirse entre corridas) — usa la identidad interna
    (`id` de la fila), estable por construcción.
  Un futuro reverso real (B7) necesitará ambas: (A) para validar que la respuesta al 0400 que él
  mismo emita corresponda a su propia solicitud, y (B) para saber a qué ejecución original se
  refiere. Son ejes independientes; `ARCH-005` ya anticipaba que la correlación cruzada entre dos
  mensajes distintos necesitaría trabajo aparte — este es exactamente ese trabajo, limitado a la
  relación de datos, sin implementar todavía el mensaje 0400 en sí.

**I. Dependencia de Escenarios/Secuencias/Suites (sin implementar, solo documentada):** un
escenario de reverso futuro no debe fijarse a un `ejecucion_id` literal — debe expresar "necesita
una ejecución origen producida dentro del mismo flujo", lo cual solo tiene sentido una vez que
Fase C (Secuencias) exista como el mecanismo que produce ese contexto encadenado. Una operación
derivada tampoco entra a una Suite todavía por la misma razón. B6 registra esta dependencia
explícitamente para que C3 (`Secuencias con MTIs reales`, sección 6) la resuelva cuando llegue, en
vez de intentar un atajo (fijar IDs literales) que B6 decidió no construir.

**J. UI implementada (mínima, pasiva):** en `/historial/{id}`, un chip "Elegible para reverso"
(solo descriptivo, sin acción real detrás) y una sección "Operaciones derivadas" con navegación
bidireccional origen↔derivada — verificado con pruebas automatizadas (`tests/
test_historial_operaciones_derivadas.py`) y con una sesión de navegador real (0200 aprobada real
vía TCP contra `sibu-host-demo`, confirmando el chip; 0200 rechazada real confirmando que el panel
NO aparece). B6 no construye ningún formulario de 0400 ni ningún botón que finja ejecutar un
reverso.

**K. Tests:** suite completa 1266 passed, 2 skipped (1245 al cerrar B5 + 21 nuevos de B6: 6 de
migración, 8 de elegibilidad, 5 de `ReferenciaEjecucion`, 2 de historial/UI). `git diff --check`
limpio en cada checkpoint.

**Investigación DE90 (punto 9 del checkpoint):** confirmado por inspección directa que
`iso8583.specs.default` (la librería `pyiso8583`) SÍ declara el campo 90 (42 caracteres fijos,
"Original Data Elements"), pero `profiles/generico.py::ESPECIFICACION_GENERICA` (la especificación
propia de este proyecto) NO lo declara. Hallazgo documentado; DE90 no se agregó en B6 — se
agregará cuando B7 (reversos reales) lo necesite de verdad, no por anticipación.

**L. Commits de B6:** `53964b5` (B6.1), `736dccd` (B6.2), `c9b68e9` (B6.3).

**M. Estado explícito:** **Falta la decisión de Secuencias (Fase C, al menos C1) antes de B7**
si se quiere que un escenario de reverso futuro no dependa de IDs fijos — ver punto I. El modelo
de datos, la elegibilidad y el snapshot seguro para B7 (reversos 0400/0410) ya están listos y
probados; lo que falta para B7 es exclusivamente: el mensaje 0400/0410 en sí (armado, codec,
orquestador), la decisión sobre DE90, y la decisión de producto sobre Secuencias.

## 9. Checkpoint B7 — Reverso interactivo real (0400/0410)

**Estado: COMPLETO para el alcance acordado.** Rama `feature/multi-mti-b7-reversal-0400`,
commits `820bd5e` (B7.1 perfil), `cde3852` (B7.2 referencia+builder), `6f4f3f6` (B7.3
orquestador), `de0556b` (B7.4-B7.7 UI/preview/seguridad). Sin mergear a `main`, pendiente de
aprobación del propietario. Decisión de orden previa (2026-09-13): Secuencias NO se adelanta —
B6 ya alcanza para un reverso manual (ver sección 7).

**A. Integración B6:** confirmada antes de abrir B7 — `main`/`origin/main` en `7c034ed`,
suite 1268 passed en verde.

**B. Perfil 0400/0410** (`profiles/generico.py`): sin campos editables ni opcionales — un
reverso no es un constructor libre. Obligatorios de la solicitud `{3,4,7,11,41,49}` (DE37/RRN
queda fuera: el original pudo no haberlo tenido); de la respuesta `{3,4,7,11,39,41}`, mismo
criterio que 0210. DE4/DE37/DE41/DE49 declarados `derivados` (vienen de `ReferenciaEjecucion`,
nunca de texto libre); DE3/DE7/DE11 `automáticos` (datos nuevos de este intercambio). Ningún
campo ISO nuevo: 0400/0410 solo reutiliza números ya declarados en `ESPECIFICACION_GENERICA`.

**C. DE90:** investigado de nuevo con la composición exacta en mano (no solo "existe o no", como
en B6). Los primeros 31 caracteres (MTI+STAN+fecha/hora+adquirente) serían derivables de
`ReferenciaEjecucion` sin inventar nada; los últimos 11 (ID de institución receptora/forwarding,
DE33) no tienen ninguna fuente en este perfil — ni siquiera está declarado para ningún MTI.
Rellenarlos fabricaría un dato que el laboratorio no tiene. **Decisión: NO implementado**,
documentado en `profiles/generico.py` y `application/armado_reverso.py`. La correlación
origen↔reverso se apoya en DE37 (cuando existe) a nivel de protocolo y en
`Ejecucion.ejecucion_origen_id` a nivel de aplicación.

**D. Builder** (`application/armado_reverso.py::armar_reverso_financiero`): recibe
`ReferenciaEjecucion` + `stan_nuevo` + `momento_nuevo`, sin ningún parámetro de texto libre
(verificado por firma en test). Nuevos: DE3 (constante de laboratorio), DE7/DE11 (reloj/STAN de
este intercambio). Del original: DE4/DE41/DE49 siempre, DE37 solo si existía. STAN del reverso
≠ STAN original, verificado en `tests/test_armado_reverso.py` y en el E2E real. Revienta con
`ReferenciaOrigenIncompleta` si falta monto/moneda/terminal (no debería ocurrir para un origen
elegible real).

**E. Correlación — dos conceptos, sin mezclar:**
  - **0400↔0410** (RN-3 estándar, sin cambios): `domain.validacion`/`campos_de_correlacion` ya
    eran genéricos por MTI (B1); el host simulado los reutiliza sin ningún camino especial para
    0400 (confirmado — no fue necesario tocar `adapters/host_simulado/servidor.py`).
  - **0400↔0200 original**: `Ejecucion.ejecucion_origen_id` (B6), nunca STAN/RRN. No se introdujo
    ninguna `EstrategiaCorrelacion` nueva: los dos casos que ARCH-005 anticipaba como "correlación
    cruzada" resultaron ser el mismo mecanismo de B6, no uno nuevo — no había un segundo
    comportamiento real que justificara la abstracción.

**F. Host simulado:** **CERO líneas tocadas.** `_construir_respuesta` ya derivaba el MTI de
respuesta genéricamente (B2) y su rama `else` (cualquier MTI con código explícito o default) ya
cubría 0400 sin necesitar una rama dedicada. Evidencia real: `tests/
test_orquestador_reverso_financiero.py` (0400→0410/00 por TCP real) y la sesión de navegador real
(ver I).

**G. Persistencia:** `ejecucion_origen_id` (columna de B6, sin migración nueva) se hiló a través
de `Orquestador._ejecutar`/`_registrar` (parámetro nuevo, `None` por defecto — cero cambio de
comportamiento para compra/echo/financiera). 1 origen → N derivadas confirmado con dos reversos
reales sobre la misma 0200 (test y navegador). Original releída de la base tras el reverso:
estado, STAN y monto intactos.

**H. Seguridad:** `tests/test_seguridad_reverso_financiero.py` confirma que el PAN nunca aparece
en la vista previa, en el resultado ni en el detalle del reverso; que DE90 no aparece en ningún
lado (documentando la decisión de C); que el reverso persiste por `card_id`, nunca duplicando el
PAN. Adversarial POST: un intento directo (sin pasar por "Crear reverso") contra un origen no
elegible o inexistente responde 404 sin generar STAN ni derivada — la elegibilidad se revalida
siempre dentro de `Orquestador.ejecutar_reverso_financiero`, nunca se confía en la web.

**I. UI:** Historial → 0200 aprobada → chip "Elegible para reverso" + botón "Crear reverso" →
`GET /historial/{id}/reverso` (preview: MTI, bitmap, RAW/HEX seguro, campos con su origen,
"Derivado de la ejecución #X" con monto/STAN original/RRN/código de autorización según
disponibilidad) → `POST /historial/{id}/reverso/ejecutar` → resultado (reutiliza
`resultado.html`) → navegación bidireccional real en `/historial/{id}`. Verificado con recorrido
manual completo en navegador real contra `sibu-host-demo` (0200 aprobada real, preview real,
0400/0410 real, navegación en ambos sentidos, segundo reverso 1→N, y una 0200 rechazada
confirmando que ni el botón ni la ruta directa `/historial/{id}/reverso` están disponibles).

**J. E2E:** `tests/test_orquestador_reverso_financiero.py::
test_reverso_real_desde_una_financiera_aprobada` — 0200→0210/00→0400→0410/00, TCP/codec/SQLite
reales, sin dobles.

**K. Arquitectura — métrica de reutilización (punto 30):** de los ~1370 líneas netas agregadas en
B7, la inmensa mayoría es específica del reverso por necesidad (perfil, builder, UI/preview,
tests) — no por duplicación. Cero condicionales especiales por MTI se agregaron a
`domain/validacion.py`, `Orquestador._ejecutar` ni `adapters/host_simulado/servidor.py`: los
cuatro ya eran genéricos desde B1/B2. Cero duplicación de plantilla: `resultado.html` se reutiliza
tal cual (parametrizado por `seccion="reverso"`); solo `reverso_preview.html` es nuevo, porque el
flujo previo a ejecutar genuinamente no existía para ninguna otra operación (sin selector de
tarjeta/monto/conexión). Cero duplicación de transporte, persistencia (`_registrar` extendido con
un parámetro, no reescrito) ni de correlación (RN-3 sin tocar). La única pieza nueva de
"infraestructura" real es `armado_reverso.py` + la extensión de `ReferenciaEjecucion` — ambas ya
anticipadas por B6. **Ninguna señal de dispersión de lógica preocupante**: agregar 0400 no forzó
tocar más de 2-3 módulos centrales (`Ejecucion`/`_ejecutar`/`_registrar` en orquestador, y nada
en dominio de validación/host). Esto sugiere que 0420/0430 (B8) sería, arquitectónicamente, un
incremento del mismo tamaño — el riesgo real de B8 es de producto (contexto entre pasos, Fase C),
no de acoplamiento de código.

**L. Tests:** 1268 passed al cerrar B6 → **1296 passed** al cerrar B7 (28 nuevos: 7 perfil, 7
builder, 7 orquestador/E2E, 4 web, 2 seguridad, 1 actualizado en `test_perfil_generico.py`). 0
skipped. `git diff --check` limpio en cada commit.

**M. Commits:** `820bd5e` (B7.1), `cde3852` (B7.2), `6f4f3f6` (B7.3), `de0556b` (B7.4-B7.7).

**N. Próximo paso — qué hace falta para Fase C (Secuencias):** nada de B7 lo bloquea ni lo
adelanta. Fase C (sección 6, C1) puede iniciarse de forma independiente en cualquier momento: su
entrega mínima (dos pasos 0100→0100) no depende de B7. Lo que SÍ depende de Fase C es **B8**
(0420/0430 y automatización de reversos dentro de escenarios/suites): un escenario de reverso
automatizado necesita expresar "usa la ejecución producida por el paso anterior", no un
`ejecucion_id` fijo — ese es exactamente el contrato que Secuencias (`ContextoPaso`,
`depende_de`/`captura`) está diseñada para dar. **No se avanza a 0420/0430 todavía.**

## 10. Checkpoint C1 — Secuencias transaccionales (infraestructura mínima)

**Estado: COMPLETO para el alcance acordado.** Rama `feature/secuencias-c1-core`, commits
`a81e080` (C1.1 modelo+persistencia), `e139522` (C1.2 contexto+ejecutor: 0200→0400 real),
`f52eaf5` (C1.3 UI mínima). Sin mergear a `main`, pendiente de aprobación del propietario.
Decisión de orden previa (ver sección 7): C1 se construyó DESPUÉS de B7, no antes ni en
paralelo — B6/B7 ya alcanzaban para el reverso manual; C1 lo automatiza dentro de un flujo de
dos pasos, sin inventar un segundo sistema de referencias.

**A. Integración B7:** confirmada antes de abrir C1 — `main`/`origin/main` en `6a31ce3`, suite
1296 passed/0 skipped en verde.

**B. Modelo de Secuencia:** `Secuencia`/`PasoSecuencia` (definición) + `CorridaSecuencia`/
`PasoCorridaSecuencia` (histórico), en `domain/modelos.py`. Cada `PasoSecuencia` declara
`origen_tipo` (`independiente`/`derivado`), mutuamente excluyente con `escenario_id`/
`origen_paso_orden` (validado en `__post_init__`): un paso independiente arma su propio
`DatosX` desde un escenario guardado (igual que un ítem de Suite); uno derivado no tiene
escenario — se construye enteramente desde la ejecución que produjo OTRO paso ANTERIOR de la
misma secuencia (`origen_paso_orden`, un `orden` dentro de la definición, nunca un
`ejecucion_id` fijo — ese solo se conoce en cada corrida real). `EstadoPasoSecuencia` reutiliza
el vocabulario de `EstadoItemCorrida` (PASS/FAIL/ERROR/SIN_EXPECTATIVAS/NO_EJECUTADO) y agrega
`BLOQUEADO`, el único estado genuinamente nuevo: un paso derivado cuyo origen no produjo una
ejecución elegible.

**C. Persistencia:** 4 tablas nuevas — `secuencias_transaccionales`/`secuencia_transaccional_
pasos` (definición) y `corridas_secuencia`/`corrida_secuencia_pasos` (histórico) — vía
`CREATE TABLE IF NOT EXISTS`, sin tocar ninguna tabla existente (`ejecucion_origen_id`, de B6,
ya alcanzaba). Nombradas con cuidado para NO chocar con la tabla `secuencias` preexistente (el
contador de STAN, sin relación con este concepto — hallazgo de la investigación previa,
Agente B). Aplicada contra la base real de desarrollo con backup
(`sibutestlab8583.db.bak-preC1-20260913-162610`), 72 filas antes/después, `PRAGMA
foreign_key_check` vacío, re-ejecutada para confirmar idempotencia.

**D. Contexto:** `ContextoSecuencia` (`application/contexto_secuencia.py`) — deliberadamente
DISTINTO de `domain.variables.ContextoResolucion` (Fase A): aquel resuelve `{{...}}` dentro de
un mensaje en armado; este ubica qué ejecución produjo un paso ya terminado. API explícita, sin
diccionarios mágicos: `registrar(orden, ejecucion_id)` / `ejecucion_id_de(orden) -> int | None`,
llenado únicamente cuando un paso independiente produce una `Ejecucion` real. Nunca reconstruye
`ReferenciaEjecucion` a mano: eso sigue siendo exclusivo de `referencia_origen_elegible`
(B6/B7), invocado internamente por `Orquestador.ejecutar_reverso_financiero`.

**E. Ejecutor:** `EjecutorDeSecuencia` (`application/ejecutor_secuencia.py`) recorre los pasos
en orden, SECUENCIAL y se detiene por dependencia — a diferencia de `CorredorDeSuites`, que
aísla ítems independientes y sigue. Un paso independiente delega tal cual en
`EjecutorDeEscenarios` (sin ningún cambio); un paso derivado arma `DatosReversoFinanciero` con
el `ejecucion_id` que el contexto ya registró y delega en `Orquestador.
ejecutar_reverso_financiero`, que revalida la elegibilidad él mismo — las excepciones
`EjecucionOrigenNoEncontrada`/`EjecucionOrigenNoElegible` se clasifican como `BLOQUEADO`, nunca
se reimplementa la regla de `domain.elegibilidad_reverso` aquí.

**F. 0200→0400 real:** `tests/test_ejecutor_secuencia.py::
test_secuencia_real_compra_financiera_y_reverso` — TCP/codec/SQLite/host simulado reales, sin
dobles: paso 1 (0200→0210/00) produce la ejecución A; paso 2 (derivado) arma y transmite el
0400, recibe 0410/00, y persiste `ejecucion_origen_id = A` con un STAN nuevo (≠ STAN de A).

**Evidencia real en la base de desarrollo (Corrida de secuencia #1, generada durante la
verificación en navegador real de C1):**

```
corridas_secuencia   corrida_id=1  secuencia="Compra + reverso (navegador)"
                      estado=finalizada  resultado_global=sin_expectativas
                      total=2  pass=0 fail=0 error=0 sin_expectativas=2 bloqueado=0

ejecuciones           id=73  0200→0210  estado=aprobada  ejecucion_origen_id=NULL
                      id=74  0400→0410  estado=aprobada  ejecucion_origen_id=73

PRAGMA foreign_key_check  -> []  (vacío, sin violaciones)
```

Confirma en datos reales, no solo en test, el diagrama exigido por el checkpoint:
`paso 1 (0200→0210, ejecución #73) → contexto de secuencia → paso 2 (0400→0410, ejecución #74,
ejecucion_origen_id=73)`, sin ningún `ejecucion_id` fijo en la definición ni referencia manual.

**G. Bloqueos:** dos negativas E2E reales, TCP/host real de por medio — `test_una_financiera_
rechazada_bloquea_el_reverso` (0200→0210/51: el paso 2 queda `BLOQUEADO`, cero ejecuciones 0400
generadas) y `test_timeout_en_el_primer_paso_bloquea_el_reverso` (timeout en el paso 1 — que SÍ
persiste como `Ejecucion` con estado `TIMEOUT` — el paso 2 igual queda `BLOQUEADO`, porque
`referencia_origen_elegible` exige `APROBADA`). Ninguno de los dos casos finge un `FAIL`/`ERROR`
del paso 2: la precondición simplemente no se cumplió.

**H. Expectativas:** por paso (`PasoSecuencia.expectativas`, solo aplica a un derivado; uno
independiente ya trae las suyas en el escenario) y global (`domain.secuencias.
calcular_resultado_global_secuencia`, que devuelve el mismo `ResultadoGlobalSuite` de Suites —
`BLOQUEADO` mapea a `INCOMPLETA`, mismo criterio que la mezcla PASS+SIN_EXPECTATIVAS). Ningún
motor de expectativas nuevo: `evaluar_expectativas` (Fase A/RN) se reutiliza sin cambios,
exactamente como ya hacía `CorredorDeSuites`.

**Semántica protegida explícitamente (revisión de la Corrida #1 real, 2026-09-13):** dos ejes
independientes que no deben confundirse nunca. `EstadoEjecucion` (transaccional: aprobada,
rechazada, timeout, ...) responde "¿qué pasó con el mensaje ISO?"; `EstadoEvaluacion`/
`EstadoPasoSecuencia` (QA) responde "¿eso era lo que el escenario esperaba?". Dos pruebas
dedicadas en `tests/test_ejecutor_secuencia.py` los fijan como regresión:
- Dos transacciones **aprobadas** sin ninguna expectativa declarada → `SIN_EXPECTATIVAS`,
  nunca `PASS` implícito (`assert paso1.resultado is not EstadoPasoSecuencia.PASS`, sobre la
  corrida real de la sección F).
- Una transacción **rechazada** (0200/51) con una expectativa que esperaba exactamente ese
  rechazo → `PASS` de QA (`test_una_financiera_rechazada_con_expectativa_correcta_es_pass_qa`),
  aunque `Ejecucion.estado` siga siendo `RECHAZADA` — y el paso derivado sigue `BLOQUEADO`: un
  PASS de QA no vuelve elegible un origen que `domain.elegibilidad_reverso` ya rechazó.

**I. Seguridad:** ningún dato de tarjeta nuevo se expone — un paso derivado nunca recibe PAN,
Track1/Track2 ni RAW (los mismos guardias de B6/B7 siguen intactos, sin tocar). El contexto
entre pasos solo transporta `ejecucion_id` (un entero), nunca un objeto de dominio con datos
sensibles. `tests/test_secuencias.py` cubre la validación pura de `PasoSecuencia`/
`ContextoSecuencia`; `tests/test_administracion_secuencias.py` cubre el rechazo de un paso
derivado que apunte hacia adelante o hacia sí mismo, y de un escenario inexistente.

**J. UI:** Historial → chip/preview de reverso (B6/B7, sin cambios) más, nuevo en C1: `/secuencias`
(lista + "Nueva secuencia"), `/secuencias/nueva` (formulario: nombre + UN escenario de compra
financiera; el paso 2 es automático, sin selector — C1 solo soporta esta forma),
`/secuencias/{id}/ejecutar`, `/secuencias/corridas[/{id}]` (historial + detalle paso a paso,
con enlace real a `/historial/{ejecucion_id}`). Nueva entrada "Secuencias"/"Corridas de
secuencia" en la barra lateral (grupo Automatización). Verificado con recorrido manual completo
en navegador real: crear escenario de compra financiera, guardarlo, crear la secuencia,
ejecutarla, confirmar ambos pasos en "Sin expectativas" (sin expectativas definidas, no es un
fallo), y navegar al Isoscopio real de cada ejecución -incluida "Originada desde la ejecución
#N" en el paso derivado-.

**K. Arquitectura — qué reutilizó B6/B7:** el modelo de operación derivada
(`ejecucion_origen_id`), la elegibilidad (`domain.elegibilidad_reverso`), el snapshot seguro
(`ReferenciaEjecucion`/`referencia_origen_elegible`) y el propio `Orquestador.
ejecutar_reverso_financiero` se reutilizaron TAL CUAL, sin ninguna modificación: la única pieza
nueva de infraestructura es el motor de secuencias en sí (modelo, persistencia, contexto,
ejecutor, UI). Cero condicionales especiales por MTI se agregaron en ningún módulo de dominio.

**L. Tests:** 1296 passed al cerrar B7 → **1331 passed** al cierre formal de C1 (35 nuevos:
3 migración, 6 E2E de ejecutor -incluida la protección explícita de la semántica
transaccional-vs-QA, punto priorizado tras revisar la Corrida #1 real-, 17 puros de
modelo/contexto/agregador, 5 de administración de secuencias, 2 web verticales, 2 web de humo).
0 skipped. `git diff --check` limpio en cada commit.

**M. Commits:** `a81e080` (C1.1), `e139522` (C1.2), `f52eaf5` (C1.3), `69624d3` (cierre: protege
la semántica transaccional-vs-QA, documenta la Corrida #1 real). **Integrado a `main` en el
merge `989991e`** (2026-09-13), suite 1331 passed en verde antes y después, smoke real en
navegador confirmado.

**N. Próximo paso (decidido, 2026-09-13):** el propietario eligió **C2** primero (variables
entre pasos), dejando 0420/0430 para después. Ver checkpoint C2 en la sección 11.

## 11. Checkpoint C2 — Contexto y variables entre pasos (`{{step.<id>...}}`)

**Estado: COMPLETO para el alcance acordado.** Rama
`feature/secuencias-c2-contexto-variables`, commits `3fef508` (C2.1 modelo+persistencia),
`754d1c3` (C2.2 motor de resolución), `6f0cd77` (C2.3 integración), `e4e0208` (C2.4 tests).
Sin mergear a `main`, pendiente de aprobación del propietario.

**A. Integración C1:** confirmada antes de abrir C2 — `main`/`origin/main` en `989991e`, suite
1331 passed en verde.

**B. Sintaxis (decidida, no litigada por gusto):**

```
{{step.<paso_id>.request.<deNN>}}    campo tal como se ENVIÓ en ese paso
{{step.<paso_id>.response.<deNN>}}   campo tal como VOLVIÓ en la respuesta
{{step.<paso_id>.execution_id}}      metadata interna (id de fila en `ejecuciones`),
                                       NUNCA un valor ISO — namespace separado
```

`request`/`response` son namespaces obligatorios y excluyentes (nunca ambiguo de dónde sale un
valor, punto 7). `deNN` es el número de campo ISO en minúsculas (`de38`, nunca "DE38" ni un
nombre de negocio). Misma gramática que Fase A: `{{` + expresión + `}}`, todo el campo o nada
-nunca mezclado con texto literal (`ABC{{step...}}` es rechazado, igual que en Fase A)-. Vive en
`application/variables_secuencia.py`, un SEGUNDO reconocedor (no una extensión del regex de
`domain/variables.py`): resuelven en dos momentos distintos del flujo (referencias de paso
ANTES de tocar el orquestador; `{{stan}}`/`{{amount}}` de siempre, DENTRO de él), nunca en el
mismo campo a la vez.

**Identidad estable de paso:** `PasoSecuencia.paso_id: str | None` (p. ej. `"purchase"`),
DISTINTO de `orden` -si la secuencia se reordena en el futuro, una referencia por `paso_id`
sigue apuntando al paso correcto, a diferencia de una referencia por número-. `orden` sigue
siendo la autoridad de PRECEDENCIA temporal (una referencia solo es válida hacia un `paso_id`
cuyo `orden` es estrictamente menor); `paso_id` es solo la llave de referencia. Generado
automáticamente (`paso{N}`) si no se indica, para no romper la definición de C1.

**C. Contexto:** `ContextoSecuencia` (C1) gana un segundo índice `{paso_id: ejecucion_id}`,
además del `{orden: ejecucion_id}` original -coexisten a propósito, cada uno resuelve un
mecanismo distinto (C1: `origen_paso_orden`, estructural; C2: `{{step...}}`, textual)-. API
explícita sin cambios de filosofía: `registrar(orden, ejecucion_id, paso_id=...)` /
`ejecucion_id_de_paso_id(paso_id)`.

**D. Seguridad — whitelist:** `perfil.es_sensible(numero)` se comprueba SIEMPRE primero, antes
de verificar si el campo está declarado en la especificación del perfil -así DE35/DE45 (ni
siquiera declarados en `ESPECIFICACION_GENERICA`) se rechazan por `CampoDeEjecucionSensible`,
nunca por "no existe", que sería un mensaje menos preciso para un campo que además es sensible
por definición del estándar. Ninguna lista nueva de campos prohibidos: la misma autoridad
consolidada en B3/B6/B7 (`domain.modelos.CAMPOS_SENSIBLES` + `perfil.campos_sensibles`).
Adversariales reales (TCP/SQLite, `tests/test_resolver_referencia_de_paso.py`): DE2/DE35/DE45
rechazados siempre, un campo no declarado en el perfil rechazado (`MetadataDeEjecucionDesconocida`),
un campo ausente en ese mensaje concreto rechazado (`CampoDeEjecucionNoDisponible`, nunca
cadena vacía), un paso inexistente rechazado (`PasoDeSecuenciaNoEjecutado`).

**E. Validación de dependencias:** `ServicioSecuencias._validar_pasos` valida, AL GUARDAR la
definición (nunca en ejecución): `paso_id` único por secuencia; toda referencia de paso
(detectada escaneando `campos_manuales` del escenario referenciado) apunta a un `paso_id` que
EXISTE y es ESTRICTAMENTE ANTERIOR -rechaza referencias hacia adelante, hacia sí mismo, o a un
paso inexistente antes de que la secuencia pueda correr siquiera (puntos 10/11).
`tests/test_validacion_referencias_de_paso.py` cubre las cinco combinaciones. Una referencia
que se cuela DESPUÉS (un escenario editado fuera de este flujo, sin volver a pasar por
`crear()`) sigue rechazándose en EJECUCIÓN por el motor (ver F) — defensa en profundidad, mismo
criterio que `domain.armado.validar_campos_manuales` ya aplica para campos manuales comunes.

**F. Persistencia — expresión vs. valor:** la definición (el escenario referenciado por un paso
independiente) guarda la EXPRESIÓN `"{{step.purchase.response.de38}}"` tal cual -nunca el valor
resuelto, misma filosofía que Fase A (`valores_efectivos_editables` ya congela expresiones sin
resolver)-. El valor EFECTIVO que se transmitió queda auditable donde siempre: en el mensaje
real persistido de la `Ejecucion` que produjo ese paso (`/historial/{id}`, Isoscopio). Limitación
conocida y documentada, no resuelta en C2: la corrida no guarda aparte "qué expresión estaba
configurada en el momento de correr" -si el escenario se edita después, la corrida histórica
sigue mostrando el valor YA TRANSMITIDO (correcto, inmutable), pero no hay una segunda copia de
la expresión textual en la fila de corrida. Mismo nivel de evidencia que ya acepta Suites hoy
para escenarios reutilizados; no se amplía en C2 sin evidencia de que haga falta.

**G. Ejecutor — clasificación de errores:** `EjecutorDeSecuencia._ejecutar_paso_independiente`
resuelve toda referencia de paso ANTES de delegar en `EjecutorDeEscenarios` (que sigue sin saber
que "step.*" existe). Un paso origen que no produjo ninguna ejecución
(`PasoDeSecuenciaNoEjecutado`) clasifica como `BLOQUEADO` -precondición no cumplida, mismo
criterio que C1 para un reverso sin origen elegible-; una referencia inválida (sensible,
inexistente, malformada) clasifica como `ERROR` -un defecto de configuración, no una
precondición de negocio sin cumplir-. Ambas rutas probadas con TCP/SQLite reales
(`tests/test_e2e_variables_secuencia.py`), incluida la "referencia sensible colada" tras editar
un escenario fuera del flujo de creación.

**H. Compatibilidad con Fase A:** `domain/variables.py` no se tocó ni una línea. `{{stan}}`/
`{{amount}}`/`{{transmission_datetime}}`/`{{local_time}}`/`{{local_date}}` siguen resolviéndose
exactamente igual, dentro y fuera de una secuencia -un campo con una de estas expresiones nunca
pasa por `application/variables_secuencia.py` (no matchea su gramática), así que llega intacto
al orquestador, que las resuelve como siempre-. Confirmado por la suite completa en verde
(1355 passed) sin ninguna regresión en `tests/test_variables.py` ni en ningún test de compra/
echo/financiera/reverso ya existente.

**I. E2E real (punto 24/25):**
- `test_paso_2_transmite_de_verdad_un_valor_producido_por_el_paso_1`: dos compras financieras
  independientes; el escenario del paso 2 tiene `DE37 = "{{step.purchase.response.de38}}"`.
  TCP/codec/SQLite/host simulado reales: el 0200 del paso 2 transmite de verdad, en su propio
  DE37, el DE38 (código de autorización) que el host asignó al paso 1 -confirmado leyendo el
  mensaje REAL persistido, no solo el valor que el resolver devuelve-. El escenario sigue
  guardando la expresión sin resolver.
- `test_referencia_a_execution_id_no_necesita_enviarse_como_campo_iso`: la metadata
  `execution_id` se resuelve y se usa en un campo de texto libre (DE41, terminal) sin que el
  motor exija tratarla como un campo ISO -confirma el namespace separado del punto 6-.

**J. UI:** **NO se agregó ninguna UI dedicada para C2**, decisión explícita. Ni Fase A
(`{{stan}}`/`{{amount}}`, ya en producción) tiene ayuda en pantalla sobre su sintaxis hoy -no
hay precedente en este proyecto de "ayuda de expresiones" en ningún editor-, así que agregar
una solo para C2 habría sido inconsistente sin evidencia de que haga falta. El mecanismo se
opera hoy vía la misma superficie que ya existe (el campo `campos_manuales` de un escenario,
editable desde `editor_transaccion.html`): quien sepa la sintaxis puede escribir la expresión
en cualquier campo editable de un escenario, igual que ya escribe `{{stan}}` hoy. La UI de
creación de secuencias (C1) sigue limitada a la forma "compra + reverso automático"; extenderla
a N pasos independientes con selección de escenarios libres es explícitamente C3+, no C2 (fuera
de alcance, punto 26).

**K. Tests:** 1331 passed al cerrar C1 → **1355 passed** al cierre de C2 (24 nuevos: 6 de
gramática pura, 9 del resolver -incluidos los 4 adversariales de seguridad-, 4 E2E reales
-2 de flujo correcto, 2 de clasificación de errores en ejecución-, 5 de validación de
definición). 0 skipped. `git diff --check` limpio en cada commit. Migración real aplicada
contra la base de desarrollo con backup (`sibutestlab8583.db.bak-preC2-20260913-193647`),
78 filas antes/después, `PRAGMA foreign_key_check` vacío, re-ejecutada para confirmar
idempotencia. Recorrido manual en navegador real confirmando que el mecanismo de C1 (derivado
por `orden`) sigue funcionando sin cambios tras la migración y el código nuevo de C2.

**L. Commits:** `3fef508` (C2.1), `754d1c3` (C2.2), `6f0cd77` (C2.3), `e4e0208` (C2.4).

**Próximo paso:** dos caminos disponibles, decisión del propietario -ninguno bloqueado por el
otro-:
1. **0420/0430** sobre el motor de secuencias ya construido (una tercera operación derivada,
   análoga a `financial_reversal`, reutilizando `EjecutorDeSecuencia` sin cambios de forma).
2. **C3** -expectativas dinámicas (un valor esperado que dependa de `{{step...}}`, hoy
   explícitamente diferido, punto 19) y/o data-driven (CONTINUE_ON_FAILURE, retries/timeout de
   paso, ver sección 6, subfase C3 actualizada).
**No se avanzó a ninguna de las dos todavía.**

---

## 12. Checkpoint B8 — Aviso de reverso (0420/0430)

**A. Integración de C2:** confirmada antes de abrir B8 — `main`/`origin/main` en `04372ba`
(merge `--no-ff` de `feature/secuencias-c2-contexto-variables`, historia preservada), suite
1355 passed / 0 skipped antes y después del merge, `git diff --check` limpio, base de desarrollo
verificada (`paso_id` presente en ambas tablas de C2, definiciones y corridas existentes
preservadas, `PRAGMA foreign_key_check` vacío). Dos smokes reales post-merge: (1) C1 — una
secuencia `0200 → 0400` real confirmó que el reverso sigue usando la ejecución producida por el
paso 1; (2) C2 — una secuencia con `{{step.purchase.response.de38}}` en el DE37 del segundo paso
confirmó, contra el DE37 realmente transmitido por TCP, que coincide con el STAN producido por el
paso anterior. `git push origin main`: `HEAD == origin/main == 04372ba`.

**B. Investigación (Agente A, dominio ISO 8583, fuentes públicas genéricas):** el tercer dígito
del MTI codifica la FUNCIÓN del mensaje: `0`=request, `1`=request response, `2`=advice,
`3`=advice response. Un *reversal* (0400/0410) es una **solicitud** que el receptor puede negar;
un *reversal advice* (0420/0430) es la **notificación** de un reverso que ya ocurrió — el emisor
no pide permiso, informa un hecho consumado, y el receptor está obligado a aceptarlo (0430), no a
evaluarlo de nuevo. Campos típicamente relevantes en la literatura genérica: DE90 (Original Data
Elements, para correlacionar con el mensaje original — ver punto F), DE39 (código de respuesta),
DE11 (STAN nuevo, distinto del original). El catálogo detallado de "reason codes" de un 0420 varía
por marca/red y **no se investigó ni se inventó** — fuera de alcance por `CLAUDE.md`. Fuentes:
isoparser.com/iso-8583-reference, github.com/moov-io/iso8583 (docs/mti.md), neapay.com.

**C. Semántica funcional:** `OPERACION_AVISO_REVERSO = "reversal_advice"` (`domain/modelos.py`),
separada de `MTI_AVISO_REVERSO = "0420"` — misma disciplina operación≠MTI que el resto del
proyecto (`OPERACION_COMPRA_FINANCIERA`, `OPERACION_REVERSO_FINANCIERO`). El nombre viene
directamente de la investigación (punto B), no es una elección arbitraria de este proyecto.

**D. Perfil (0420/0430):** `OBLIGATORIOS_0420 = {"3","4","7","11","41","49"}`,
`OBLIGATORIOS_0430 = {"3","4","7","11","39","41"}`, `_POLITICA_AVISO_REVERSO` — declarados de
cero en `profiles/generico.py`, **sin referenciar** `OBLIGATORIOS_0400`/`_POLITICA_REVERSO_
FINANCIERO` aunque comparten forma (punto 7 del encargo): auditados campo por campo contra
`ReferenciaEjecucion`, resultaron idénticos a los de 0400 porque este laboratorio no tiene ninguna
fuente que distinga los campos de un aviso de los de una solicitud — la diferencia es de
*contrato de mensaje*, no de campos (ver punto E). `CODIGO_PROCESO_AVISO_REVERSO = "000000"`,
constante propia.

**E. Diferencia frente a 0400:** documentada en el docstring de `domain/modelos.py::
MTI_AVISO_REVERSO` y en `application/armado_aviso_reverso.py`: 0400 es una solicitud que el
receptor puede negar; 0420 es un aviso que el receptor debe aceptar. Esa diferencia de contrato
(no de campos) es la que justifica dos operaciones derivadas separadas — dos MTI, dos builders,
dos métodos del `Orquestador` — en vez de una sola parametrizada por MTI.

**F. DE90:** revisitada, no reabierta. Sigue sin fuente defendible para DE33 (Forwarding
Institution ID) en `ESPECIFICACION_GENERICA` — misma conclusión de B7, ratificada sin
implementar nada parcial ni admitir texto libre. La correlación 0420↔original sigue apoyándose
en `Ejecucion.ejecucion_origen_id` (B6) y DE37/RRN cuando el original lo tenía; la correlación
0420↔0430 (RN-3, la del intercambio actual) siguió funcionando sin ninguna estrategia nueva una
vez completado el punto G.

**G. Builder y arquitectura reutilizada:** `application/armado_operacion_derivada.py` (nuevo)
extrae `componer_operacion_derivada_financiera(mti, referencia, *, stan_nuevo, momento_nuevo,
codigo_proceso)` — la composición de campos resultó **idéntica** entre 0400 y 0420 al comparar
campo por campo (duplicación medida, no anticipada, punto 8 del encargo); `armar_reverso_
financiero` ahora delega en ella, `armar_aviso_reverso` (nuevo) es su wrapper específico.
Reutilizado **sin ningún cambio**: `ReferenciaEjecucion`/`referencia_origen_elegible`
(application/referencia_ejecucion.py), `domain.elegibilidad_reverso.puede_generar_operacion_
derivada` (misma regla de 0200 aprobada — investigada para B8, no asumida: el evento que ambas
operaciones referencian es el mismo), `GeneradorStanSQLite` (STAN nuevo automático), y el núcleo
`Orquestador._ejecutar`/`_registrar`. Único hallazgo que requirió un cambio real: `domain.
validacion.mti_de_respuesta` mapeaba el tercer dígito SIEMPRE a `0->1`, calculando `0420 → 0410`
(incorrecto) en vez de `0420 → 0430` — el propio comentario de una versión anterior ya lo
señalaba como "caso distinto, fuera de esta función". Se completó con una tabla genérica
`{0:1, 2:3}` (la misma regla de función-de-mensaje del punto B, no una regla inventada): RN-3
(`domain/validacion.py`), el `HostSimulado` y la validación de expectativas del `Orquestador` ya
derivaban el MTI de respuesta desde esta función, así que quedaron correctos para 0420/0430 sin
tocarlos — confirmado con un test E2E real por TCP antes de continuar con el resto de B8.

**H. Host:** `HostSimulado._construir_respuesta` no tiene branching por MTI 0400 — cae en el
`else` genérico (DE39 configurable, default `"00"`) igual que cualquier MTI sin caso especial.
Con el fix del punto G, 0420 usa exactamente el mismo camino: **cero líneas tocadas** en
`adapters/host_simulado/servidor.py`.

**I. Interactivo:** rutas `GET/POST /historial/{id}/aviso-reverso(/ejecutar)` (espejo exacto de
`reverso_preview`/`reverso_ejecutar`), plantilla `aviso_reverso_preview.html` (espejo de
`reverso_preview.html`, PAN nunca en claro). El detalle de una ejecución elegible ahora muestra
dos botones diferenciados ("Crear reverso" / "Crear aviso de reverso") con un párrafo explicando
la diferencia funcional; la tabla de derivadas distingue cada una ("Reverso financiero · 0400",
"Aviso de reverso · 0420") en vez de listar solo el número de ejecución. Verificado con evidencia
real en navegador (TCP/SQLite reales, host `sibu-host-demo`): ejecución origen #87 (0200
aprobada, STAN 000089) → aviso de reverso real #88 (0420→0430, STAN 000090) → reverso financiero
real #89 (0400→0410, STAN nuevo) sobre el MISMO origen; el detalle de #87 lista ambas derivadas
correctamente rotuladas y enlazadas, y cada detalle derivado enlaza de vuelta a #87.

**J. Secuencia (0200 → 0420):** `PasoSecuencia`/`DatosPaso` ganan `operacion_derivada: str =
OPERACION_REVERSO_FINANCIERO` (default preserva toda definición de C1 sin migrarla);
`EjecutorDeSecuencia._ejecutar_paso_derivado` despacha entre `ejecutar_reverso_financiero`/
`ejecutar_aviso_reverso` según ese campo — el resto del método (resolución de `ContextoSecuencia`
por `orden`, clasificación BLOQUEADO/ejecutado) no cambió. Migración aditiva
(`operacion_derivada TEXT NOT NULL DEFAULT 'financial_reversal'` en `secuencia_transaccional_
pasos`), verificada contra la base de desarrollo real (backup `sibutestlab8583.db.bak-preB8-
migracion-*`): 10 pasos existentes, los 10 retro-completados a `'financial_reversal'` (su
significado real antes de B8), `PRAGMA foreign_key_check` vacío. E2E real (TCP/SQLite/host
simulado) confirma: paso "purchase" (0200→0210/00) → paso "reversal_advice" (0420→0430, origen =
ejecución del paso purchase, resuelto vía `ContextoSecuencia`, **sin** `ejecucion_id` fijo en la
definición) y una secuencia con AMBOS tipos de paso derivado (reverso Y aviso) sobre el mismo
origen, sin ningún candado de exclusividad. **Sin UI** para crear esta secuencia desde
`/secuencias/nueva` — mismo criterio que C2 (el formulario web sigue construyendo solo compra +
reverso; la capacidad se probó a nivel de aplicación/dominio).

**K. C2 (uso real de variables entre pasos):** ninguno nuevo, deliberadamente (punto 18 del
encargo): 0420, igual que 0400, se construye **completamente** desde `ReferenciaEjecucion` — no
existe ningún dato no sensible donde forzar una referencia `{{step...}}` habría agregado valor
real sin ser artificial. La prueba de que C2 sigue funcionando después de B8 ya está cubierta
independientemente (punto A, smoke 2, y la suite completa de C2 sin regresiones). Punto 17
protegido explícitamente: un paso derivado sigue sin `campos_manuales` (`DatosReversoFinanciero`/
`DatosAvisoReverso` son "constructores cerrados"), así que `{{step...}}` no tiene ningún punto de
entrada en él — la identidad del origen es *siempre* `ContextoSecuencia`/`ReferenciaEjecucion`,
nunca una variable de paso.

**L. Seguridad:** `ReferenciaEjecucion.campos_respuesta` sigue siendo la whitelist `{"37","38"}`
sin cambios; el preview de 0420 no consulta `RepositorioTarjetas` (igual que el de 0400); el piso
universal `CAMPOS_SENSIBLES = {"2","35","45"}` y el orden de verificación de C2 (`perfil.
es_sensible` antes que cualquier otra cosa en `resolver_referencia_de_paso`) se confirmaron
intactos con una prueba de regresión dedicada (`tests/test_seguridad_aviso_reverso.py`); ningún
campo `"90"` (DE90) aparece en la vista previa (punto F); ninguna tabla nueva de C1/B8
(`secuencia_transaccional_pasos` con su columna `operacion_derivada`) tiene columna de PAN. B8 no
introduce ningún vector nuevo de exposición de PAN/Track/RAW respecto de B7 (confirmado por
investigación dedicada antes de escribir código, y por la suite de seguridad después).

**M. Arquitectura — señal de reutilización:** medido con `git diff --stat` contra `main`. B8
(cuatro commits, segunda operación derivada) queda en ~1670 líneas insertadas entre código y
pruebas — muy similar en tamaño a B7 (~1566 líneas, la PRIMERA operación derivada, que tuvo que
construir `ReferenciaEjecucion`, `domain/elegibilidad_reverso.py` y la extensión del núcleo del
`Orquestador` desde cero). La señal real no está en el conteo de líneas -la mitad de B8 son
pruebas espejo, deliberadamente redundantes con las de B7 por diseño- sino en **qué no se tocó
en absoluto**: `elegibilidad_reverso.py`, `referencia_ejecucion.py`, el núcleo `Orquestador._
ejecutar`/`_registrar`, `GeneradorStanSQLite`, `HostSimulado`, `ContextoSecuencia`, y el motor de
variables de C2 — cero líneas modificadas en los siete. Lo genuinamente nuevo fue angosto:
constantes de MTI/operación, un dataclass de 3 líneas (`DatosAvisoReverso`), un wrapper de
builder de ~20 líneas, una política de perfil declarada aparte, un método del `Orquestador` de
~30 líneas, dos rutas web + una plantilla, y una línea de despacho en el ejecutor de secuencias.
**La arquitectura de operaciones derivadas escala**: agregar una segunda operación no forzó
duplicar B7, solo extenderlo en los puntos que su propio diseño ya dejaba abiertos (perfil por
MTI, despacho por campo). El único ajuste que NO estaba anticipado fue el fix de
`mti_de_respuesta` (punto G) — y ese es una corrección de una regla genérica incompleta, no una
señal de que la arquitectura de reversos no escale.

**N. Tests:** 1355 passed / 0 skipped al abrir B8 (tras integrar C2) → **1391 passed / 0
skipped** al cierre de B8 (36 nuevos: 9 de builder/perfil puros, 8 E2E reales del `Orquestador`
-incluida la coexistencia 0400+0420 sobre el mismo origen-, 5 web/interactivos, 5 del motor de
secuencias -incluida una secuencia con ambos tipos de paso derivado-, 6 de migración/seguridad,
3 de ajuste a pruebas existentes). `git diff --check` limpio en cada commit. Migración real
aplicada contra la base de desarrollo con backup (punto J). Recorrido manual en navegador real
(punto I). Fase A y B7 intactas (sin cambios, suite completa en verde). C1/C2 intactas: sus
propias suites (`test_ejecutor_secuencia.py`, `test_e2e_variables_secuencia.py`, `test_
validacion_referencias_de_paso.py`, etc.) pasan sin modificación.

**O. Commits:** `cc2479e` (B8.1-B8.3: semántica/perfil/builder/orquestador), `b298ee7` (B8.4: UI
interactiva), `a242bc5` (B8.5: secuencias), `6add431` (B8.6a: seguridad). Integrado a `main`
(merge `9a7dd32`) tras el checkpoint — ver sección 13 para el bloque siguiente (C3).

**Próximo paso, decidido con la evidencia de este checkpoint:** el propietario eligió **C3**
(control de flujo avanzado) antes que Fase D (Host Simulator 2.0) — B8 demostró que el motor de
secuencias generaliza bien a una segunda operación derivada sin tocar su núcleo
(`ContextoSecuencia`, validación de pasos), mientras que `HostSimulado` no necesitó ningún
cambio para soportar 0420 (punto H), señal de que el simulador actual todavía tiene margen. Ver
checkpoint C3 en la sección 13.

## 13. Checkpoint C3 — Control de flujo avanzado de secuencias

**Estado: COMPLETO para el alcance acordado.** Rama `feature/secuencias-c3-control-flujo`,
commits `f5c9821` (C3.1-C3.2: modelo/migración/motor STOP-CONTINUE), `aa972c6` (C3.3: E2E real +
tabla de verdad del resultado global), `171129d` (C3.4: expectativas dinámicas), `ec7bd2b` (C3.5:
retry mínimo y seguro), `282fcab` (C3.6: UI de intentos). **No mergeado a `main`** — queda en la
rama, pendiente de revisión del propietario.

**A. Integración de B8:** confirmada antes de abrir C3 — `main`/`origin/main` en `9a7dd32`, suite
completa 1393 tests (1391 passed + 2 skipped por un `PATH` de shell sin `sibu-run-suite`, no una
regresión — confirmado corrigiendo el `PATH` de la sesión: 1393 passed/0 skipped). Base de datos
real verificada (`operacion_derivada` presente, 10 pasos existentes preservados como
`financial_reversal`, 5 secuencias preservadas, `PRAGMA foreign_key_check` vacío). Cuatro smokes
reales post-merge: (1) 0200→0400, (2) 0200→0420, (3) el historial del origen lista ambas
derivadas (0400 y 0420) con enlaces, (4) una secuencia con referencia C2
(`{{step.purchase.response.de38}}`) sigue transmitiendo el valor real sin regresión — confirmado
también navegando la Ejecución #94 en el navegador real. `git push origin main`: `HEAD` ==
`origin/main` == `9a7dd32`.

**B. Investigación previa y un hallazgo que cambió el diseño:** cuatro agentes read-only
(motor de secuencias, expectativas, retry, UX/auditoría) antes de escribir código. El hallazgo
más importante del Agente A: **el bucle de `EjecutorDeSecuencia._correr` nunca se detuvo por sí
mismo desde C1** — lo que en C1 parecía "detenerse" era siempre el efecto emergente de un paso
DERIVADO sin contexto válido (`BLOQUEADO` por precondición/elegibilidad), nunca una decisión de
flujo real. Esto contradice la premisa inicial del propietario ("hoy C1 esencialmente tiene
stop_on_failure"), y cambia la decisión correcta de default: `CONTINUAR`, no `DETENER`, es el
único valor que preserva el comportamiento observable de una secuencia definida antes de C3 —
documentado explícitamente en vez de resuelto en silencio.

**C. STOP/CONTINUE — comportamiento:** `PoliticaContinuacion` (`CONTINUAR`/`DETENER`) en
`PasoSecuencia.on_error`/`on_qa_fail` (default `CONTINUAR` para ambos, ver punto B). Cuando un
paso con la política en `DETENER` termina en `ERROR`/`FAIL`, **todos** los pasos siguientes
—independientes y derivados— quedan `BLOQUEADO` sin intentarse, con un `detalle` que dice
explícitamente que fue la política de continuación (nunca solo la palabra "BLOQUEADO", punto 26
del checkpoint) y distinto del motivo ya existente de "origen no elegible". No se creó ningún
estado nuevo: `BLOQUEADO` ya existía desde C1, ahora con dos causas distintas diferenciadas por
texto, nunca por un enum nuevo.

**D. Precondiciones protegidas:** la política de flujo nunca puede saltarse una precondición de
dominio. Confirmado con E2E real: `CONTINUAR` tras un `FAIL` de QA en el paso origen no vuelve
elegible a un reverso/aviso derivado — sigue `BLOQUEADO` por `domain.elegibilidad_reverso`,
exactamente igual que sin ninguna política. `SIN_EXPECTATIVAS` nunca activa `on_qa_fail` (un
rechazo transaccional sin expectativa que lo contradiga sigue sin ser un fallo).

**E. Resultado global — regla:** sin cambiar `calcular_resultado_global_secuencia` (la
precedencia ya existente desde C1 ya produce el resultado correcto): un `ERROR` que detuvo la
secuencia por política sigue dominando como `ERROR` global; un `FAIL` de QA que detuvo la
secuencia por política produce `FAIL` global, nunca "el último paso gana" (confirmado con un
caso real: paso 1 FAIL + paso 2 PASS con `CONTINUAR` → global `FAIL`). Se agregaron dos pruebas
de la tabla de verdad (`test_secuencias.py`) formalizando ambos casos con evidencia, no solo
argumentándolos.

**F. Expectativas dinámicas — sintaxis/resolución/auditoría:** mismo lenguaje `{{step.<paso_id>.
request|response.deNN}}` de C2, reutilizado sin crear un segundo lenguaje. Solo aplica a
`PasoSecuencia.expectativas` (exclusivo de un paso DERIVADO en este proyecto desde C1 — un paso
independiente sigue tomando sus expectativas del escenario, que es reusable fuera de cualquier
secuencia). Se resuelve DESPUÉS de que el paso origen tiene su respuesta persistida pero ANTES de
evaluar la respuesta del paso actual. Auditoría: la definición de la secuencia sigue guardando la
EXPRESIÓN (nunca el valor resuelto), mientras que el `detalle` de la corrida registra expresión Y
valor efectivo juntos (`"expectativa dinámica DE39: {{step.purchase.response.de39}} → 00"`),
incluso en pasos PASS/FAIL donde `detalle` normalmente queda vacío. Seguridad: mismas reglas de
C2 — DE2/DE35/DE45 rechazados siempre, `perfil.es_sensible()` primero; una referencia hacia un
paso posterior o inexistente se rechaza al GUARDAR la secuencia, nunca en ejecución.

**G. Retry — qué se implementó y qué se rechazó por seguridad:** investigado explícitamente
antes de implementar (agente de retry): un timeout o una transmisión indeterminada DESPUÉS de
enviar 0200/0400/0420 no permite demostrar si el host ya procesó el mensaje, así que **se
rechazó** cualquier retry automático de esas operaciones — `PasoSecuencia.__post_init__` rechaza
`max_retries > 0` en cualquier paso DERIVADO de forma incondicional. Lo que **sí se implementó**:
`max_retries > 0` únicamente para un paso independiente cuyo escenario es Echo (0800, la única
operación sin efecto de negocio del laboratorio), validado también en
`application.secuencias._validar_pasos` (que sí puede consultar el escenario real). Cada intento
se registra por separado en la tabla nueva `corrida_secuencia_paso_intentos` sin sobrescribir al
anterior; el resultado final del paso es el del primer intento con una respuesta real, o el
último si todos fallaron. E2E real con timeout inducido en el primer intento (mismo
`HostSimulado` de siempre, alternando su atributo `responder` ya existente desde la prueba, sin
tocar código de producción ni construir infraestructura de Fase D) y éxito real en el segundo.

**H. Persistencia — migración:** columnas aditivas `on_error`/`on_qa_fail`/`max_retries` en
`secuencia_transaccional_pasos` (default `'continuar'`/`'continuar'`/`0`, preserva C1 sin migrar
datos) y tabla nueva `corrida_secuencia_paso_intentos`. Verificada contra la base de desarrollo
real: backup previo (`sibutestlab8583.db.bak-preC3-20260914-085301`), columnas y tabla nuevas
confirmadas, 9 secuencias y 11 corridas existentes preservadas, `PRAGMA foreign_key_check` vacío.

**I. UI — recorrido real:** decisión deliberada (mismo criterio que C2/B8-secuencias) de no
expandir `secuencia_nueva.html` con controles nuevos — el formulario sigue siendo fijo (compra +
reverso automático) y `detalle` ya renderiza el motivo completo de cada paso sin ningún cambio de
plantilla. Lo único genuinamente invisible sin UI eran los intentos de retry: se agregó una tabla
anidada en `secuencia_corrida_detalle.html`, visible solo cuando un paso tuvo más de un intento.
Verificado en el navegador real contra la base de desarrollo (ya migrada): la Corrida #12 (Echo
con retry real) muestra "Reintentos (C3): 2 intentos", Intento 1 `ERROR` (timeout) e Intento 2
`Sin expectativas`, cada uno con su propio enlace a Ver ejecución.

**J. Seguridad:** los nuevos motivos de auditoría (política de detención, expectativa dinámica
resuelta, intentos de retry) usan siempre texto fijo y seguro o valores ya confirmados no
sensibles — nunca `str(excepción)`, nunca traceback. Confirmado con pruebas dedicadas
(`test_seguridad_c3.py`): el motivo de "detenido por política" nunca incluye texto de excepción;
ningún intento de retry puede cargar un PAN (retry es exclusivo de Echo, que nunca tiene tarjeta);
el `detalle` de una expectativa dinámica resuelta nunca contiene una secuencia con forma de PAN.

**K. E2E — casos realizados:** seis casos reales de STOP/CONTINUE (`test_ejecutor_secuencia_
control_flujo.py`, puntos 17-22 del checkpoint), cinco de expectativas dinámicas
(`test_expectativas_dinamicas.py`), cuatro de retry (`test_retry_echo.py`, incluido el caso real
de timeout-inducido-éxito), uno de UI de intentos (`test_web_retry_intentos.py`), tres de
seguridad (`test_seguridad_c3.py`), doce de modelo puro (`test_politica_continuacion.py`) — todos
contra TCP/SQLite/host simulado reales donde aplica, ninguno con mocks del núcleo.

**L. Tests:** 1393 passed al abrir C3 (tras integrar B8) → **1421 passed / 2 skipped** al cierre
de C3 (los 2 skipped son un artefacto del `PATH` del shell de esta sesión sin `sibu-run-suite`
instalado, no una regresión — confirmado ejecutando la suite con el `PATH` corregido: 1421
passed/0 skipped). 46 pruebas nuevas: 12 de modelo/política puro, 6 de STOP/CONTINUE E2E, 2 de
tabla de verdad del resultado global, 5 de expectativas dinámicas, 4 de retry, 1 de UI, 3 de
seguridad. Fase A, B6, B7, C1, C2, B8 intactas (sus propias suites pasan sin modificación).

**M. Commits:** `f5c9821` (C3.1-C3.2: modelo de política, migración, motor STOP/CONTINUE),
`aa972c6` (C3.3: E2E real + tabla de verdad), `171129d` (C3.4: expectativas dinámicas), `ec7bd2b`
(C3.5: retry mínimo seguro), `282fcab` (C3.6: UI de intentos), `06e4957` (C3.7: seguridad/docs).
Integrado a `main` en `a7be884` tras la aprobación del propietario (2026-09-14).

**N. Próximo paso:** decidido por el propietario -**Fase D, Host Simulator 2.0**- sobre C4. Ver
checkpoint D1 en la sección 14.

## 14. Checkpoint D1 — Motor de reglas del Host Simulado

**Estado: COMPLETO para el alcance acordado.** Rama `feature/host-simulator-d1-rules-engine`,
commits `8fcbb36` (D1.1-D1.2: modelo puro + matching), `791fa6b` (D1.3: persistencia SQLite),
`39c4215` (D1.4: integración en `HostSimulado`), `f6da670` (D1.5: migración de la regla sintética),
`d4538f9` (D1.6: UI), `4a498bf` (D1.7a: integración con retry de C3). **No mergeado a `main`** —
queda en la rama, pendiente de revisión del propietario.

**A. Integración de C3:** confirmada antes de abrir D1 — `main`/`origin/main` en `a7be884`. Suite
completa reconciliada: 1424 passed + 2 skipped (artefacto de `PATH` del shell sin `sibu-run-suite`
instalado) = 1426 passed/0 skipped con el `PATH` corregido — mismo hallazgo ya documentado en
C2/B8/C3, confirmado explícitamente de nuevo antes de continuar. Base de datos real verificada
(columnas `on_error`/`on_qa_fail`/`max_retries` presentes, tabla de intentos presente, defaults
`continuar`/`continuar` en pasos existentes, `PRAGMA foreign_key_check` vacío). Cuatro smokes
reales post-merge: (1) secuencia 0200→0400, (2) STOP ante FAIL QA, (3) CONTINUE con paso posterior
independiente (resultado global FAIL, no "el último paso gana"), (4) retry de Echo mostrando
múltiples intentos. `git push origin main`: `HEAD` == `origin/main` == `a7be884`.

**B. Investigación y una decisión de alcance explícita:** cuatro agentes read-only (host actual,
diseño del motor de reglas, seguridad, UX) antes de escribir código. Hallazgo relevante del agente
de diseño: el roadmap ya registraba un diseño previo de una jornada anterior para Fase D (YAML,
sin persistencia ni UI en ninguna subfase). El propietario, consultado explícitamente sobre este
conflicto de alcance antes de implementar, confirmó continuar con lo pedido en este encargo —D1
incluye persistencia SQLite y UI, reemplazando esa nota del roadmap—, documentado aquí para que
quede trazable la razón del cambio.

**C. Modelo de reglas — entidades:** `domain/reglas_host.py` (nuevo). `CondicionRegla(campo,
operador, valor)` reutiliza el vocabulario de `ExpectativaCampo` (`igual`/`presente`/`ausente`) y
agrega `distinto`/`mayor_que`/`menor_que`. `RespuestaRegla(de39, campos_adicionales)` declara solo
las diferencias sobre la base correlacionada que el host ya arma. `ComportamientoRegla(tipo,
delay_ms)` con cuatro tipos (`normal`/`delay`/`timeout`/`disconnect`), límites explícitos
(`delay_ms` entre 0 y 10 000, nunca negativo). `ReglaHost(nombre, prioridad, activa, condiciones,
respuesta, comportamiento, regla_id)`, todo inmutable. Reglas como DATOS: sin `eval`/`exec`/
scripting embebido — investigado y prohibido explícitamente, nunca solo una lista de cortesía.

**D. Matching — operadores:** `evaluar_reglas` ordena por prioridad ascendente (menor primero) y
devuelve la primera regla activa cuyas condiciones todas coincidan (AND implícito, sin OR/grupos/
NOT complejo). `mayor_que`/`menor_que` comparan como `Decimal` (nunca lexicográfico); un campo no
numérico o ausente simplemente no coincide, nunca una excepción sin controlar. El pseudo-campo
`mti` compara el tipo de mensaje sin pasar por el perfil.

**E. Prioridad/default:** determinista (orden ascendente de prioridad; una regla inactiva nunca
gana). Sin ninguna regla coincidente, el host cae al comportamiento DEFAULT: el `if/elif`
hardcodeado de siempre (`_construir_respuesta`), preservado sin ningún cambio — nunca un error.

**F. Acciones — response/delay/timeout/disconnect:** `_aplicar_regla` construye la respuesta sobre
la misma base correlacionada que ya usa el camino default (`campos_de_correlacion`, extraído a un
helper compartido). `GeneradorValor` (`stan_request`/`datetime_now`/`authorization_from_stan`), un
Enum cerrado marcado con prefijo `@`, nunca un lenguaje de templates. `TIMEOUT` reutiliza el
mecanismo ya existente de `responder=False`/`_apagado` (nunca un `sleep` fijo, decisión por mensaje
en vez de una bandera fija de todo el host); `DISCONNECT` cierra el socket de inmediato sin
escribir nada — distinto de `TIMEOUT`, confirmado con un test que verifica que el cliente nunca lo
confunde con una aprobación ni con un timeout.

**G. Persistencia — decisión:** SQLite (autorizado explícitamente, ver punto B), no YAML. Dos
tablas nuevas y aditivas: `reglas_host` (configuración; condiciones/campos adicionales en JSON,
mismo criterio ya usado para `expectativas_json`) y `reglas_host_eventos` (auditoría de qué regla
—o ninguna— gobernó una respuesta real, deliberadamente sin FK hacia `ejecuciones` del cliente y
sin guardar nunca el valor de ningún campo del mensaje). Reglas con estado (`visto_antes`,
contadores) NO se implementaron: es exactamente lo que el propietario pidió dejar fuera de D1
(puntos 30/40 del encargo) para no deformar el alcance con complejidad de estado compartido entre
intentos.

**H. Seguridad — campos prohibidos:** `perfil.es_sensible()` (misma autoridad que C2/B6, nunca una
lista nueva) gatea tanto condiciones como campos de respuesta, verificado SIEMPRE al guardar
(`validar_regla`) — DE2/DE35/DE45 rechazados sin excepción, ni siquiera para comparar. Ningún
mensaje de error incluye el valor real de un campo, solo el nombre y el motivo. El `<select>` de
"elegir campo" en la UI excluye estructuralmente los mismos campos (nunca aparecen como opción).
Los eventos de auditoría nunca registran el valor de ningún campo del mensaje — solo qué regla, con
qué prioridad, y qué respondió.

**I. UI — recorrido:** decisión deliberada (mismo criterio que C2/B8-secuencias/C3-intentos): un
formulario enfocado, filas fijas para condiciones/campos de respuesta (sin "+Agregar campo"
incremental), sin drag-and-drop (confirmado ausente del proyecto). Verificado en el navegador real
contra la base de datos de desarrollo (migrada primero, backup `sibutestlab8583.db.bak-preD1-*`,
10 secuencias y 12 corridas preservadas, `PRAGMA foreign_key_check` limpio): crear una regla real
(rechazo por monto vía DE4), verla en la lista con su resumen de condiciones/respuesta,
desactivarla y reactivarla — confirmado end-to-end. Hallazgo real corregido durante esa
verificación: el `<select>` de campo ofrecía las claves estructurales del bitmap ("Campo h/p/t")
como si fueran campos ISO reales; corregido para excluirlas (mismo criterio que
`campos_permitidos_expectativa`).

**J. Auditoría:** cada mensaje —con regla ganadora o sin ella— queda registrado en
`reglas_host_eventos` si se configura un repositorio de eventos, con el nombre/prioridad/DE39/
comportamiento de la regla que gobernó, nunca el contenido del mensaje.

**K. E2E — casos realizados:** ocho casos reales contra `HostSimulado` (`test_host_simulado_
reglas.py`): sin reglas el comportamiento es idéntico al de antes de D1; una regla ganadora
gobierna la respuesta (rechazo dinámico que el umbral sintético no habría dado); ninguna regla
coincidente cae al default; una regla inactiva nunca gana; delay real produce latencia observable;
timeout por regla produce el mismo `TiempoAgotado` que `responder=False`; disconnect es distinto de
timeout; los eventos quedan auditables. Cinco casos de caracterización (`test_migracion_regla_
sintetica.py`) confirman que la regla sintética migrada produce el mismo resultado externo que el
camino hardcodeado, incluido el límite exacto del umbral. Un caso de integración con C3 (`test_
integracion_reglas_host_secuencias_c3.py`): una regla D1 de timeout activa de verdad el retry de
Echo que C3 ya construyó, sin test doubles del núcleo.

**L. Compatibilidad:** sin reglas configuradas (el default), `0100`/`0200`/`0400`/`0420`/`0800`
siguen funcionando exactamente igual que antes de D1 — el `if/elif` de `_construir_respuesta` nunca
se tocó, solo se extrajo un helper compartido (`_campos_base_correlacionados`) sin cambiar su
comportamiento. `sibu-host-demo` sigue arrancando igual, sin argumentos nuevos —
`composicion.host_simulado()` no se conectó a reglas todavía, decisión deliberada para esta entrega
(punto 34 del encargo: "no romper el comando existente").

**M. Tests:** 1426 passed/0 skipped al abrir D1 (tras integrar C3 y reconciliar el artefacto de
`PATH`) → 1493 passed/0 skipped al cierre de D1 (67 nuevos: 40 de modelo/matching/seguridad puros,
3 de migración de esquema, 7 de administración, 8 de integración con `HostSimulado`, 5 de migración
de la regla sintética, 4 de UI web, 1 de integración con el retry de C3). Fase A, B6-B8, C1-C3
intactas (sus propias suites pasan sin modificación).

**N. Commits:** `8fcbb36` (D1.1-D1.2: modelo puro + matching), `791fa6b` (D1.3: persistencia),
`39c4215` (D1.4: integración en `HostSimulado`), `f6da670` (D1.5: migración de la regla sintética),
`d4538f9` (D1.6: UI), `4a498bf` (D1.7a: integración con retry de C3), `aa60f71` (D1.7b: docs).
Integrado a `main` en `fc69dbd` tras la aprobación del propietario (2026-09-14).

**O. Próximo paso:** decidido por el propietario — **D2** (reglas con estado limitado) sobre C4 y
Fase E. Ver checkpoint D2 en la sección 15.

## 15. Checkpoint D2 — Reglas del Host con estado controlado

**Estado: COMPLETO, incluido el cierre del gap de restart.** Rama
`feature/host-simulator-d2-stateful-rules`, commits `906593d` (D2.1: modelo), `9353499` (D2.2:
persistencia/atomicidad), `d32ce30` (D2.3-D2.4: matching stateful + auditoría), `640d627` (D2.5:
E2E retry de C3), `34dba88` (D2.6: UI), `ea118e7` (D2.7a: seguridad), `95393d1` (D2.7b: docs),
D2.8 (cierre del restart real, ver punto J). **Pendiente de integrar a `main`** una vez cerrado
este punto — ver verificación final más abajo.

**A. Integración de D1:** confirmada antes de abrir D2 — `main`/`origin/main` en `fc69dbd`. Suite
completa reconciliada: 1493 passed + 2 skipped (artefacto de `PATH`) = 1495 passed/0 skipped con
el `PATH` corregido. Base de datos real verificada (tabla `reglas_host` sin filas de prueba
residuales, `PRAGMA foreign_key_check` vacío). Cinco smokes reales post-merge: (1) sin reglas,
comportamiento histórico; (2) `0200` + monto alto → 51; (3) Echo con delay; (4) Echo timeout;
(5) Echo disconnect. `git push origin main`: `HEAD` == `origin/main` == `fc69dbd`.

**B. Modelo de estado — decisión:** `ReglaHost.max_aplicaciones` (atributo de nivel-regla,
`None` = ilimitada) en vez de una `CondicionRegla` especial sobre un "número de coincidencia" —
más simple de explicar a un QA, menos cambio sobre el matching de D1 (investigado y confirmado
por el agente de diseño). `EstadoReglaHost` (`aplicaciones_consumidas`) vive deliberadamente
SEPARADO de `ReglaHost` — mismo principio que ya separa `reglas_host` (configuración) de
`reglas_host_eventos` (auditoría): duplicar una regla copia la configuración pero nunca el
estado; editar la configuración nunca resetea el contador salvo una acción explícita.

**C. Persistencia:** tabla nueva `reglas_host_estado` (PK/FK 1:1 hacia `reglas_host`), PERSISTENTE
—no efímera en memoria—, decisión tomada con evidencia (investigado): un contador efímero sería el
único componente inconsistente del modelo de reglas (configuración y auditoría ya son
persistentes), y un restart de `sibu-host-demo` reseteando silenciosamente un límite contradiría
la premisa misma del feature.

**D. Atomicidad:** `incrementar_si_no_agotada` resuelve TODO en una sola sentencia
(`INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING`), mismo espíritu que
`GeneradorStanSQLite.siguiente()` (precedente ya existente en el proyecto): SQLite mantiene el
bloqueo de escritura durante toda la sentencia, así que dos conexiones concurrentes compitiendo
por la MISMA regla se serializan — nunca un `SELECT` seguido de un `UPDATE` en pasos separados.
Confirmado con una prueba real: 20 corrutinas concurrentes contra una regla `max_aplicaciones=1`,
exactamente UNA obtiene un resultado exitoso.

**E. Matching:** `evaluar_reglas` (dominio, sigue PURA, sin I/O) recibe el estado YA obtenido y
salta una regla agotada, continuando con la siguiente por prioridad. `HostSimulado.
_seleccionar_regla_ganadora` (adaptador, con I/O) orquesta: intenta el incremento atómico sobre
la candidata; si falla (agotada, o perdió una carrera concurrente), la excluye y reintenta con
las demás — nunca cae directo al fallback del host si otra regla (incluido un fallback explícito
sin límite) aún coincide.

**F. Reset:** acción EXPLÍCITA (`ServicioReglasHost.reiniciar_contador`, ruta
`/reglas-host/{id}/reiniciar-contador`, siempre POST), nunca implícita en guardar/activar/
desactivar. Pone el contador en 0 sin borrar la fila ni tocar la auditoría histórica
(`reglas_host_eventos` permanece intacta, confirmado con una prueba dedicada).

**G. Auditoría — match number:** `EventoReglaHost.match_number` (columna nueva, aditiva) registra
en qué número de aplicación gobernó la regla — `None` si es ilimitada o si ninguna coincidió.
Permite reconstruir después "por qué el segundo intento recibió otra respuesta" sin adivinar.

**H. C3 Retry — E2E real:** la prueba de fuego del checkpoint (`test_d2_c3_retry_automatico.py`):
una secuencia C3 con retry de Echo (`max_retries=1`) contra una regla D2 de timeout
(`max_aplicaciones=1`) más un fallback normal, TOTALMENTE AUTOMÁTICA — a diferencia del test
equivalente escrito en la sesión D1/C3 (`test_integracion_reglas_host_secuencias_c3.py`), que
necesitaba alternar `regla.activa` manualmente entre intentos. Aquí el propio motor de reglas
decide, sin ninguna intervención de la prueba: primer intento TIMEOUT real, segundo intento
NORMAL real, confirmado tanto por la auditoría de C3 (tabla de intentos) como por la auditoría
independiente del lado del HOST (`reglas_host_eventos`).

**I. Concurrencia — evidencia:** dos niveles de prueba real, sin mocks: (1) contra el repositorio
aislado, 20 corrutinas concurrentes, exactamente una tiene éxito; (2) contra el `HostSimulado`
completo (TCP real), 10 solicitudes Echo concurrentes reales compitiendo por una regla
`max_aplicaciones=1`, exactamente una recibe el rechazo, las demás caen al fallback.

**J. Restart — cerrado con un proceso real (D2.8):** el checkpoint original documentaba esta
garantía solo por inferencia. Se cerró con evidencia directa, en dos niveles:

- *Gap encontrado y corregido primero:* `Composicion.host_simulado()` (la fábrica que usa
  `sibu-host-demo`) nunca conectaba reglas/eventos/estado — decisión deliberada de D1 para "no
  romper el comando existente" (ver punto L de la sección 14), pero eso significaba que el
  proceso real jamás había aplicado NINGUNA regla D1/D2, con o sin restart. Sin corregir esto,
  la prueba de restart pedida era imposible de ejecutar contra el comando real. Se volvió
  `async`, carga `listar()` de `reglas_host` al arrancar (una foto tomada al iniciar, no
  recarga en caliente — un cambio de reglas en la web requiere reiniciar el proceso para verse,
  igual que cualquier configuración de un servidor de demostración) y conecta
  `repositorio_eventos`/`repositorio_estado`. `sibu-host-demo` sigue arrancando sin argumentos
  nuevos. Los tres call-sites (`cli.py`, `test_web_vertical.py`, y el propio método) se
  actualizaron a `await`; suite de esos archivos re-verificada (15 passed).
- *Prueba automatizada* (`tests/test_d2_restart_real.py`): lanza `sibu-host-demo` como un
  PROCESO REAL nuevo (`python -m sibutestlab8583.adapters.host_simulado.cli`, no una instancia
  de clase reiniciada dentro del proceso de la prueba), con las dos reglas del encargo (timeout
  `max_aplicaciones=1` + fallback normal) ya persistidas. Primer Echo → TIMEOUT, contador queda
  en 1 en SQLite. El proceso se MATA (`terminate`/`wait`, con `kill` de respaldo), se confirma
  que ya no escucha (`poll() is not None` y un intento de conexión TCP falla). Se lanza un
  SEGUNDO proceso (PID distinto) sobre la MISMA base SQLite. Segundo Echo → APROBADA (la regla
  timeout seguía agotada, ganó el fallback). Verificado tras el segundo proceso: contador sigue
  en 1 (no volvió a subir), los dos eventos de auditoría con su `match_number` correcto, y
  `PRAGMA foreign_key_check` vacío.
- *Verificación manual adicional, en el puerto real 8583* (no solo un puerto efímero de prueba):
  mismas dos reglas creadas en la base de desarrollo real (backup previo
  `sibutestlab8583.db.bak-preRestartManual-*`), `sibu-host-demo` arrancado como proceso de
  Windows real, Echo → TIMEOUT, contador confirmado en 1, proceso terminado con `taskkill /F`
  por PID, puerto confirmado libre por `netstat`, proceso NUEVO arrancado (PID distinto
  confirmado por `netstat`), Echo → APROBADA, contador seguía en 1, auditoría y
  `foreign_key_check` limpios. Las dos reglas de esta demostración se desactivaron después
  (`cambiar_estado activa=False`, nunca borradas — mismo principio que el resto del proyecto:
  nunca eliminar filas con auditoría asociada).

Con esto, la limitación señalada en la primera versión de este checkpoint queda cerrada con
evidencia directa, no solo por analogía.

**K. UI — recorrido real:** campo "Número máximo de aplicaciones" (vacío = sin límite, mismo
patrón que `comportamiento_delay_ms`); columna "Aplicaciones" ("N / M" o "∞"); chip "Activa ·
agotada" (variante propia, nunca `chip--inactiva` — una regla agotada sigue activa
conceptualmente); acción "Reiniciar contador" (POST, visible solo con límite configurado).
Verificado en el navegador real contra la base de datos de desarrollo (migrada primero, backup
`sibutestlab8583.db.bak-preD2-*`, 10 secuencias y 12 corridas preservadas, `PRAGMA
foreign_key_check` limpio): una regla real con límite 2 mostró "1 / 2", "Reiniciar contador" la
llevó a "0 / 2", y consumir el límite completo mostró "Activa · agotada" con "2 / 2".

**L. Compatibilidad D1:** una regla sin `max_aplicaciones` nunca toca el repositorio de estado,
confirmado con una prueba dedicada; el `if/elif` hardcodeado de `_construir_respuesta` sigue sin
tocarse.

**M. Seguridad:** `max_aplicaciones` no abre ninguna vía nueva para evadir la prohibición de
campos sensibles (DE2/35/45 siguen rechazados con límite configurado); `EstadoReglaHost` es
estructuralmente incapaz de contener un PAN (solo `regla_id`/contador entero/timestamp); el
reset nunca borra auditoría histórica.

**N. Tests:** 1495 passed/0 skipped al abrir D2 (tras integrar D1 y reconciliar el artefacto de
`PATH`) → **1522 passed/0 skipped** al cierre de D2 (27 nuevos: 8 de modelo puro, 5 de
persistencia/atomicidad incluida la prueba de concurrencia real, 5 de matching stateful contra
`HostSimulado`, 1 de E2E principal con retry de C3, 4 de UI web, 4 de seguridad). Fase A, B6-B8,
C1-C3, D1 intactas (sus propias suites pasan sin modificación).

**O. Commits:** `906593d` (D2.1: modelo de estado limitado), `9353499` (D2.2: persistencia y
atomicidad), `d32ce30` (D2.3-D2.4: matching stateful + auditoría con match_number), `640d627`
(D2.5: E2E principal, retry de C3 automático), `34dba88` (D2.6: UI), `ea118e7` (D2.7a: seguridad).
No mergeado a `main` — queda en `feature/host-simulator-d2-stateful-rules`, pendiente de
revisión del propietario.

**P. Próximo paso:** tres caminos disponibles, ninguno bloqueado por el otro — **D3** (simulación
adversarial/`visto_antes`/modos de falla restantes), **C4** (data-driven u otras capacidades de
secuencia), o **Fase E** (Client/Server/Proxy). D2 demostró que el estado limitado se integra de
verdad con el retry de C3 sin test doubles (punto H), y que la atomicidad real de SQLite (mismo
patrón que `GeneradorStanSQLite`) es suficiente para concurrencia real sin necesitar locks de
proceso (punto I) — señal de que el laboratorio tiene ahora una base sólida tanto para reglas
declarativas como para el próximo incremento de estado (`visto_antes`) si se necesita. Decisión
pendiente del propietario.
