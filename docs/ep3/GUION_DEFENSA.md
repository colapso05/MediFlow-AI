# Guion de defensa · MediFlow AI

**Idea que deben saber los tres.** En la EP2 diseñamos la arquitectura de agendamiento. En la EP3 la llevamos a AWS EC2 y agregamos una predicción de inasistencia que recepción puede consultar desde el CRM.

**Tiempo.** Demis 3 min · Bruno 4 min · Matías 6 min · 2 min de margen. Usen el [paso a paso de la demo](README.md#abrir-el-crm-en-la-sala) y dejen el CRM abierto antes del turno.

## Demis · láminas 1 y 2 · problema y cambio

**Lámina 1.** “MediFlow AI apoya el agendamiento de una clínica. Cuando una persona falta a una cita, ese horario se pierde y recepción tiene menos tiempo para reaccionar. Agregamos una estimación para ayudar al equipo a decidir a quién conviene recordar primero.”

**Lámina 2.** “En la evaluación anterior diseñamos la arquitectura, justificamos los patrones y estimamos el costo de infraestructura con AWS. Esta vez desplegamos el sistema en una instancia EC2 del laboratorio. Integramos el modelo, la API y el tablero, y registramos pruebas del flujo completo. Bruno va a explicar cómo se conectan.”

**Para recordar.** Agenda → riesgo → priorizar recordatorio.

## Bruno · láminas 3 y 4 · arquitectura y modelo

**Lámina 3.** “El CRM pide una predicción a FastAPI. La API consulta un contenedor de inferencia y devuelve el resultado al CRM. PostgreSQL guarda la agenda y RabbitMQ transporta el evento de predicción a un consumidor. Docker Compose reúne estos servicios en EC2. Con la alternativa acordada para el lab, podemos separar y probar los componentes con una instancia y operar directamente el despliegue.”

**Lámina 4.** “El modelo es una regresión logística entrenada con cuatro mil ejemplos sintéticos. Recibe los días de anticipación, el día de la semana y la hora. A partir de un 25 por ciento sugiere priorizar el recordatorio. Obtuvimos un ROC AUC de 0,712 con los datos sintéticos. Para usarlo en una clínica tendríamos que validarlo con un historial real y revisar el umbral.”

**Para recordar.** Tres entradas → probabilidad → 25 % para priorizar. “Matías va a mostrar ese flujo funcionando.”

## Matías · láminas 5 y 6 · demostración y resultados

**Lámina 6, 3–4 min.** Pasa brevemente por la lámina 5 y ábrela al volver de la demo.

1. Muestra **mediflow-ep3 · En ejecución** y vuelve al CRM. “Esta instancia ejecuta los servicios que acabamos de ver.”
2. En **Agenda**, abre una cita confirmada futura y pulsa **Estimar riesgo**. “Recepción selecciona una cita. El sistema usa su anticipación, día y hora, y devuelve la probabilidad con una acción sugerida.” Lee la acción que salió.
3. Cambia a la terminal de AWS. Ejecuta la llamada `curl` de la guía. “Aquí consumimos por REST el mismo endpoint que usa el flujo del tablero. Este caso tiene 60 días de anticipación y un horario temprano de fin de semana. La respuesta trae la probabilidad, los factores y la sugerencia.”
4. Señala los casos fijos **79,24 %** en la respuesta REST y **6,64 %** en los resultados guardados. “Con la cita de riesgo alto sugerimos priorizar. Con la de riesgo bajo mantenemos el recordatorio habitual.”

**Vuelve a la lámina 5, 2 min.** “Pasaron 11 comprobaciones funcionales. La prueba de carga envió 50 peticiones en grupos de cinco y todas devolvieron HTTP 200. En la corrida guardada, el percentil 95 fue 1,28 segundos. También comprobamos que el consumidor recibe los eventos de RabbitMQ. Esta es una prueba acotada dentro de la instancia. Para un piloto ampliaríamos la carga, vigilaríamos errores y latencia, y validaríamos el modelo con datos representativos.”

**Si el tablero no abre.** Usa la terminal para demostrar la API y el modelo en vivo. Explica el flujo del CRM con la lámina 6 y menciona que quedó pendiente abrir el tablero en ese computador. Si falla AWS, usa los resultados registrados de la lámina 5 y preséntalos como evidencia de una corrida anterior.

## Preguntas que pueden hacerle a cualquiera

| Pregunta | Respuesta corta |
| --- | --- |
| ¿Qué se agregó respecto a la EP2? | Despliegue en EC2, un modelo de inasistencia servido por API, resultado en el CRM y pruebas del flujo. |
| ¿Por qué EC2 con Docker? | Fue la alternativa acordada para el laboratorio. Permitió desplegar y controlar los servicios en una instancia con separación por contenedores. Deja al equipo a cargo de parches, operación y escalado. |
| ¿Para qué RabbitMQ? | Separa el envío del evento de su procesamiento. El consumidor puede recibirlo y confirmarlo sin que el CRM tenga que procesarlo. |
| ¿Qué significa 79,24 %? | Es la probabilidad que asigna el modelo a un ejemplo sintético. Supera el umbral de 25 %, así que se sugiere priorizar el recordatorio. |
| ¿Qué significa p95 de 1,28 s? | Aproximadamente el 95 % de las respuestas de esa corrida demoró 1,28 segundos o menos. Se midió dentro de EC2, con cinco solicitudes simultáneas como máximo. |
| ¿Qué cubren las 11 pruebas? | Salud de la API y base, acceso al CRM, autenticación, predicciones alta y baja y rechazo de datos inválidos, entre otras comprobaciones. |
| ¿Qué falta para producción? | Validar con datos reales representativos, calibrar el umbral, ampliar las pruebas de carga y preparar monitoreo, recuperación y escalado. |
