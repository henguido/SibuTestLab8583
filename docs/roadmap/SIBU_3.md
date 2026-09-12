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
| B — Modelo multi-MTI, subfase B1 (núcleo genérico) | **EN PROGRESO** |
| B2 en adelante, C, D1-D3, E, F, G, H, I | **PLANIFICADO** o **INVESTIGACIÓN** (ver detalle en la sección de cada fase) |

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

**Diseño ya disponible** (Agente 2, sin código): introducir `ClaveOperacion = (mti,
codigo_proceso_prefijo | None)` como tercer eje ortogonal a `MetadatoCampo` (forma) y
`PoliticaCamposMti` (gobierno); generalizar `Orquestador.ejecutar_compra` extrayendo un
`_ejecutar` interno parametrizado por una función de armado, dejando `ejecutar_compra` como
envoltorio de una línea sin cambiar su firma ni comportamiento observable.

**Prerrequisito de fase (bloqueante, sección 0 de PROYECTO.md):** decisión explícita del
usuario/curso de ampliar el alcance más allá de 0100/0110, y actualización de `PROYECTO.md`. Sin
esto, ninguna subfase de Fase B debería empezar a escribir código — el diseño ya existe, la
autorización de alcance no.

**Subfases** (orden sugerido por el propio diseño, sección 9 del documento de Agente 2):

| Subfase | Objetivo | Depende de | Riesgo |
|---|---|---|---|
| B1 | Extraer `_ejecutar` genérico dentro de `Orquestador`, sin ningún MTI nuevo — refactor interno puro | Ninguno | Bajo: cubierto por los tests de compra existentes, cero cambio de comportamiento |
| B2 | Introducir `ClaveOperacion`/`politica_por_operacion` en `PerfilDeMarca`, sin ningún perfil que lo use todavía | B1 | Bajo: aditivo, verificable con test de "el perfil genérico no cambia de comportamiento" |
| B3 | Primer MTI adicional real: 0800/0810 (el más simple — sin tarjeta, sin monto) | B2, y la decisión de alcance (prerrequisito de fase) | Medio: exige el "tercer camino" en `evaluar_respuesta` para MTIs sin DE39, y decidir qué significa `Ejecucion` sin `card_id` (ARCH-002) |
| B4 | 0200/0210 con variantes por DE3 | B2, decisión de alcance | Medio: primera vez que `politica_por_operacion` tiene más de una entrada real |
| B5 | Reversos (0400/0410, 0420/0430) | B4, `EstrategiaCorrelacion` (ARCH-005) | Alto: correlación cruzada entre dos mensajes distintos en el tiempo, el caso que RN-3 actual no cubre |

**Criterio de aceptación de cada subfase:** suite verde, cero cambio de comportamiento para
0100/0110 existente, escenarios/suites/historial de compra sin migración de esquema (confirmado
por el propio diseño: `escenarios.mti` y `ejecuciones.mti_solicitud` ya son texto libre).

**NO se implementa en Fase B:** ningún catálogo de "tipos de operación" con nombres de negocio
(retiro, transferencia) como enum de dominio — eso sería inventar semántica de marca, prohibido
por `CLAUDE.md`.

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

| Subfase | Objetivo | Depende de |
|---|---|---|
| C1 | Infraestructura: `Secuencia`/`PasoSecuencia`/`ContextoPaso`, validación de dependencias, tablas nuevas (`secuencias`, `secuencia_pasos`, `corridas_secuencia`, `corrida_secuencia_items`), secuencia de 2 pasos 0100→0100, STOP_ON_FAILURE fijo (sin CONTINUE_ON_FAILURE, sin retries, sin timeout de secuencia) | Fase A (ya completa) |
| C2 | CONTINUE_ON_FAILURE, retries por paso, timeout de paso | C1 |
| C3 | Secuencias con MTIs reales (0100→0200→0420) | C1, Fase B completa |
| C4 | Comparación de corridas de secuencia (equivalente a `comparacion_corridas.py`) | C1, al menos una corrida real que comparar |

**Riesgo documentado:** un campo capturado (`captura`) debe validarse contra `CAMPOS_SENSIBLES`
al guardar la secuencia — mismo criterio que ya usa `campos_permitidos_expectativa` — para que
ningún dato de tarjeta quede expuesto a interpolación entre pasos (relacionado con ARCH-001).

**NO se implementa en Fase C:** ramas condicionales (if/else entre pasos), paralelismo entre
pasos de un mismo flujo, ni un DSL completo de scripting.

### Fase D — Host Simulator 2.0

**Objetivo:** reglas declarativas por contenido de solicitud, en vez de un único comportamiento
global fijo.

**Diseño ya disponible** (Agente 4, sin código): motor de reglas en YAML, evaluado por conexión,
primera-coincidencia-gana (sin pesos ni "más específica gana"); reutiliza el vocabulario de
operadores ya existente en `domain/expectativas.py` (`igual`/`presente`/`ausente`), agrega
`mayor_que`/`menor_que` para montos y `visto_antes` (con estado inyectado, nunca global) para
duplicados; el modo actual (`--codigo`, sin archivo de reglas) sigue funcionando idéntico como
caso particular de "una sola regla default".

**Prerrequisito bloqueante:** QA-002 (agregar test dedicado para `adapters/host_simulado/cli.py`
antes de modificarlo) — único gap de cobertura real detectado en la auditoría de calidad.

**Subfases:**

| Subfase | Objetivo | Depende de |
|---|---|---|
| D0 | Cerrar QA-002: test de `_argumentos()` de `cli.py`, sin ningún cambio de comportamiento | Ninguno — puede hacerse ya, independiente de esta fase |
| D1 | `domain/reglas_host.py` puro (`CondicionCampo`, `ReglaHost`, `evaluar_reglas`), solo operadores `igual`/`presente`/`ausente`/`mayor_que`/`menor_que` (sin `visto_antes` todavía) | D0 |
| D2 | Carga/validación de YAML, wiring en `HostSimulado`/`cli.py` (`--reglas` opcional, compatibilidad total sin el flag) | D1 |
| D3 | `visto_antes` (duplicados) y los 3 modos de falla que no requieren estado (`sin_respuesta`, `cerrar_sin_responder`, `bytes_invalidos`) | D2 |

**Confirmado por el diseño:** ninguno de los 5 fallos simulados requiere cambios en el lado
cliente — `TiempoAgotado`, `FalloDeTransmision`, `ErrorDeDecodificacion`→`INVALIDA`, `RECHAZADA`
vía catálogo ya cubren los 5 casos.

**NO se implementa en Fase D:** regex/rangos combinados, prioridad por especificidad, remapeo de
campo en `copiar`, persistir el archivo de reglas en SQLite, UI web de edición de reglas.

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

**B1 — Extraer `_ejecutar` genérico dentro de `Orquestador`** (diseño ya completo, ver Fase B),
condicionado a la autorización explícita de ampliar el alcance de `PROYECTO.md` más allá de
0100/0110 — sin esa autorización, B1 quedaría implementado sin ningún consumidor real (violaría
el mismo principio de "no sobre-diseñar" que todos los agentes citaron).

Alternativa segura sin esa autorización, ejecutable ya: **D0 — cerrar QA-002** (test dedicado
para `adapters/host_simulado/cli.py`) y/o **C1 — infraestructura mínima de Secuencias** (no
requiere ampliar alcance de MTI, solo agrega un nivel de agrupación sobre escenarios 0100 ya
existentes, ver ARCH-004).
