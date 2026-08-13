# Ficha de aprobación · Simulador de Transacciones ISO 8583

**Emanuel Guido Sequeira** · SINT-732 · 4 de agosto de 2026

**Qué es.** Una aplicación que permite construir mensajes de transacciones ISO 8583,
enviarlos por conexión TCP, y probar la mensajería y la capacidad de carga del
sistema que las recibe.

**Cómo se hace hoy.** Con un simulador de VISA rígido, que no permite pruebas de
carga reales y toma un tiempo muy variable armar cada prueba.

---

## Lo esencial

| | |
|---|---|
| **Eje de valor** | Antes/después estimado, más eje alterno (capacidad nueva) |
| **La comparación** | De un tiempo variable e impredecible armando pruebas y sin poder probar carga real, a un tiempo más predecible y con pruebas de carga reales habilitadas |
| **Recorrido principal** | Parte de elegir el escenario de compra y llenar los datos de la transacción; termina en la respuesta validada y la ejecución guardada |
| **Queda afuera** | Retiro, consulta de saldo, reverso, OCT, AFT, refund, anulaciones, verificaciones de cuenta; catálogos de código por marca (Mastercard, Amex); panel de métricas elaborado |
| **La decisión difícil** | Qué catálogo de códigos de aprobación usar: por marca (uso real) vs. uno genérico de seis códigos (demostración) |
| **Datos para la demo** | Tarjetas reales de un ambiente de pruebas del banco/cooperativa (no de producción) |
| **Horas por semana** | 4, por 5 semanas |
| **Punto de partida** | Desde cero |

## El núcleo

| Pieza | | Cómo se cumple acá |
|---|---|---|
| Prototipo de extremo a extremo | ✔ | Recorrido de compra (0100/0110) completo |
| Persistencia en base de datos real | ✔ | Mensajes, respuestas, resultados de pruebas y catálogos |
| Pruebas sobre las reglas del negocio | ✔ | Cuatro reglas sobre códigos de aprobación, timeout, validación de respuesta y validación de campos obligatorios |
| CLAUDE.md y bitácora con entradas de gobernanza | ✔ | Aplica igual que a todos |
| Integración continua y skill de arranque | ✔ | Aplica igual que a todos |
| Los dos documentos | ✔ | Aplica igual que a todos |

## Banderas

- **Restricciones sin cuantificar** — la institución impone restricciones de red y
  límites de tasa, pero aún no están cuantificadas. No compromete el arranque del
  proyecto, pero conviene precisarlas antes de la fase de pruebas de carga.

## Supuestos que quedaron declarados

- El catálogo de códigos de la demostración es genérico (00, 05, 14, 51, 54, 94), no
  específico de una marca de tarjeta.
- El público objetivo abarca varios roles, sin un número fijo de personas.
- No hay cifra medida del costo actual de no poder hacer pruebas de carga; se
  reconoce como afectación real pero no cuantificada.

## Preguntas para el docente

Ninguna.

---

*Enunciado completo en `PROYECTO.md`.*
