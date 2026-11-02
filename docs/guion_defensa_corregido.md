# Guion de defensa corregido — MediFlow AI (EP2 ITY1102)

**Duración: 10 minutos · apuntar a 9:00 · 10 diapositivas**

> Correcciones aplicadas sobre el guion original: precisión terminológica ("dimensionamos", no "medimos"),
> separación entre las seis unidades desplegables y la infraestructura del diagrama, distinción entre
> concurrencia e idempotencia, el rol real de SNS, y las frases de remate que faltaban.

**Reparto:** Demis (apertura, C4 y comparación técnica) · Bruno (dimensionamiento y costos) · Matías (patrones, Kubernetes, seguridad). Ajustar a quién domina cada tema.

---

## Antes de empezar (2 minutos)

1. Abrir el PDF de la presentación en pantalla completa; el informe en otra pestaña (por si piden un diagrama o una tabla).
2. Verificar que el proyector no recorte los bordes: la presentación es 16:9.
3. Cronómetro a la vista. 10 minutos es el máximo.
4. Tener claro quién habla en cada bloque: si dos empiezan a la vez, se pierden 20 segundos y la nota es de equipo.

---

## 0:00 – 1:00 · Diapositivas 1 y 2 — Apertura

> "Buenos días. Presentamos **MediFlow AI**: agendamiento de horas médicas conversando, por web o WhatsApp. El paciente escribe en lenguaje natural, el sistema interpreta la intención, consulta disponibilidad real, **registra la cita** y notifica. Sin formularios ni menús.
>
> Esta entrega **no diseña el flujo: diseña la arquitectura que lo sostiene en producción.** Lo dimensionamos sobre **72.000 turnos al mes** —300 conversaciones diarias por 8 turnos— con un **pico de cinco veces la media**, y ese pico justifica todo lo que viene después.
>
> La arquitectura responde a cuatro problemas que un prototipo no enfrenta: **concurrencia sobre el mismo cupo, reanudación si un pod cae a mitad de la conversación, datos de salud sensibles y costo variable por token.**
>
> El resultado: **5,23 centavos de dólar por turno**, canal incluido."

**No digas:** "medimos el costo" (fue un cálculo con precios de lista y volumen proyectado), ni "atención al cliente 24/7" como si fuera un requisito del caso.

---

## 1:00 – 2:30 · Diapositiva 3 — C4 Nivel 1 (contexto)

- El sistema como **una sola caja**, en el centro. Arriba, quién lo usa; abajo, de qué depende.
- **Los cinco vecinos:** paciente · personal administrativo (recepción) · proveedor de LLM (DeepSeek) · **HIS / ficha clínica** · pasarela de correo/SMS. La pasarela de pagos queda **fuera del alcance** de esta versión.
- El paciente entra por web o WhatsApp; **no accede a la operación interna**.

**Frase de remate (decirla sí o sí):**

> "El sistema **no reemplaza la agenda del HIS: escribe en ella**. Por eso la frontera del contexto técnico está en la **API de negocio**, no en la base de datos."

**Si preguntan por el HIS:** es la fuente autoritativa de especialidades, médicos y bloqueos. Nosotros no duplicamos esa verdad, la consultamos y le escribimos a través de su API.

---

## 2:30 – 4:00 · Diapositiva 4 — C4 Nivel 2 (contenedores)

**Primero las seis unidades desplegables** (es lo que dice el título de la slide):

1. Canal WhatsApp
2. Frontend web
3. API de negocio
4. Servicio Agente IA
5. Agenda y Reservas
6. Gateway de LLM

**Después, lo que además muestra el diagrama:**

- **Infraestructura que las soporta:** WAF + CloudFront (TLS 1.3, OWASP Top 10, rate limit por IP), balanceador ALB (health check cada 10 s), secretos con KMS y rotación a 90 días, observabilidad (Prometheus, Grafana, Loki).
- **Datos:** PostgreSQL (RDS 17 Multi-AZ), Redis (sesión, estado, checkpoints), bus de eventos SQS + SNS.

**Frase de remate (es la que da nota en esta slide):**

> "El servicio de agente escala con la conversación; la agenda escala con las escrituras. Si fueran el mismo contenedor, escalarían juntos y pagaríamos de más."

**Si preguntan "¿WAF y ALB son contenedores C4?"** — respuesta honesta y corta:

> "En el diagrama están dibujados con la misma notación porque son parte del despliegue; en sentido estricto son servicios gestionados de infraestructura. Las **seis unidades desplegables propias** son las que nombré primero."

**No digas:** que el ALB o el WAF son "contenedores" sin aclarar. Es el error que la pauta marca como más común.

---

## 4:00 – 5:00 · Diapositiva 5 — C4 Nivel 3 (componentes del agente)

Recorrer el ciclo señalando el diagrama: **consumidor de cola → orquestador de estados → planificador → ejecutor de herramientas → guardrails → respuesta.**

Dos piezas que un prototipo no tiene y una evaluación sí exige:

- **Checkpointer:** guarda el estado después de cada nodo. Si el pod muere, el turno se reanuda donde quedó.
- **Guardrails:** ni diagnóstico ni prescripción. Entrada y salida filtradas.

Cada decisión del agente queda **auditable**: qué herramienta llamó, con qué argumentos, cuántos tokens.

---

## 5:00 – 6:00 · Diapositiva 6 — Patrones

**Microservicios:**
- Cada servicio con su ciclo de despliegue y su propio escalado.
- **API de negocio como única puerta de escritura.** Sin base compartida entre servicios.
- El gateway de LLM aísla al proveedor: cuotas, reintentos y **enmascarado de datos** antes de salir.

**Event-Driven:**
- El webhook de WhatsApp responde **200 en menos de 100 ms** y publica el turno; el trabajo pesado ocurre después.
- **SQS absorbe el pico de 5×**; cola de mensajes muertos tras tres fallos: ningún turno se pierde en silencio.
- **SNS publica el evento** (cita creada, movida o cancelada). El que le avisa al paciente es la **pasarela de correo/SMS, que está suscrita**; SNS no le escribe directamente.

**Si preguntan por qué no monolito:**

> "El pico es de la conversación, no de la agenda. Separarlos permite escalar solo lo que se satura."

---

## 6:00 – 7:00 · Diapositiva 7 — Dimensionamiento y costos

**Método primero, números después:**

> "Precios on-demand reales de **sa-east-1**, **730 horas** al mes, tomados de la lista de precios de AWS. **Dimensionamos**, no estimamos a ojo."

| Concepto | USD/mes |
|---|---|
| Infraestructura (EKS, EC2, RDS, ElastiCache, ALB+NAT, resto) | **2.297,19** |
| Canal WhatsApp (72.000 mensajes × 0,02) | **1.465,00** |
| **Total del sistema** | **3.762,19** |
| **Costo por turno** | **0,0523** |

**El dato que conviene decir en voz alta:**

> "El canal pesa **39 % del costo**. Meta empezó a cobrar las respuestas del bot el 1 de octubre de 2026: 0,02 dólares por mensaje en Chile, con mil gratis al mes. Por eso agrupamos la respuesta en **un solo mensaje** y no usamos plantillas de marketing, que cuestan **4,4 veces más**."

**Sin GPU — decirlo antes de que lo pregunten:**

> "La inferencia ocurre en el proveedor. Una g4dn.xlarge está evaluada **solo para fine-tuning**, no para operación. Comprar GPU para inferencia remota sería gasto sin uso."

**Si preguntan qué se recorta primero:**

> "Los nodos de aplicación bajan a 2 y ElastiCache a una réplica: unos **USD 520** de ahorro, con degradación de disponibilidad, no de función."

---

## 7:00 – 8:00 · Diapositiva 8 — Kubernetes y balanceo

- **EKS 1.31**, node group de **3 a 6 nodos m6i.xlarge**, separados por tipo de trabajo (app, agente, observabilidad).
- **HPA por CPU y por profundidad de cola**: el pico de 5× no exige servidores ociosos todo el mes. **PDB** para que un mantenimiento no tumbe todo.
- **ALB** con health check HTTP sobre `/api/health` cada **10 s**, umbral 3.
- **Nginx con `least_conn`** — y explicar por qué: *"la conexión del agente dura más que una consulta; repartir por turnos dejaría un pod con cinco conversaciones y otro con una"*.
- **Drenaje de 30 s** antes de terminar un pod, para no cortar una conversación a medias.
- Rollout progresivo: si el health check falla, el despliegue se detiene y quedan los pods viejos.

---

## 8:00 – 9:00 · Diapositiva 9 — Seguridad, observabilidad y alta disponibilidad

Los **10 puntos en tres fases**, nombrando la fuente: la guía de la actividad 2.1 del curso.

- **Gobierno:** dato de salud como sensible (**Ley 19.628 y 21.719**), modelado de amenazas por contenedor, confianza cero con mTLS.
- **Datos y modelo:** minimización, **seudonimización en logs**, 60 casos adversarios en CI, guardrails de entrada y salida.
- **Operación:** aislamiento de entornos, monitoreo de deriva, red teaming trimestral.

**Evidencia medida:** 20 ataques ejecutados 7 veces (**140 turnos**), cero fugas y cero respuestas vacías; el contador se ve en `/api/guardrails`.

**Continuidad:** **RPO 5 min** y **RTO 30 min**, con la restauración **probada, no supuesta**.

**Monitoreo:** Prometheus, Grafana y Loki con trazas OpenTelemetry por turno. Alerta si el error supera el **2 % en 5 min** o el **p95 supera 4 s**.

---

## 9:00 – 10:00 · Diapositiva 10 — Cinco decisiones y cierre

Una frase por fila, sin leer la tabla completa:

1. **EKS en vez de ECS Fargate** — HPA por profundidad de cola, NetworkPolicy de egreso y despliegue progresivo; el plano de control son USD 73 sobre 3.762.
2. **PostgreSQL con restricción de exclusión en vez de NoSQL** — el solapamiento se impide en la base, no en el código.
3. **SQS en vez de Kafka** — 72.000 turnos al mes no pagan operar un clúster de Kafka.
4. **Idempotencia por clave y huella en vez de control solo en la aplicación** — el reintento devuelve la misma cita, no una nueva.
5. **Grafo de estados en vez de cadena de llamadas** — con checkpoint el turno se reanuda; cada decisión queda auditable.

**Cierre:**

> "La arquitectura queda documentada, dimensionada en **USD 3.762 al mes** con el canal incluido y con un plan de seguridad verificable. Quedamos atentos a sus preguntas."

---

## Preguntas probables

**¿Cuáles son las seis unidades desplegables?**
Canal WhatsApp, frontend web, API de negocio, servicio agente, agenda/reservas y gateway de LLM. La infraestructura (WAF, ALB, secretos, observabilidad) y los datos (PostgreSQL, Redis, bus) están en el diagrama pero no son unidades propias.

**¿Por qué EKS y no ECS, si cuesta más?**
El plano de control son USD 73 al mes dentro de 2.297 (3 %). A cambio: HPA por métrica de cola, NetworkPolicy de egreso y despliegues progresivos. ECS obligaría a construir eso a mano.

**¿Dónde se cae este diseño si el tráfico se multiplica por diez?**
Primero la base de datos: la escritura transaccional de citas. La mitigación está en el bloqueo por cupo y el índice único parcial; después, réplicas de lectura y partición por fecha.

**¿Cómo se evita que dos pacientes tomen la misma hora?**
Dos problemas distintos. **Concurrencia:** dos pacientes por el mismo cupo, se resuelve con `SELECT FOR UPDATE` y restricción de exclusión en horarios. **Duplicado:** el mismo paciente reintentando, se resuelve con clave de idempotencia y huella SHA-256. La primera es de la base; la segunda, de la aplicación.

**¿Qué pasa si el proveedor de LLM se cae?**
Circuit breaker en el gateway, reintentos con retroceso y respuesta degradada: se ofrece la agenda sin lenguaje natural. La cita no se pierde, se deriva al flujo clásico.

**¿Cómo se protege un dato de salud de la fuga en los logs?**
Enmascarado en el gateway antes de salir al proveedor, seudonimización en logs y retención de 90 días con borrado programado. El dato identificable no se escribe en texto plano.

**¿Cómo se mide que la arquitectura cumple?**
Tablero en Grafana con error, p95, deriva de intención y profundidad de cola; alerta si el error supera el 2 % en 5 min o el p95 supera 4 s.

**¿Por qué no usaron GPU si es un sistema de IA?**
Porque el modelo no se entrena ni se sirve localmente. El costo por turno está en el token, no en el hardware; una GPU ociosa sería el error clásico de dimensionamiento.

**¿Qué no alcanzaron a hacer?**
Ser honestos y acotados: el motor de reservas está implementado y probado (reserva doble rechazada, turno reanudado, imagen con healthcheck sano), pero la **conexión completa del flujo conversacional con las herramientas de escritura** queda como trabajo siguiente.

> **Nunca decir "está todo listo".** La pregunta siguiente sería una demostración en vivo.

---

## Los números que no se olvidan

- **72.000** turnos/mes = 300 conversaciones/día × 8 turnos
- **5×** el pico sobre la media
- **2.297,19** USD/mes de infraestructura
- **1.465,00** USD/mes de canal WhatsApp
- **3.762,19** USD/mes total
- **0,0523** USD por turno
- **39 %** del costo es el canal
- **0,02** USD por mensaje de servicio en Chile
- **73** USD/mes el plano de control de EKS
- **RPO 5 min / RTO 30 min**
- **140** turnos de pruebas adversarias, cero fugas
- **2 % en 5 min** y **p95 4 s**: los umbrales de alerta

---

## Errores que ya corregimos

| Antes | Ahora |
|---|---|
| "Medimos el costo de operación" | "Dimensionamos con precios on-demand de sa-east-1" |
| "Mensajes duplicados" como uno de los cuatro problemas | "Concurrencia sobre el mismo cupo"; el duplicado es otro problema (idempotencia) |
| Nivel 2 = WAF, CloudFront, ALB, Secretos | Nivel 2 = las **seis unidades**; WAF, ALB, secretos y observabilidad son infraestructura del diagrama |
| "Se cae un contenedor" | "Se cae un **pod**" |
| "SNS manda el mensaje al paciente" | SNS publica el evento; la pasarela de correo/SMS suscrita es la que envía |
| "sql inyection" | "inyección SQL"; XSS = "equis-ese-ese" |
| Faltaba el número de la slide 2 | Se dice: **0,0523 USD por turno** |
| Faltaba el marco EP2 | "No diseña el flujo: diseña la arquitectura que lo sostiene en producción" |
| Faltaba la frase del HIS | "No reemplaza la agenda del HIS: escribe en ella; la frontera está en la API de negocio" |
