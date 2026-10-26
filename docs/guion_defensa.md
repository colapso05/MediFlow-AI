# Guion de defensa — EP2 ITY1102 (10 minutos)

> Uso interno del equipo. No forma parte de la entrega.
> Reparto sugerido: Demis (apertura, C4 y comparación técnica), Bruno (dimensionamiento y costos),
> Matías (patrones, Kubernetes, seguridad). Ajustar a quién domina cada tema.

## Antes de empezar (checklist de 2 minutos)
1. Abrir el PDF de la presentación en pantalla completa; tener el documento abierto en otra pestaña
   (por si piden ver un diagrama o una tabla).
2. Verificar que el proyector no recorte los bordes: la presentación es 16:9.
3. Cronómetro a la vista. 10 minutos es el máximo; apuntar a 9:00 para no quedar cortados.

## Minuto 0:00 — 1:00 · Diapositiva 1 y 2 (apertura)
- "El caso es MediFlow AI: agendar horas médicas conversando, por web o WhatsApp."
- Cerrar con el marco de la entrega: "esta segunda parte no diseña el flujo, diseña la arquitectura
  que lo sostiene en producción: concurrencia, caída, datos sensibles y costo por token."
- Dar los dos números del caso: **72.000 turnos al mes** (300 conversaciones diarias × 8 turnos)
  y pico de **5 veces** la media. Ese pico justifica todo lo que viene después.

## 1:00 — 2:30 · Diapositiva 3 (C4 Nivel 1, contexto)
- Explicar los tres vecinos y el límite: paciente (WhatsApp/web), proveedor de LLM, sistema
  de agenda del HIS y el servicio de notificaciones.
- Frase clave: "el sistema no reemplaza la agenda del HIS: escribe en ella. Por eso la frontera
  del contexto técnico está en la API de negocio, no en la base de datos."

## 2:30 — 4:00 · Diapositiva 4 (C4 Nivel 2, contenedores)
- Seis unidades desplegables: frontend, canal WhatsApp, API de negocio, servicio de agente,
  agenda/reservas y gateway de LLM; más datos: PostgreSQL, Redis y el bus de eventos.
- Justificar la separación: "el servicio de agente escala con la conversación; la agenda escala
  con las escrituras. Si fueran el mismo contenedor, escalarían juntos y pagaríamos de más."

## 4:00 — 5:00 · Diapositiva 5 (C4 Nivel 3, componentes)
- Recorrer el ciclo con el diagrama: consumidor de cola → orquestador de estados → planificador →
  ejecutor de herramientas → guardrails → respuesta.
- Destacar dos piezas: **checkpointer** (estado tras cada nodo) y **guardrails** (ni diagnóstico
  ni prescripción). Son las dos que un prototipo no tiene y una evaluación sí exige.

## 5:00 — 6:00 · Diapositiva 6 (patrones)
- Microservicios: cada servicio con su despliegue, sin base compartida, API como única puerta
  de escritura.
- Event-Driven: el webhook responde 200 en menos de 100 ms y publica el turno; SQS absorbe el
  pico de 5×; cola de mensajes muertos tras tres fallos.
- Si preguntan por qué no monolito: "el pico es de la conversación, no de la agenda; separarlos
  permite escalar solo lo que se satura."

## 6:00 — 7:00 · Diapositiva 7 (dimensionamiento y costos)
- Método primero, números después: "precios on-demand reales de la región sa-east-1, 730 horas
  al mes, tomados de la lista de precios de AWS, no estimados."
- Total **USD 2.297,19/mes** de infraestructura; con el canal de WhatsApp (**USD 1.465,00**) el
  sistema completo queda en **USD 3.762,19/mes**, es decir **USD 0,0523 por turno**.
- El dato que sorprende y conviene decir en voz alta: "el canal pesa 39 % del costo. Meta empezó a
  cobrar las respuestas del bot el 1 de octubre de 2026: 0,02 dólares por mensaje en Chile, con mil
  gratis al mes. Por eso agrupamos la respuesta en un solo mensaje y no usamos plantillas de
  marketing, que cuestan 4,4 veces más."
- Aclarar la ausencia de GPU: "la inferencia ocurre en el proveedor; una g4dn.xlarge está evaluada
  solo para fine-tuning, no para operación. Comprar GPU para inferencia remota sería gasto sin uso."
- Si preguntan qué se recorta primero: "los nodos de aplicación bajan a 2 y ElastiCache a una
  réplica: el ahorro es de unos USD 520 con degradación de disponibilidad, no de función."

## 7:00 — 8:00 · Diapositiva 8 (Kubernetes y balanceo)
- EKS 1.31, node group de 3 a 6 nodos m6i.xlarge; HPA por CPU y por profundidad de cola.
- Balanceo: ALB con health check cada 10 s y umbral 3; Nginx con **least_conn** porque la conexión
  del agente dura más que una consulta y round-robin castigaría a los pods lentos.
- Cerrar con el detalle que suele preguntarse: "drenaje de 30 s antes de terminar un pod para no
  cortar una conversación a medias."

## 8:00 — 9:00 · Diapositiva 9 (seguridad, observabilidad y HA)
- Los 10 puntos en tres fases (gobierno, datos y modelo, operación) — nombrar la fuente:
  la guía de la actividad 2.1 del curso, aplicada al caso.
- Ley 19.628 y 21.719: dato de salud como sensible; minimización y seudonimización en logs.
- Continuidad: **RPO 5 min** y **RTO 30 min**, con la restauración probada, no supuesta.

## 9:00 — 10:00 · Diapositiva 10 (cinco decisiones) y cierre
- Recorrer la tabla de arriba abajo, una frase por fila: "cada decisión descarta una alternativa
  concreta y responde a un requisito de calidad del informe".
- Rematar: "las cinco están implementadas en el repositorio y probadas: reserva doble rechazada,
  turno reanudado, imagen construida con healthcheck sano".
- Cierre: "la arquitectura queda documentada, dimensionada en USD 3.762 al mes con el canal
  incluido y con un plan de seguridad verificable. Quedamos atentos a sus preguntas."

---

## Preguntas probables y respuesta corta

**¿Por qué EKS y no ECS, si cuesta más?**
El plano de control son USD 73 al mes dentro de 2.297 (3 %). A cambio: HPA por métrica de cola,
NetworkPolicy de egreso y despliegues progresivos. ECS obligaría a construir eso a mano.

**¿Dónde se cae este diseño si el tráfico se multiplica por diez?**
Primero la base de datos: la escritura transaccional de citas. La mitigación está en el bloqueo
por cupo y en el índice único parcial; después, en réplicas de lectura y partición por fecha.

**¿Cómo se evita que dos pacientes tomen la misma hora?**
Bloqueo por cupo (`SELECT FOR UPDATE`) y restricción de exclusión en horarios. La idempotencia
(clave + huella SHA-256) evita además el duplicado por reintento del mismo paciente.

**¿Qué pasa si el proveedor de LLM se cae?**
Circuit breaker en el gateway de LLM, reintentos con retroceso y respuesta de degradación:
se ofrece la agenda sin lenguaje natural. La cita no se pierde, se deriva al flujo clásico.

**¿Cómo se protege un dato de salud de la fuga en los logs?**
Enmascarado en el gateway antes de salir al proveedor, seudonimización en logs y retención de
90 días con borrado programado. El dato identificable no se escribe en texto plano.

**¿Cómo se mide que la arquitectura cumple?**
Tablero en Grafana con error, p95, deriva de intención y profundidad de cola; alerta si el error
supera el 2 % en 5 min o el p95 supera 4 s.

**¿Qué no alcanzaron a hacer?**
Ser honestos y acotado: la ejecución del agente está en el repositorio con el motor de reservas
probado, pero la conexión completa del flujo conversacional con las herramientas de escritura
queda como trabajo siguiente. Nunca decir "está todo listo" si no lo está: la pregunta siguiente
sería una demostración.

**¿Por qué no usaron GPU si es un sistema de IA?**
Porque el modelo no se entrena ni se sirve localmente. El costo por turno está en el token,
no en el hardware; una GPU ociosa sería el error clásico de dimensionamiento.
