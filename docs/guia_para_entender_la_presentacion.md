# Guía para entender y defender la presentación

**MediFlow AI · EP2 ITY1102 · Demis Zúñiga, Bruno Burgos, Matías Cortez**

Esta guía explica en palabras simples todo lo que aparece en las 10 diapositivas. No es el guion: es el "qué significa". Léela una vez completa y después vuelve solo a la sección 4 mientras practicas.

---

## 1. La idea en 30 segundos

Un paciente escribe por WhatsApp "necesito hora con el dermatólogo". Un agente de IA entiende el mensaje, busca los cupos reales en la base de datos, ofrece tres horarios, y cuando el paciente elige uno, **graba la cita de verdad**. La secretaria lo ve en un panel (el CRM) y puede mover, cancelar o marcar la hora como atendida.

Lo que hace **difícil** esto no es el chat. Es lo que hay detrás:

1. **Dos personas pueden pedir el mismo cupo al mismo tiempo** → hay que impedir que se duplique.
2. **Los servidores se caen** → si un contenedor muere a mitad de la conversación, la cita no puede quedar a medias.
3. **Son datos de salud** → no pueden viajar al proveedor del modelo ni quedar en los registros tal cual.
4. **Cada mensaje cuesta plata** → el costo no es fijo, crece con el uso.

La arquitectura de la EP2 responde a esos cuatro problemas. Eso es lo que estás defendiendo.

---

## 2. Cómo leer un diagrama C4 (sin saber de arquitectura)

C4 es una forma de dibujar un sistema en **cuatro niveles de zoom**, como los mapas: el mapa de Chile, el de la ciudad, el del barrio y el de tu casa. La pauta pide los tres primeros.

| Nivel | Nombre | Qué muestra | Analogía |
|---|---|---|---|
| C1 | **Contexto** | El sistema como **una sola caja**, con quién lo usa y con qué servicios externos habla | Una foto aérea del edificio y quién entra y sale |
| C2 | **Contenedores** | Las **piezas grandes** que hay dentro: la API, el agente, la base de datos, la cola | El plano del edificio: cada oficina y para qué sirve |
| C3 | **Componentes** | Lo que hay **dentro de una oficina**: los módulos del servicio de agente | El plano del mobiliario de una oficina |

**"Contenedor" en C4 no es Docker.** Es una unidad desplegable: un servicio, una base, una cola. Confundirlos es el error más común en la defensa. Si te preguntan, di: "contenedor en C4 es una unidad que se despliega por separado; puede ser un contenedor Docker, pero también una base de datos gestionada".

---

## 3. Glosario en lenguaje simple

### Nube y red

- **Región**: el lugar físico del mundo donde están los servidores. Usamos `sa-east-1`, que es São Paulo. Se eligió por cercanía a Chile: menos latencia.
- **Zona de disponibilidad (AZ)**: un edificio de servidores independiente dentro de la región. São Paulo tiene tres. Si se cae una, las otras siguen. Por eso todo lo crítico se reparte en **dos**.
- **VPC**: la red privada del sistema dentro de AWS. Es como el condominio cerrado donde vive todo.
- **Subred pública**: la parte de la red que tiene puerta a internet. Ahí van solo el balanceador y el NAT.
- **Subred privada**: sin puerta a internet. Ahí van la base de datos y los servidores de aplicación. Es la diferencia entre el "hall del edificio" y la "bodega con clave".
- **Security Group**: el portero de cada servidor. Define quién puede entrar y a qué puerto. La base solo acepta conexiones desde la aplicación, nadie más.
- **NAT Gateway**: la puerta de salida. Los servidores privados no pueden salir a internet, pero necesitan llamar al proveedor de IA (DeepSeek). El NAT les deja **iniciar** la conexión sin que nadie pueda entrar desde afuera. Cuesta USD 135,78 al mes por dos (uno por zona).
- **CloudFront**: la red de caché global. Guarda los archivos estáticos cerca del usuario para que carguen rápido.
- **WAF**: el cortafuegos de aplicaciones. Filtra ataques conocidos (inyección SQL, XSS) y limita cuántas peticiones puede hacer una misma IP.

### Cómputo

- **Kubernetes**: el sistema que administra contenedores. Tú le dices "quiero 4 copias de esta aplicación" y él las levanta, las reinicia si mueren y las reparte entre servidores.
- **EKS**: Kubernetes administrado por AWS. AWS mantiene el cerebro del clúster; nosotros solo los servidores donde corren las aplicaciones. Cuesta USD 73 al mes solo el plano de control.
- **Pod**: la unidad más pequeña en Kubernetes. Es un contenedor (o un grupito) corriendo tu aplicación. Se levantan y mueren todo el tiempo, y eso está bien.
- **Node group**: el grupo de servidores (EC2) que prestan capacidad al clúster. Tenemos tres, separados por tipo de trabajo: **app** (API, herramientas, gateway), **agente** (el que piensa) y **observabilidad** (las métricas).
- **HPA (Horizontal Pod Autoscaler)**: el que agrega o quita pods solo. Si la CPU pasa de 65 %, agrega. Si baja, quita. Así el pico de 5× no requiere tener servidores ociosos todo el mes.
- **PDB (Pod Disruption Budget)**: la regla que impide que, durante un mantenimiento, se apaguen todos los pods a la vez. Garantiza que siempre quede al menos uno vivo.
- **Requests y limits**: cuánta CPU y memoria **reserva** cada pod (requests) y cuánto puede **usar como máximo** (limits). Sin esto, un pod se come la memoria del resto.
- **Sonda de vida (liveness)**: la pregunta "¿estás vivo?" cada pocos segundos. Si no responde, Kubernetes lo mata y levanta otro.
- **Sonda de disponibilidad (readiness)**: "¿puedes atender tráfico ya?". Si no, deja de mandarle usuarios pero no lo mata. Sirve mientras arranca.
- **Rollout progresivo**: actualizar de a poco, no todos los pods de golpe. Si la versión nueva falla, se detiene el despliegue y quedan los viejos funcionando.

### Balanceo de carga

- **ALB (Application Load Balancer)**: el recepcionista de entrada. Recibe todo el tráfico HTTPS y lo reparte entre las zonas y servidores disponibles.
- **Health check**: el ALB le pregunta al servidor "¿estás sano?" cada 10 segundos, contra `/api/health`. Si falla tres veces, deja de mandarle tráfico.
- **NGINX Ingress Controller**: el que reparte **dentro** del clúster. El ALB le entrega la petición y Nginx decide a qué servicio y a qué pod va. Se usa `least_conn`: manda al pod con menos conexiones abiertas, no al que va por turnos. ¿Por qué? Porque una conversación con el agente tarda 2–10 segundos y abre una conexión larga; repartir por turnos dejaría un pod con cinco conversaciones y otro con una.
- **LCU**: la unidad con que AWS cobra el ALB además del precio fijo (mide conexiones y tráfico). En el informe son 10 LCU-h.

### Datos

- **RDS**: la base de datos administrada por AWS. AWS hace los respaldos y las actualizaciones.
- **Multi-AZ**: la base tiene una copia en otra zona lista para tomar el control si la principal se cae. Cuesta más, pero un fallo de zona no bota el sistema.
- **gp3**: el tipo de disco de AWS. En Multi-AZ se escribe en dos zonas a la vez.
- **ElastiCache / Redis**: memoria rápida para guardar cosas que no vale la pena ir a buscar a la base en cada mensaje: la sesión del paciente, la clave de idempotencia y el punto donde quedó la conversación (checkpoint).
- **Índice**: como el índice de un libro. Sin él, la base leería todas las filas para encontrar una cita. Con él va directo.
- **Restricción de exclusión (GiST)**: una regla **dentro de la base** que impide que un mismo médico tenga dos cupos que se solapen. Es la garantía de que no hay doble reserva, aunque el código falle.

### Mensajería y eventos

- **Cola (SQS)**: una fila de mensajes pendientes. Cuando llega un turno de WhatsApp, se encola y un trabajador libre lo toma. Sirve para que un pico de 5× no tumbe la aplicación: la cola aguanta y se procesa más lento.
- **Desacoplar**: que dos partes del sistema no dependan una de la otra en tiempo real. Si el agente se cae, la cola guarda los mensajes y no se pierde nada.
- **DLQ (cola de mensajes muertos)**: donde caen los mensajes que fallaron tres veces. Se revisan a mano en lugar de perderse.
- **Webhook**: la forma en que WhatsApp nos avisa que llegó un mensaje. Le respondemos 200 en menos de 100 ms (o sea, "recibido") y procesamos después.
- **SNS**: el servicio de notificaciones de AWS; publica un aviso a varios interesados a la vez.

### Seguridad

- **Autenticación**: quién eres. Aquí: el paciente se identifica por teléfono y un código de un solo uso (OTP); la secretaria entra con usuario y contraseña.
- **Autorización**: qué puedes hacer. Un paciente puede ver **sus** citas; la secretaria puede ver la agenda de todos. Esto es **RBAC** (control por rol).
- **Encriptación en tránsito**: los datos van cifrados por la red (TLS/HTTPS). Nadie que intercepte ve el contenido.
- **Encriptación en reposo**: los datos están cifrados en el disco (KMS). Si alguien roba el disco, no puede leerlo.
- **mTLS**: cifrado en el que **las dos partes** se identifican con certificado, no solo el servidor. Se usa entre servicios internos.
- **Secrets Manager**: la caja fuerte de las claves. La clave de DeepSeek no está en el código: se pide en tiempo de ejecución.
- **Mínimo privilegio**: cada componente tiene solo los permisos que necesita. El servicio de agenda no puede leer las claves de facturación.
- **Seudonimización**: reemplazar el nombre y el RUT por un código antes de que el dato salga al proveedor del modelo o quede en un log.
- **Guardrails**: filtros a la entrada y a la salida del modelo. A la entrada, bloquean intentos de manipulación; a la salida, impiden que invente datos clínicos o filtre información de otro paciente.
- **Deriva (drift)**: cuando el sistema empieza a comportarse distinto sin que nadie haya cambiado el código (por ejemplo, el proveedor actualiza el modelo y las respuestas empeoran). Se monitorea con un tablero.

### Monitoreo

- **Prometheus**: recolecta los números del sistema cada 15 segundos (CPU, memoria, latencia, errores) y los guarda como series de tiempo.
- **Grafana**: los tableros. Convierte esos números en gráficos y alertas. **Es lo que la pauta pide explícitamente.**
- **Loki**: guarda los registros (logs) de texto de los servicios y los busca rápido.
- **OpenTelemetry**: el estándar para instrumentar el código. Genera una **traza** por cada turno.
- **Traza y span**: la traza es el recorrido completo de una conversación; cada span es un paso (recibir, clasificar, consultar cupos, reservar, responder). Sirve para saber **dónde** se demoró.
- **p95**: el percentil 95. Si la latencia p95 es 3 s, significa que 95 de cada 100 turnos demoraron 3 segundos o menos. Se usa p95 y no el promedio porque el promedio esconde a los usuarios que sufren.
- **SLO**: el objetivo de calidad que prometemos. Ejemplo: 99,5 % de turnos respondidos en menos de 8 segundos.
- **Error budget**: cuánto puede fallar el sistema dentro del SLO antes de que sea un problema. Si se gasta el presupuesto, se dejan las features y se arregla la estabilidad.
- **Alerta**: aviso automático cuando un número rompe el umbral (CPU alta, errores 5xx, cola creciendo).

### Alta disponibilidad

- **RPO (Recovery Point Objective)**: cuánta información puedo perder si todo se cae. RPO 5 minutos = como máximo se pierden 5 minutos de datos.
- **RTO (Recovery Time Objective)**: cuánto puedo tardar en volver a funcionar. RTO 30 minutos = media hora máximo.
- **Failover**: el cambio automático a la copia de respaldo cuando la principal falla.
- **Respaldo probado**: un respaldo que nunca se restauró no es un respaldo. En el plan se ensaya la restauración.

### IA

- **LLM**: el modelo de lenguaje (aquí DeepSeek) que entiende y redacta. Es externo: no corre en nuestra infraestructura.
- **Token**: la unidad con que se cobra y se mide el texto en un LLM (más o menos 3/4 de una palabra). Si el proveedor cobra por token, el costo crece con cada mensaje.
- **Tool calling (herramientas)**: el modelo no inventa; pide ejecutar una función real (`buscar_medicos`, `agendar_cita`). El sistema la ejecuta contra la base y le devuelve el resultado.
- **Grafo de estados**: el ciclo del agente dibujado como cajas y flechas (recibir → clasificar → planificar → ejecutar → validar → responder). Cada caja se puede guardar, auditar y reanudar.
- **Checkpoint**: la foto del estado en cada nodo del grafo. Si el pod muere, se retoma desde la última foto.
- **Idempotencia**: hacer la misma operación dos veces deja el mismo resultado que hacerla una. Si el modelo reintenta "agenda la hora", no se crean dos citas: la segunda devuelve la primera.
- **Gateway de LLM**: un servicio intermediario que enmascara datos personales, controla cuotas, aplica timeout y corta el paso si el proveedor falla.

### Dinero y capacidad

- **On-demand**: pagar por hora de uso, sin contrato. Es lo que se cotizó.
- **vCPU**: procesador virtual. **GiB** es memoria (1 GiB ≈ 1,07 GB; el GiB es la medida real, el GB comercial es más chico).
- **m6i.xlarge**: el tipo de servidor: familia m (uso general), 6ª generación, i (Intel), xlarge = 4 vCPU y 16 GiB.
- **Turno**: un mensaje del paciente más la respuesta del bot. 72.000 turnos al mes = 300 conversaciones diarias × 8 turnos × 30 días.

### WhatsApp (el canal)

- **WhatsApp Business Platform (Cloud API)**: la API oficial de Meta para que un negocio converse por WhatsApp.
- **Mensaje de servicio**: la respuesta libre del bot dentro de las 24 horas desde el último mensaje del paciente.
- **Plantilla (template)**: mensaje preaprobado por Meta, obligatorio para escribir **fuera** de esas 24 horas (por ejemplo, el recordatorio de la cita del día siguiente).
- **Categorías**: *marketing* (promociones), *utility* (recordatorios, confirmaciones), *authentication* (códigos), *service* (respuestas del bot).
- **Ventana de 24 horas**: el plazo en que puedes responder libremente después de que el paciente escribió.
- **Free entry point (72 h)**: si la conversación se inició desde un anuncio con click-to-WhatsApp, hay 72 horas sin costo.

---

## 4. Recorrido de las 10 diapositivas

### 1 · Portada
Di: "Somos Demis Zúñiga, Bruno Burgos y Matías Cortez. Vamos a presentar la arquitectura de MediFlow AI, un agente conversacional que agenda horas clínicas de verdad, no un prototipo de chat."

### 2 · El caso
Qué se ve: la descripción del problema y dos cifras grandes: **72.000 turnos al mes** y **USD 0,0523 por turno**.

Qué significa: el sistema atiende 300 conversaciones diarias de 8 turnos cada una. Y ese número manda: define cuántos servidores, cuánta cola y cuánto cuesta.

Frase: "La arquitectura resuelve cuatro problemas que un prototipo no enfrenta: concurrencia sobre el mismo cupo, reanudación tras una caída, datos de salud sensibles y costo variable por turno."

### 3 · C4 Nivel 1 — Contexto
Qué se ve: una caja (MediFlow) con el paciente, la secretaria, WhatsApp, el proveedor del modelo y la base de datos alrededor.

Qué significa: es el mapa general: quién usa el sistema y de qué servicios externos depende.

Frase: "En el nivel 1 mostramos que el sistema depende de tres cosas externas: la plataforma de WhatsApp de Meta, el proveedor del modelo y la base de datos. Nada más entra ni sale."

### 4 · C4 Nivel 2 — Contenedores
Qué se ve: las **seis unidades desplegables**: adaptador de canal (webhook), API de negocio, servicio de agente, servicio de herramientas, gateway de LLM y la base de datos, más Redis y la cola.

Qué significa: se separó por responsabilidad y por **motivo de escalado**. El que piensa (agente) escala distinto que el que atiende peticiones (API).

Frase: "Separamos lo que piensa de lo que atiende. El agente escala por profundidad de cola; la API escala por CPU. Si estuvieran juntos, tendríamos que sobredimensionar los dos."

### 5 · C4 Nivel 3 — Componentes
Qué se ve: dentro del servicio de agente, los módulos: recepción del turno, clasificador de intención, planificador, ejecutor de herramientas, validador y redactor de respuesta.

Qué significa: es el detalle del ciclo razonar-actuar. Cada módulo tiene una función y se puede probar por separado.

Frase: "Cada componente es un nodo del grafo. Eso permite probar el clasificador sin llamar al modelo y auditar qué decidió el sistema en cada paso."

### 6 · Patrones
Qué se ve: "Microservicios con contenedores" y "arquitectura dirigida por eventos".

Qué significa: **la pauta pide explícitamente los patrones**, y son dos:
- Microservicios: cada servicio se despliega aparte, no comparten base de datos, la API es la única puerta de escritura.
- Eventos: el webhook responde 200 en menos de 100 ms y publica en la cola; SQS absorbe el pico; la DLQ guarda los que fallan tres veces.

Frase: "Ningún servicio lee la base de otro. La comunicación es por API o por eventos, y eso es lo que permite desplegar uno sin tocar los demás."

### 7 · Dimensionamiento y costo
Qué se ve: la tabla de recursos con su precio, y el desglose: **2.297,19 de infraestructura + 1.465,00 de canal = 3.762,19 al mes**.

Qué significa: el costo se calculó con precios on-demand reales de São Paulo al 25/10/2026, y el dimensionamiento parte de la carga (72.000 turnos y pico de 5×), no al revés.

Frase clave: "El hallazgo del capítulo es que el canal pesa 39 % del costo. Meta empezó a cobrar las respuestas del bot desde el 1 de octubre de 2026: 0,02 dólares por mensaje entregado en Chile, con mil gratis al mes. Por eso el costo por turno no es 0,0319 de infraestructura, sino 0,0523 con el canal incluido. Optimizar servidores no mueve la aguja si el volumen de mensajes no se controla."

### 8 · Kubernetes, escalado y balanceo
Qué se ve: dos columnas: EKS/Node groups/HPA y Balanceo/ALB/NGINX.

Qué significa: **la pauta pide orquestación y balanceo con Nginx**. Son dos capas:
1. El **ALB** (de AWS) reparte entre zonas y pregunta `/api/health` cada 10 segundos.
2. **NGINX Ingress** reparte dentro del clúster y usa `least_conn`.

Frase: "Usamos dos capas a propósito. El ALB no conoce los pods; Nginx sí. Y como las conexiones del agente duran segundos, repartimos por conexiones abiertas y no por turnos."

### 9 · Seguridad, observabilidad y alta disponibilidad
Qué se ve: el plan de seguridad en **10 puntos y 3 fases** (gobierno, datos y modelo, operación), y monitoreo con **Prometheus + Grafana + Loki**.

Qué significa: cubre lo que la pauta pide: **autenticación** (OTP para el paciente, usuario y contraseña para la secretaria), **autorización** (RBAC por rol) y **encriptación** (TLS en tránsito, KMS en reposo, mTLS entre servicios).

Frase: "Grafana es el tablero donde se ve latencia p95, errores, profundidad de cola y deriva del modelo. Y el respaldo no se supone: se restaura en un ensayo."

### 10 · Cinco decisiones
Qué se ve: la tabla de decisiones con la alternativa descartada y el motivo.

Qué significa: demuestra que las decisiones se pensaron contra una alternativa, no por gusto.

Frase: "Cada decisión descarta una alternativa concreta: EKS sobre ECS, PostgreSQL sobre NoSQL, SQS sobre Kafka. Y las cinco están implementadas en el repositorio, no solo dibujadas."

---

## 5. Los cuatro números que sí o sí debes saber

| Dato | Valor | De dónde sale |
|---|---|---|
| Turnos al mes | **72.000** | 300 conversaciones/día × 8 turnos × 30 días |
| Costo de infraestructura | **USD 2.297,19/mes** | Tabla de precios on-demand `sa-east-1` |
| Costo del canal WhatsApp | **USD 1.465,00/mes** | 71.000 mensajes × USD 0,0200 (Chile, desde 1/10/2026) |
| Costo total por turno | **USD 0,0523** | 3.762,19 ÷ 72.000 |

Si te preguntan "¿y cuánto cuesta?", esa es la respuesta completa. Decir solo 2.297 es la mitad de la verdad.

---

## 6. Ocho preguntas que te pueden hacer

**1. ¿Por qué Kubernetes y no algo más simple?**
Porque hay servicios con perfiles de escalado distintos (el agente escala por cola, la API por CPU), y EKS da HPA por métrica de cola, políticas de red entre servicios y despliegue progresivo. El plano de control cuesta 73 dólares sobre 3.762: no es la decisión económica.

**2. ¿Cómo evitan que dos pacientes tomen la misma hora?**
Con una restricción de exclusión en PostgreSQL que impide solapamientos por médico, más `SELECT FOR UPDATE` al reservar y una clave de idempotencia. La base rechaza la segunda reserva aunque lleguen al mismo tiempo; al usuario le devuelve 409 "el horario ya no está disponible". Está probado.

**3. ¿Qué pasa si se cae un pod en medio de la conversación?**
El estado del grafo está guardado en Redis con un checkpoint por nodo. Otro pod retoma desde el último nodo, y como la reserva es idempotente, no se duplica la cita.

**4. ¿Por qué Nginx si ya tienen el ALB?**
El ALB balancea entre zonas y no conoce los pods. Nginx Ingress sí: enruta por ruta, aplica límites de tasa por servicio y reparte con `least_conn`, que es lo que conviene cuando las conexiones duran segundos.

**5. ¿Dónde está Grafana?**
En el node group de observabilidad, con Prometheus y Loki. Mide latencia p95 por turno, errores 5xx, profundidad de cola, y un tablero de deriva del modelo. Las alertas van a Grafana y a CloudWatch para lo de infraestructura.

**6. ¿Qué datos del paciente salen al proveedor del modelo?**
Ninguno identificable. Antes de salir, el gateway de LLM reemplaza nombre, RUT y teléfono por un código (seudonimización). Los logs tampoco guardan datos clínicos identificables.

**7. ¿Está desplegado en AWS?**
No. Lo desplegado es el sistema completo funcionando en local con Docker: agente, base con 8 médicos y 1.328 cupos, CRM de recepción y simulador de WhatsApp. La arquitectura AWS es el diseño objetivo con precios reales. Decirlo así te deja bien: la pauta pide diseño, no producción.

**8. ¿Cuánto se demora una respuesta?**
De 2 a 10 segundos de punta a punta. El webhook responde en menos de 100 ms y el turno se procesa en la cola. Ese es el motivo del diseño asíncrono: si respondiéramos esperando al modelo, WhatsApp cortaría la conexión en los picos.

---

## 7. Errores que no puedes cometer

1. **No digas que está en producción en AWS.** Es un diseño con precios reales y un sistema funcionando en local.
2. **No digas "contenedor" pensando en Docker** cuando hablas de C4. Son unidades desplegables.
3. **No digas solo 2.297 de costo.** El total es 3.762,19; el canal pesa 39 %.
4. **No inventes que usamos Kubernetes por moda.** La razón es el escalado por perfiles distintos.
5. **No prometas GPU.** La inferencia es externa; no se compra GPU en la ruta en línea.
6. **Si no sabes algo, di "eso no lo medimos".** Es mejor que improvisar un número.

---

## 8. Orden de exposición sugerido (10 minutos)

| Min | Quién | Qué |
|---|---|---|
| 0:00–0:40 | Demis | Portada y el caso en una frase |
| 0:40–2:00 | Demis | C4 nivel 1 y 2: qué piezas hay y por qué están separadas |
| 2:00–3:10 | Bruno | C4 nivel 3: el ciclo del agente y las herramientas |
| 3:10–4:20 | Bruno | Patrones: microservicios y eventos |
| 4:20–5:40 | Matías | Dimensionamiento y costos: los cuatro números |
| 5:40–7:00 | Matías | Kubernetes, HPA y las dos capas de balanceo |
| 7:00–8:20 | Demis | Seguridad en tres fases y monitoreo con Grafana |
| 8:20–9:20 | Bruno | Las cinco decisiones |
| 9:20–10:00 | Demo o cierre | El sistema funcionando en local (si el profe lo permite) |

Lo que cada uno debe poder responder sin mirar el informe: Demis → seguridad y C4; Bruno → agente y patrones; Matías → números y Kubernetes.

---

## 9. Glosario mínimo de siglas

| Sigla | Significado |
|---|---|
| C4 | Context, Containers, Components, Code (niveles de diagrama) |
| VPC | Virtual Private Cloud (red privada en AWS) |
| AZ | Availability Zone (zona de disponibilidad) |
| EKS | Elastic Kubernetes Service |
| HPA | Horizontal Pod Autoscaler |
| PDB | Pod Disruption Budget |
| ALB | Application Load Balancer |
| LCU | Load Balancer Capacity Unit (unidad de cobro del ALB) |
| RDS | Relational Database Service |
| SQS / SNS | cola simple / notificaciones simples de AWS |
| DLQ | Dead Letter Queue (cola de mensajes muertos) |
| WAF | Web Application Firewall |
| KMS | Key Management Service (cifrado de discos) |
| RBAC | Role-Based Access Control |
| TLS / mTLS | cifrado en tránsito / cifrado mutuo entre servicios |
| OTP | One-Time Password (código de un solo uso) |
| RPO / RTO | pérdida máxima de datos / tiempo máximo de recuperación |
| SLO | Service Level Objective |
| p95 | percentil 95 de latencia |
| LLM | Large Language Model |
