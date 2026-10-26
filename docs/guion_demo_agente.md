# Guion de la demo en vivo — MediFlow AI (5 a 7 minutos)

> Uso interno. Se ejecuta después de la presentación de arquitectura, cuando el profe pide
> "muéstrenme funcionando".

## Antes de empezar

**La noche anterior / 10 minutos antes:**

1. Doble clic en `demo.cmd` (raíz del proyecto). Levanta Postgres, arranca la API y abre las dos
   pestañas: WhatsApp (`http://127.0.0.1:8000/app`, el simulador en React del repo) y CRM
   (`http://127.0.0.1:8000/crm`).
2. Verificar que la franja verde del CRM diga "última sincronización …" con la hora actual. Si no
   dice eso, la API no está respondiendo: revisar la ventana negra "MediFlow API".
3. Dejar el CRM **a la derecha** y el WhatsApp **a la izquierda** si el proyector lo permite:
   la gracia es que se vea la cita aparecer en el CRM mientras se conversa.
4. Tener abierto `/docs` en una pestaña de respaldo (Swagger), por si piden ver la API.

**Lo que NO hay que hacer:** no reiniciar los contenedores durante la demo (la primera
sincronización tarda unos segundos y el profe va a pensar que se cayó).

## Guion

### 1. Encuadre (20 segundos)
> "El caso de la EP1 era agendar horas conversando. Esto es ese caso funcionando de punta a punta:
> WhatsApp a la izquierda, CRM de recepción a la derecha. Todo lo que pase en el chat se escribe en
> PostgreSQL y aparece en el CRM."

### 2. Consultar sin reservar (1 minuto)
Escribir en el WhatsApp:

```
Hola, necesito una hora con dermatología
```

Qué debe pasar: el agente consulta especialidades, médicos y horarios reales, y ofrece tres
opciones concretas con fecha.

> "Fíjense que no inventa horarios: las tres horas que ofrece salen de la tabla `horarios`."

### 3. Reservar (1,5 minutos)
Escribir:

```
Me sirve la de las 15:00. Soy Demis Zúñiga, demis@example.com
```

Qué debe pasar: repite la opción y **pide confirmación** antes de escribir. Luego:

```
Sí, confirma
```

Qué debe pasar: entrega el **número de cita**, médico, fecha y hora. Girar al CRM:

- Sube el contador **Confirmadas**.
- En la **agenda del día**, en el médico elegido, el cupo aparece con el nombre del paciente,
  el teléfono y el canal `whatsapp`, y con los botones **Atendida / Mover / Cancelar**.
- En "Conversación del agente" queda el registro completo del diálogo.

> "El CRM no está leyendo el chat: está leyendo la base de datos. Es el mismo modelo de dominio del
> diagrama ER."

> "Y esto es lo que ve la secretaria: la agenda real del doctor, cupo por cupo, con la hora que
> acaba de agendar el agente."

### 4. El detalle técnico que da nota (1 minuto)
Escribir de nuevo:

```
Sí, confirma
```

Qué debe pasar: responde con **el mismo número de cita**, no crea otra.

> "Esto es idempotencia: la clave se deriva de teléfono + horario + nombre, así que un reintento del
> modelo o un doble clic del paciente devuelve la misma cita. Está en `backend/reservas.py` y en el
> ADR-05 del documento."

### 5. Reagendar y cancelar (1,5 minutos)
Escribir:

```
¿Puedes cambiarla a las 16:00 del mismo día?
```

y después:

```
Mejor cancélala
```

Qué debe pasar: `reagendar` mueve la cita a otro cupo del mismo médico (aparece una cita nueva y la
anterior queda cancelada) y `cancelar` deja todo en estado cancelada. El CRM lo refleja en el
siguiente ciclo de 5 segundos.

> "El agente solo puede tocar las citas del teléfono que está conversando: la identidad se fija en el
> servidor, no la decide el modelo."

### 6. La secretaria trabaja en el CRM (1 minuto)
Sin tocar el chat. En el CRM:

1. Elegir **otro médico** en el selector y un cupo en **Libre** → botón **Agendar**.
2. Escribir nombre y teléfono → **Confirmar**. La fila pasa a "Confirmada" con canal `recepcion`.
3. Marcar una cita como **Atendida** (estado `completada`).
4. **Mover** una cita a otro cupo del mismo día (reagendamiento desde recepción).

> "El mismo dominio, dos canales: el paciente por WhatsApp, la secretaria por la agenda. Los dos
> escriben en la misma tabla `citas`, con las mismas garantías de cupo único."

### 7. Cierre (30 segundos)
Mostrar `/docs` (Swagger) y decir:

> "Todo esto está sobre la arquitectura de la EP2: API en contenedor, cola para los webhooks del
> WhatsApp real, gateway de LLM con enmascarado de datos y las citas con bloqueo por cupo en
> PostgreSQL Multi-AZ. El CRM es la vista de recepción sobre el mismo modelo de datos."

## Si el profe pregunta por el código

| Pregunta | Dónde mirar |
|---|---|
| ¿Dónde está el grafo del agente? | `agente.py` (`StateGraph`, `ToolNode`, `tools_condition`) |
| ¿Dónde están las herramientas? | `herramientas.py` (`HERRAMIENTAS`, siete `@tool`) |
| ¿Cómo evitan dos citas en el mismo cupo? | `backend/reservas.py` (`FOR UPDATE` + índice único parcial) |
| ¿Dónde está la idempotencia? | `reservas.py` (huella SHA-256) y `herramientas.py` (UUID v5) |
| ¿Cómo se guarda la conversación? | tabla `conversaciones` en `database/init.sql` |
| ¿Cuántos tests hay? | 11 unitarios: `python -m unittest test_agenda.py test_reservas.py` |

## Plan B

**Si el agente responde lento o falla el proveedor de LLM:**
1. No improvisar delante del profe. Decir: "el proveedor de inferencia está con latencia, les
   muestro el mismo flujo por API" y ejecutar en la ventana de la API:
   ```
   .venv\Scripts\python.exe _interno\probar_chat.py "Hola, necesito hora con cardiología" "La primera me sirve, soy Demis Zúñiga, demis@example.com" "Sí, confirma"
   ```
   El resultado se ve en la consola y la cita aparece igual en el CRM.

**Si el CRM no actualiza:** presionar F5. El panel consulta cada 5 segundos; un F5 fuerza la carga.

**Si la base no responde:** `docker compose up -d` en otra ventana y esperar 15 segundos. Los datos
están en el volumen, no se pierden.

**Si nada funciona:** quedan el documento con los seis diagramas y esta demo ya verificada. El
discurso de arquitectura se sostiene solo.

## Mensajes exactos de la demo (copiar y pegar si se necesita)

```
Hola, necesito una hora con dermatología
Me sirve la de las 15:00. Soy Demis Zúñiga, demis@example.com
Sí, confirma
Sí, confirma
¿Puedes cambiarla a las 16:00 del mismo día?
Mejor cancélala
```

Consejo: dejar estos seis mensajes en el portapapeles o en el Bloc de notas, no escribirlos a mano
frente al profe. Los errores de tipeo confunden al agente y gastan tiempo de la demo.

## Limpiar después de la demo

```
docker exec mediflow-postgres psql -U mediflow -d mediflow_db -c "DELETE FROM citas WHERE paciente_id IN (SELECT id FROM pacientes WHERE telefono='+56911110009'); DELETE FROM pacientes WHERE telefono='+56911110009'; DELETE FROM conversaciones;"
```
