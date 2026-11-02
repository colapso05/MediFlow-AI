# MediFlow AI

Agente conversacional de agendamiento clínico. El paciente escribe por WhatsApp (simulado en este
repositorio) y el sistema interpreta la intención, consulta disponibilidad real, **registra la
cita**, la reagenda o la cancela, y deja todo visible en un CRM para recepción.

Proyecto del curso **ITY1102 — Arquitectura de Sistemas de IA** (Duoc UC), continuación del caso
definido en la Evaluación Parcial 1 y desplegado según la arquitectura de la Evaluación Parcial 2.

Todos los datos son ficticios: 8 médicos, dos semanas de agenda, pacientes y citas de ejemplo.

---

## Qué incluye

| Pieza | Descripción |
|---|---|
| `agente.py` | Grafo LangGraph: ciclo razonar-actuar con `ToolNode`, prompt de recepcionista y límites de seguridad. |
| `herramientas.py` | Siete herramientas: consultar especialidades, médicos y horarios; reservar, listar, cancelar y reagendar. |
| `backend/main.py` | API FastAPI: chat, citas, pacientes, métricas del CRM, CRM y simulador. |
| `backend/reservas.py` | Escritura transaccional de citas con bloqueo por cupo e idempotencia. |
| `backend/servicios.py` | Consultas de lectura para la API y el CRM. |
| `frontend/` | Simulador de WhatsApp en React, conectado a `/api/chat`. |
| `backend/static/crm.html` | CRM de recepción: agenda del día por médico, agendar/atender/mover/cancelar, pacientes y conversaciones. |
| `backend/static/demo.html` | Simulador simple de respaldo, si no hay Node para compilar el frontend. |
| `database/init.sql` | Esquema y datos ficticios (se cargan solos la primera vez que arranca la base). |

---

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | reciente | PostgreSQL en un contenedor, sin instalar nada más |
| [Python](https://www.python.org/downloads/) | 3.12 | ejecutar la API y el agente |
| [Node.js](https://nodejs.org/) | 20 o superior | **opcional**: compilar el simulador en React |
| Clave de DeepSeek | — | el modelo que conversa con el paciente |

Si no tienes Node, la demo funciona igual con el simulador simple en `/demo`.

---

## Instalación paso a paso

### Windows

1. **Instala Docker Desktop** y ábrelo. Espera a que el ícono de la ballena diga "Engine running".
2. **Instala Python 3.12** marcando la casilla *Add python.exe to PATH*.
3. **Descarga el proyecto**: botón verde *Code* → *Download ZIP*, y descomprímelo
   (por ejemplo en `C:\MediFlow-AI`). También sirve `git clone`.
4. **Crea el archivo de configuración**: en la carpeta del proyecto, copia `.env.example` y
   renómbralo a `.env`.
5. **Abre `.env` con el Bloc de notas** y completa:
   - `DEEPSEEK_API_KEY=` con tu clave (más abajo se explica cómo obtenerla)
   - `POSTGRES_PASSWORD=` con una contraseña que inventes (sin espacios)
   - en `DATABASE_URL` reemplaza `CAMBIA_ESTA_CONTRASENA` por la misma contraseña
6. **Doble clic en `demo.cmd`**.

El script levanta la base, instala dependencias si faltan, compila el frontend y arranca la API.
Cuando termina, abre el CRM y el simulador en el navegador.

> El **primer arranque** puede tardar entre uno y dos minutos en equipos modestos: LangChain se
> importa y se compila a bytecode la primera vez. Los arranques siguientes son de segundos.

### macOS / Linux

```bash
# 1. Docker y Python 3.12 ya instalados

# 2. Configuración
cp .env.example .env
nano .env            # completa DEEPSEEK_API_KEY, POSTGRES_PASSWORD y DATABASE_URL

# 3. Base de datos
docker compose up -d

# 4. Entorno de Python
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 5. Frontend (opcional, requiere Node)
cd frontend && npm install && npm run build && cd ..

# 6. Arranque
./arrancar.sh
```

### Arranque manual (cualquier sistema)

```bash
docker compose up -d
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

En Windows la ruta del intérprete es `.venv\Scripts\python.exe`.

---

## Cómo obtener la clave de DeepSeek

1. Entra a <https://platform.deepseek.com> y crea una cuenta.
2. En el menú lateral, abre **API keys** → **Create new API key**.
3. Copia la clave (empieza con `sk-`); solo se muestra una vez.
4. Pégala en `.env`, en la línea `DEEPSEEK_API_KEY=`.
5. Si la cuenta no tiene saldo, en **Top up** puedes cargar el mínimo. El costo real del agente es
   de fracciones de centavo por conversación.

La clave **nunca** se sube al repositorio: `.env` está en `.gitignore`. Cada persona que clone el
proyecto usa la suya.

---

## Agrupación de mensajes (ventana de 5 s)

En WhatsApp real el paciente escribe varias veces seguidas: "hola", "necesito hora", "con el doctor rojas".
La API agrupa esos mensajes y responde **una sola vez**, no tres. La ventana es de 5 segundos: si el paciente deja de escribir 5 s, se responde el lote completo.

- Se configura con `VENTANA_AGRUPACION` en `.env` (segundos; por defecto `5`).
- Cada mensaje del mismo teléfono **reinicia** la ventana; cuando pasa ese tiempo sin mensajes nuevos, el lote se procesa en un solo turno del agente y todos los envíos pendientes reciben la misma respuesta.
- En el simulador se ven los tres mensajes del paciente y **una sola respuesta**, con el chip "N mensajes agrupados".

Para cambiarla: editá `.env`, guardá y **reiniciá la API** (cerrá la ventana "MediFlow API" y volvé a ejecutar `demo.cmd`). El código está en `backend/main.py`, línea 213.

---

## Reglas de agenda

- **Un cupo, una cita.** Se garantiza en la base con el índice único `citas_horario_activo_idx`.
- **Un paciente puede tener varias citas**, incluso el mismo día y con especialistas distintos.
- **No puede tener dos a la misma hora**: si intenta reservar otra que se solape con una cita activa, la API responde `409` con el médico y la especialidad que ya ocupa esa franja, y el agente le ofrece moverla, cancelarla o elegir otro horario. Se valida en `backend/reservas.py` (`_cita_solapada`), también al reagendar.
- **Idempotencia**: la misma clave con la misma huella devuelve la misma cita; no duplica por reintento.

---

## Direcciones una vez arrancado

| Página | Dirección |
|---|---|
| Simulador de WhatsApp (React) | <http://127.0.0.1:8000/app> |
| CRM de recepción | <http://127.0.0.1:8000/crm> |
| Simulador simple de respaldo | <http://127.0.0.1:8000/demo> |
| Documentación interactiva de la API | <http://127.0.0.1:8000/docs> |

Todo se sirve por el mismo puerto (8000).

## Cómo apagar

```bash
docker compose down      # detiene la base (los datos se conservan)
```

En Windows, `detener.cmd` hace lo mismo y cierra la ventana de la API.

---

## Flujo que resuelve el agente

1. El paciente pide una hora (por especialidad o por médico).
2. El agente consulta especialidades, médicos y **horarios libres reales**.
3. Pide el **nombre completo y el RUT**. El RUT se normaliza y se valida con el módulo 11
   (`backend/rut.py`): se acepta con puntos, sin puntos, con o sin guion y con `K` minúscula.
   Si el dígito verificador no calza, no se escribe nada y el agente lo pide de nuevo.
4. Repite la opción elegida y pide confirmación antes de escribir nada.
5. Llama a `reservar`: la base bloquea el cupo y garantiza una sola cita activa por horario.
6. Devuelve el número de cita, el médico, la fecha, la hora y el RUT registrado.
7. Puede `reagendar` a otro cupo del mismo médico o `cancelar`, siempre sobre las citas del
   teléfono que está conversando.

La identidad del paciente se fija en el servidor con un `ContextVar` a partir del número de
WhatsApp: el modelo no puede cambiarla ni consultar citas de terceros. El RUT es único en la
tabla `pacientes`, así que no puede haber dos fichas para la misma persona; si un RUT aparece
asociado a otro número, la reserva se deriva a recepción en lugar de mezclar historiales.

**Si ya tienes la base creada de antes** (sin la columna `rut`), aplica la migración:

```bash
.venv\Scripts\python.exe database\migracion_rut.py
```

---

## API

| Método | Ruta | Uso |
|---|---|---|
| `POST` | `/api/chat` | Conversación con el agente (`mensaje`, `historial`, `telefono`) |
| `GET` | `/api/health` | Estado de la API y de la base |
| `GET` | `/api/medicos` | Listado de médicos con especialidad |
| `GET` | `/api/horarios` | Cupos libres por médico o especialidad |
| `GET` | `/api/agenda` | Cupos de un médico en una fecha, con la cita si está ocupado |
| `GET` | `/api/citas` | Citas con filtros (`estado`, `medico_id`, `desde`, `hasta`, `q`) |
| `POST` | `/api/citas` | Reserva directa (canal `recepcion` o `agente`) |
| `POST` | `/api/citas/{id}/cancelar` | Cancelación |
| `POST` | `/api/citas/{id}/reagendar` | Cambio de cupo |
| `POST` | `/api/citas/{id}/completar` | Marcar la cita como atendida |
| `GET` | `/api/pacientes` | Fichas con conteo de citas |
| `GET` | `/api/crm/resumen` | Indicadores para el CRM |
| `GET` | `/api/conversaciones` | Últimos mensajes del agente |

---

## Decisiones técnicas

- **Idempotencia**: clave derivada de `teléfono + horario + nombre` (UUID v5) más huella del
  contenido. Un reintento del modelo devuelve la misma cita en lugar de duplicarla.
- **Concurrencia**: `SELECT ... FOR UPDATE` sobre el cupo e índice único parcial; dos pacientes no
  pueden tomar la misma hora (la segunda reserva recibe `409`).
- **Identidad**: el teléfono es la llave del paciente; la ficha se reutiliza y se actualiza el
  nombre si cambia.
- **Guardrails**: sin diagnósticos ni recetas, sin identificadores internos, sin promesas de
  notificaciones; las herramientas devuelven `ok=false` para que el agente ofrezca alternativas
  en lugar de inventar datos.

## Pruebas

```bash
# Linux / macOS
.venv/bin/python -m unittest test_agenda.py test_reservas.py test_rut.py -v

# Windows
.venv\Scripts\python.exe -m unittest test_agenda.py test_reservas.py test_rut.py -v
```

28 pruebas: motor de agenda y reservas (cupo ocupado, idempotencia, cancelación de una cita
ajena, reagendamiento) y normalización y validación del RUT con módulo 11 (formatos con
puntos, sin puntos, sin guion, `K` y rechazos).

### Verificación adversarial del agente

Con la API levantada, lanza 20 ataques (inyección de prompt, cambio de rol, datos de
otro paciente, inyección SQL, abuso de reserva, respuestas vacías) y falla si el agente
filtra algo o deja al paciente sin respuesta:

```bash
# Windows
.venv\Scripts\python.exe tests\verificar_agente.py --repeticiones 3

# Linux / macOS
.venv/bin/python tests/verificar_agente.py --repeticiones 3
```

Los bloqueos quedan contados en `GET /api/guardrails`.

### Límite conocido de la demo local

La demo corre en tu equipo y **sin autenticación**: `/crm` y los endpoints de lectura
(`/api/pacientes`, `/api/citas`, `/api/conversaciones`) responden a cualquiera que alcance
el puerto 8000, con datos ficticios de prueba. El agente sí limita cada conversación a su
propio teléfono. No expongas este puerto a internet: en la arquitectura desplegada el
acceso va detrás de ALB con autenticación y mTLS entre servicios.

---

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `docker: command not found` o `error during connect` | Docker Desktop está cerrado. Ábrelo y espera a que el motor arranque. |
| La API responde `502 No fue posible obtener respuesta del agente` | La base no está arriba o la clave de DeepSeek no es válida. Revisa `docker ps` y el `.env`. |
| "No pude conectar con el servidor" en el simulador | La ventana de la API se cerró. Vuelve a ejecutar `demo.cmd`. |
| El CRM aparece sin cupos | Es domingo o el médico no atiende ese día. Usa "Ir al próximo día con agenda". |
| `port is already allocated` | Otro PostgreSQL ocupa el 5433. Cambia el puerto en `docker-compose.yml` y en `DATABASE_URL`. |
| `/app` da 404 | Falta compilar el frontend. Ejecuta `cd frontend && npm install && npm run build`, o usa `/demo`. |

---

## Ejecutar con Docker

El repositorio incluye el `Dockerfile` del servicio de API y agente (dos etapas, usuario sin
privilegios, healthcheck contra `/api/health`).

```bash
# Construir la imagen
docker build -t mediflow-api:local .

# Arrancar la API en el puerto 8000, apuntando a la base del compose
docker run -d --name mediflow-api -p 8000:8000 \
  -e DEEPSEEK_API_KEY=tu_clave \
  -e DATABASE_URL="postgresql://mediflow:tu_password@host.docker.internal:5433/mediflow_db" \
  mediflow-api:local
```

En un clúster real la base se resuelve por el nombre del servicio interno, no por
`host.docker.internal`, y la configuración entra por Secrets Manager.

## Documentación técnica

La entrega de la evaluación está en [`docs/`](docs/):

| Archivo | Contenido |
|---|---|
| `docs/EP2_Zuniga_Burgos_Cortez.pdf` | Informe técnico arc42 con los diagramas C4, dimensionamiento, patrones, seguridad y costos |
| `docs/EP2_Presentacion_Zuniga_Burgos_Cortez.pdf` | Apoyo gráfico de la defensa (10 diapositivas) |
| `docs/Guia_para_entender_la_presentacion.pdf` | Glosario técnico y recorrido de cada diapositiva en lenguaje simple |
| `docs/guion_defensa.md` | Guion minuto a minuto de la exposición |
| `docs/guion_demo_agente.md` | Guion de la demo en vivo del agente y del CRM |

Asignatura ITY1102 — Arquitectura de Sistemas de Inteligencia Artificial, Duoc UC.
Integrantes: Demis Zúñiga, Bruno Burgos, Matías Cortez.
