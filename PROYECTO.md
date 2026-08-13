# Simulador de Transacciones ISO 8583

**Emanuel Guido Sequeira** · SINT-732 Laboratorio Ejecutivo en Claude Code
Entrega y presentación: martes 8 de septiembre de 2026, Sesión 8

> Este es mi enunciado del proyecto del curso. Reemplaza a los casos semilla de la
> consigna oficial; todo lo demás de esa consigna —el núcleo, la rúbrica de nueve
> criterios y las restricciones— aplica igual.

## 1. Qué es y para quién

Una aplicación que permite construir mensajes de transacciones ISO 8583 (el protocolo
que usan las transacciones con tarjeta), enviarlos por una conexión TCP directa, y
probar tanto que la mensajería esté bien formada como la capacidad de carga del
sistema que la recibe.

- **Quién lo usa:** ingenieros, equipo de QA o usuarios no expertos de un banco o
  cooperativa que necesite probar su sistema de autorizaciones o switch. **(supuesto)**
  Yo mismo soy el primer usuario; no hay un número fijo de personas porque también se
  imagina como algo que se podría ofrecer a otras personas o instituciones.
- **Qué dispara el uso:** cuando hay que probar el switch de autorizaciones — sea una
  prueba puntual de un mensaje, o una prueba de carga y estrés con muchos mensajes
  simultáneos.

## 2. El eje de valor

**Eje declarado:** antes/después estimado, más una capacidad nueva.

Hoy se usa un simulador de VISA que es rígido: armar una prueba (una puntual o una de
carga) toma un tiempo muy variable, de 10 segundos a horas, buscando los casos o
campos que sirvan. Además, ese simulador no permite hacer pruebas de carga reales
contra el switch — que es la prueba que de verdad importa. En algunos casos, no poder
probar la carga real ya ha afectado al banco o cooperativa, aunque no hay un número
exacto de cuánto.

| | Hoy | Con el prototipo | Origen del número |
|---|---|---|---|
| Tiempo para armar y ejecutar una prueba | De 10 segundos a horas (muy variable) | Menor y más predecible *(por definir durante el proyecto)* | Estimado |
| Prueba de carga real contra el switch | No se puede hacer | Sí, con métricas de aprobados, rechazados y timeouts | Eje alterno — capacidad nueva |

Sobre este eje se van a argumentar el criterio 1 —oportunidad— y el criterio 6 —hoja
de ruta y retorno—. Los números finales se construyen durante el proyecto; lo que
queda fijo acá es contra qué se comparan.

## 3. El recorrido principal

1. Elegir el escenario transaccional: compra (mensaje MTI 0100).
2. Completar los datos de la transacción — tarjeta de prueba y monto.
3. Construir el mensaje ISO 8583 completo.
4. Validar que el mensaje tenga los campos obligatorios antes de enviarlo.
5. Enviar el mensaje por el socket TCP: al switch real de pruebas cuando se usa de
   verdad, o al host simulado propio cuando se hace la demostración en clase.
6. Recibir la respuesta (MTI 0110), mostrar los campos ya interpretados (el
   "isoscopio"), y validar el campo 39 junto con los demás campos esperados.
7. Guardar la ejecución: mensaje enviado, respuesta recibida y resultado.
8. Para pruebas de carga: repetir el envío a razón de decenas de mensajes por
   segundo, y mostrar métricas — aprobados, rechazados, timeouts y tiempo de
   respuesta promedio.

**Queda afuera a propósito:** retiro, consulta de saldo, reverso, OCT, AFT, refund,
anulaciones y verificaciones de cuenta — quedan como hoja de ruta. También queda
afuera el catálogo de códigos específico de Mastercard y Amex, y cualquier panel de
métricas más elaborado que el descrito arriba.

## 4. Las reglas que valen

1. Una transacción se considera aprobada cuando el campo 39 de la respuesta trae un
   código que la marca de la tarjeta define como aprobado — no es un único valor fijo
   (00, 10, 51, etc.), depende del catálogo de códigos configurado.
2. Si no llega respuesta dentro de 10 segundos, se considera un timeout (equivalente
   al código 91), y se cuenta aparte de un rechazo explícito del switch.
3. Una respuesta solo cuenta como válida si, además del código de aprobación, los
   demás campos del mensaje de respuesta coinciden con lo esperado.
4. Un mensaje al que le falta un campo obligatorio para su tipo (MTI) no se debe
   poder enviar sin que el simulador avise — si se manda mal armado, la prueba no
   está probando lo que dice probar.

**La decisión difícil.** Qué catálogo de códigos usar y hasta dónde llega. En el uso
real contra el switch, los códigos válidos dependen del manual de cada marca (Visa,
Mastercard, Amex). Para la demostración en clase decidí usar un catálogo genérico de
seis códigos — 00 aprobada, 05 no autorizada, 14 tarjeta inválida, 51 fondos
insuficientes, 54 tarjeta vencida, 94 transacción duplicada — y dejar el detalle por
marca como trabajo futuro. Esto es lo que voy a defender en la Sesión 8.

## 5. Los datos

- **Qué persiste:** mensajes enviados y sus respuestas, resultados de las pruebas y
  de las corridas de carga, catálogo de tarjetas de prueba (con su propio
  mantenimiento, aparte), catálogo de códigos de respuesta. Volumen esperado: decenas
  de mensajes por segundo en las pruebas de carga.
- **De dónde salen para la demostración:** tarjetas físicas reales, pero de un
  ambiente de pruebas del banco o cooperativa — no números ficticios inventados ni
  tarjetas de producción.
- **Confidencialidad:** ninguna restricción declarada. Al ser tarjetas de ambiente de
  pruebas, se pueden mostrar en clase sin problema.

## 6. Frontera técnica

- **Depende de:** el switch de autorizaciones del banco o cooperativa.
- **Acceso real:** sí, en el uso real tengo acceso a un switch de pruebas que conecta
  con un autorizador real. Para la demostración en clase se usa un host simulado
  propio, construido en este proyecto, en lugar de conectarse al switch real.
- **Restricciones impuestas:** la institución normalmente impone restricciones de
  acceso de red y límites de tasa. **(supuesto)** No están cuantificadas todavía —
  queda como bandera abierta.

## 7. Qué debe ser cierto cuando entregue

1. **La oportunidad está comparada.** Contra el tiempo variable e impredecible que
   toma hoy armar una prueba con el simulador de VISA, y contra la imposibilidad
   actual de hacer pruebas de carga reales contra el switch.
2. **La arquitectura se decidió antes que el código.** Tendrá que estar documentado
   cómo se separan el armado del mensaje, la validación, la conexión TCP, el host
   simulado y el motor de pruebas de carga — sin decidirlo todavía acá.
3. **El prototipo funciona de extremo a extremo y persiste datos de verdad.** El
   recorrido de compra (0100/0110) descrito en la sección 3, con persistencia real de
   mensajes, respuestas y resultados.
4. **Las reglas del negocio están cubiertas por pruebas que corren en cada push.**
   Las cuatro reglas de la sección 4.
5. **El proceso de construcción quedó registrado.** CLAUDE.md, bitácora e historial
   de commits.
6. **La gobernanza quedó registrada en la bitácora.** Dado que se trabaja contra un
   switch real de un banco o cooperativa, revisar siempre que ningún dato de tarjeta
   real se filtre en logs o en la demostración, y cómo se detecta si el simulador
   afirma que una prueba fue exitosa sin serlo.
7. **La decisión de adoptar está fundamentada.** Se defendería ante un área de QA o
   de ingeniería de pagos de un banco o cooperativa real.
8. **La presentación defiende decisiones.** De 10 a 12 minutos, Sesión 8.

## 8. El núcleo en este proyecto

| Pieza | Cómo se cumple acá |
|---|---|
| Prototipo de extremo a extremo | El recorrido de compra (0100/0110) completo, descrito en la sección 3 |
| Persistencia en base de datos real | Mensajes, respuestas, resultados de pruebas y catálogos |
| Pruebas sobre las reglas del negocio | Las cuatro reglas de la sección 4 |
| CLAUDE.md propio y bitácora con entradas de gobernanza | Aplica igual que a todos |
| Integración continua y skill de arranque | Aplica igual que a todos |
| Los dos documentos | Aplica igual que a todos |

**Excepciones abiertas.** Ninguna.

## 9. Calendario

Horas disponibles por semana: **4**. Semanas hasta la entrega: **5**.

| Para la sesión | Qué tengo que tener listo |
|---|---|
| 4 · 11 de agosto | Repositorio con CLAUDE.md propio; arquitectura con módulos (armado de mensaje, validación, conector TCP, host simulado, persistencia) y sus contratos; diagramas versionados; bitácora abierta |
| 5 · 18 de agosto | Recorrido de compra (0100/0110) funcionando de extremo a extremo, con persistencia real, contra el host simulado |
| 6 · 25 de agosto | Pruebas automatizadas de las cuatro reglas corriendo en cada push; refactorización de lo acumulado |
| 7 · 1.º de septiembre | Skill de arranque para la demostración; motor de pruebas de carga con métricas; escenarios de adopción y riesgos en el documento de negocio |
| 8 · 8 de septiembre | Repositorio completo y presentación |

## 10. Supuestos declarados

- El catálogo de códigos usado en la demostración es genérico (00, 05, 14, 51, 54,
  94), no específico de una marca de tarjeta.
- Las restricciones de red y límites de tasa que impone la institución no están
  cuantificadas todavía.
- El público objetivo abarca varios roles (ingenieros, QA, usuarios no expertos),
  sin un número fijo de personas.
- No hay una cifra medida de cuánto cuesta hoy no poder hacer pruebas de carga; se
  reconoce como una afectación real pero no cuantificada en dinero u horas exactas.

## 11. Lo que este documento no decide

A propósito. Estas decisiones son mías y llegan después:

- La arquitectura: módulos, responsabilidades y contratos entre ellos.
- El modelo de datos.
- El stack: lenguaje, framework y motor de base de datos.

El criterio 2 de la rúbrica evalúa exactamente estas decisiones, así que tomarlas
temprano y sin fundamento no adelanta nada.
