# Documento de negocio — SibuTestLab8583

## 1. La oportunidad

Hoy, probar transacciones ISO 8583 depende de un simulador de VISA rígido. El problema no es
el tiempo de una transacción aislada: una prueba simple puede validarse casi de inmediato
(HECHO, aportado por el estudiante). El mayor esfuerzo operativo tiende a concentrarse cuando
el trabajo deja de ser una transacción aislada y pasa a incluir:

- **regresiones**, donde el mismo conjunto de casos se repite una y otra vez;
- **certificaciones**, que exigen recorrer un lote completo de escenarios antes de dar por
  válido un cambio;
- **repetición de múltiples casos** ante cualquier ajuste en el switch o en la configuración
  de prueba;
- **coordinación entre personas**: según la certificación, pueden intervenir una, dos, tres o
  más, sin que exista un número fijo (HECHO, aportado por el estudiante — sin cifra exacta);
- **revisión manual de resultados**, cuando es más detallada, puede tomar alrededor de 5
  minutos o más por caso (HECHO, aportado por el estudiante);
- **escenarios que no se pueden probar antes de llegar a ambientes posteriores**, porque el
  simulador actual no permite pruebas de carga reales contra el switch.

Esta es una interpretación razonada del eje de valor, no una medición: `PROYECTO.md` (§2)
documenta el tiempo de armar y ejecutar una prueba como "de 10 segundos a horas (muy
variable)", clasificado en la fuente como **Estimado**, no medido — esa clasificación se
mantiene sin modificarse. No existe una frecuencia estable de cuántas pruebas se ejecutan por
semana: varía y puede crecer considerablemente en ciclos de regresión o de carga (HECHO,
aportado por el estudiante).

**Evidencia cualitativa del riesgo.** Han existido casos reales en los que escenarios que no
pudieron probarse adecuadamente terminaron provocando incidentes en etapas posteriores. No se
documentan aquí nombres, sistemas, entidades, montos ni ningún dato que permita identificarlos
— se registra únicamente como evidencia de que el riesgo es real, no como una cifra de impacto
(EVIDENCIA CUALITATIVA, aportada por el estudiante; no cuantificada). Esto es consistente con
lo que ya admite `PROYECTO.md` (§2): "no poder probar la carga real ya ha afectado al banco o
cooperativa, aunque no hay un número exacto de cuánto" — la propia consigna reconoce la
ausencia de cifra, y este documento no la inventa.

**Qué resuelve SibuTestLab hoy** — todo verificable en el repositorio, no proyectado:

- Recorrido completo **0100 → TCP → 0110**, de punta a punta, contra un host simulado propio
  (MEDIDO).
- Resultado reproducible: mismo caso, mismo comportamiento, con persistencia real en SQLite y
  un historial consultable de cada ejecución (MEDIDO), que reduce parte de la revisión manual
  sin eliminar la necesidad de análisis humano en todos los casos.
- Administración de tarjetas de prueba desde la interfaz de Configuración (MEDIDO).
- Las cuatro reglas de negocio declaradas en `PROYECTO.md` §4, cubiertas por pruebas
  automatizadas que corren en cada `push` (MEDIDO).
- Reproducibilidad desde un clon limpio, sin depender del equipo original, validada en más de
  una máquina (MEDIDO, `CONTEXTO.md`).
- Arranque automatizado con `demo.cmd` y con el skill `levantar-demo`, que verifica de forma
  independiente que el sistema quedó realmente disponible (MEDIDO).

**Lo que esto NO resuelve todavía:** la prueba de carga real contra el switch — la "capacidad
nueva" que menciona `PROYECTO.md` §2 — sigue sin existir. El motor de carga está congelado, no
implementado; no se presenta en ningún punto de este documento como algo entregado (HECHO).

## 2. Escenarios de adopción y riesgos

### Escenario 1 — Uso interno en QA/desarrollo

El escenario más cercano al prototipo actual: un desarrollador o un equipo pequeño usando
SibuTestLab para probar el propio recorrido de compra, en su máquina o en una red controlada.

| | |
|---|---|
| **Beneficio** | Reduce el trabajo repetitivo de armar cada caso a mano y deja un historial consultable de cada ejecución (HECHO) |
| **Riesgo técnico** | Un solo perfil genérico; sin motor de carga; framing propio, no estandarizado (HECHO) |
| **Riesgo operativo** | Un único autor concentra el conocimiento del proyecto, sin plan de traspaso documentado (HECHO) |
| **Riesgo ético** | Bajo en este escenario: el PAN completo nunca llega al navegador ni a los logs; solo vive en el catálogo local de tarjetas de QA (HECHO) |
| **Riesgo regulatorio** | Mínimo: uso de laboratorio, sin datos de producción (HECHO) |
| **Mitigación** | Mantener el uso confinado a red local; no exponer el servicio a internet |

### Escenario 2 — Piloto institucional controlado

Presentado explícitamente como **fase posterior**, no como algo listo para producción hoy.
Requeriría endurecimiento antes de instalarse dentro de una organización financiera real.

| | |
|---|---|
| **Beneficio** | Podría reducir la dependencia de simuladores externos en un piloto controlado, siempre que antes se adapten framing, perfiles, seguridad y controles operativos a las necesidades reales de la institución |
| **Riesgo técnico** | Sin autenticación en la web; framing de demostración, no interoperable con un switch real sin adaptación; catálogo de respuestas genérico, no certificado por ninguna marca |
| **Riesgo operativo** | Cualquiera con acceso de red administra el catálogo de tarjetas; sin roles ni registro de quién hizo qué |
| **Riesgo ético** | El catálogo de tarjetas de QA contendría PAN reales de un ambiente de pruebas institucional, sin cifrado en reposo ni infraestructura real de PIN/llaves |
| **Riesgo regulatorio** | Este documento no afirma cumplimiento PCI-DSS, ISO 27001 ni certificación de ninguna marca — el repositorio no lo demuestra y no corresponde afirmarlo |
| **Mitigación** | No instalar en este escenario sin resolver primero autenticación y cifrado en reposo; tratar cualquier conexión a un switch real como un proyecto de integración aparte, con perfiles reales de marca que hoy no existen |

### Escenario 3 — Producto para terceros

Evolución futura, **no una promesa comercial inmediata**.

| | |
|---|---|
| **Beneficio** | Ofrecer la misma mecánica de prueba a múltiples organizaciones — totalmente hipotético hoy |
| **Riesgo técnico** | Requeriría motor de carga (no existe), perfiles reales por marca (no implementados), y separación multi-cliente (no diseñada) |
| **Riesgo operativo** | Sin gestión de usuarios, sin soporte ni SLA definido |
| **Riesgo ético** | Manejar PAN de terceros a escala exige gobernanza de datos muy superior a la de un proyecto académico de un solo usuario |
| **Riesgo regulatorio** | Requeriría evaluación externa de cumplimiento (PCI-DSS u otra norma aplicable) que este proyecto no ha realizado ni puede autocertificar |
| **Mitigación** | Tratar este escenario como hoja de ruta a largo plazo, condicionado a resolver primero los escenarios 1 y 2 |

**Brechas actuales, válidas para los tres escenarios y explícitas a propósito:** sin
autenticación · sin cifrado en reposo del catálogo QA · sin infraestructura real de
PIN/llaves · sin perfiles reales de Visa/Mastercard · framing de demostración, no estándar ·
catálogo de respuestas genérico, no certificado por marca.

## 3. Hoja de ruta y estimación de retorno

**No se expresa en dinero.** El retorno se plantea en horas, reducción de trabajo repetitivo y
reducción de riesgo/retrabajo, de forma condicional — porque la frecuencia real de uso varía y
no está fijada (HECHO, aportado por el estudiante).

**El razonamiento, sin inventar un punto de equilibrio semanal:**

- Una transacción aislada puede validarse prácticamente de inmediato; ahí el ahorro por caso
  es marginal.
- Cuando la revisión es más detallada, el análisis manual actual puede tomar alrededor de 5
  minutos o más por caso; SibuTestLab reduce parte de esa revisión al presentar los campos de
  forma estructurada y conservar el historial de ejecución, aunque no elimina la necesidad de
  análisis humano en todos los casos.
- En regresiones o pruebas de carga, el número de casos se multiplica; como el prototipo
  ejecuta el mismo recorrido reproducible cada vez, el beneficio escala con la cantidad de
  repeticiones, no con una frecuencia fija.
- Una certificación puede involucrar de una a varias personas; cada persona que hoy repite
  manualmente el mismo análisis es tiempo que se deja de gastar.

**En una frase:** el beneficio crece con el número de casos, el número de repeticiones, el
número de personas involucradas y la cantidad de análisis manual que se evita — no es una
cifra fija, es una función de esas cuatro variables, ninguna de las cuales tiene hoy un valor
documentado y estable.

**Costo de construcción.** La planificación contemplaba aproximadamente 4 horas semanales
(dato del propio calendario del proyecto, `BITACORA.md`), pero el esfuerzo real no fue
cronometrado, por lo que no se presenta una cifra total de construcción.

**Mantenimiento.** Sostener el catálogo genérico, la integración continua y futuras
dependencias representa un esfuerzo recurrente menor, hoy no medido (SUPUESTO).

### Hoja de ruta sugerida

1. **Consolidación del prototipo académico** — cerrar documentación, arquitectura y demo
   (estado actual).
2. **Endurecimiento para piloto interno** — resolver lo mínimo necesario antes de un uso más
   allá del autor.
3. **Perfiles y framing compatibles con necesidades reales** — cuando exista documentación de
   marca autorizada para analizar.
4. **Motor de carga** — la capacidad que hoy falta para cerrar el eje de valor declarado en
   `PROYECTO.md` §2.
5. **Seguridad: autenticación y cifrado en reposo** — condición previa a cualquier instalación
   institucional.
6. **Evaluación eventual para uso institucional o producto** — solo después de completar los
   pasos anteriores, y sujeta a validación externa que este documento no puede otorgar.
