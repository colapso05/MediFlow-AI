# EP3 de MediFlow AI · guía para presentar

**Si tienen 30 minutos, descarguen la presentación, abran el guion y hagan un ensayo completo.** En la defensa usen un solo computador y dejen listas las pestañas de presentación, EC2 y CRM.

| Material | Para qué sirve |
| --- | --- |
| [Presentación PDF](MediFlow_AI_EP3_Defensa_AWS.pdf) · [PowerPoint editable](MediFlow_AI_EP3_Defensa_AWS.pptx) | Las 6 diapositivas. Descarguen el PDF para proyectar sin depender de PowerPoint. |
| [Guion para Demis, Bruno y Matías](GUION_DEFENSA.md) | Qué dice cada uno, en qué lámina y qué responder al docente. |
| [Informe técnico PDF](MediFlow_AI_EP3_Informe_AWS.pdf) | Arquitectura, validación, limitaciones y operación. Guarden una copia local. |
| [Resultados HTTP registrados en EC2](RESULTADOS_EC2.json) | Evidencia de dos predicciones, 11 comprobaciones y 50 solicitudes. Respaldo para explicar los resultados si falla la demo en vivo. |
| [Vista de respaldo para el proyector](RESPALDO_PROYECTOR.html) | Descarguen el HTML desde GitHub y ábranlo en el navegador. Muestra los dos resultados guardados sin conexión. |

## Ensayo de 30 minutos

| Minuto | Qué hacer |
| --- | --- |
| 0–5 | Descarguen los dos PDF y abran el guion. Mientras los demás leen, una persona inicia el lab y la instancia. |
| 5–12 | Cada persona ensaya su parte una vez en voz alta. Acuerden quién maneja el computador. |
| 12–22 | Abran el CRM y hagan una predicción. Ejecuten el comando de demo y expliquen sus resultados. Si no abre el CRM, practiquen el respaldo de la lámina 6. |
| 22–30 | Repasen las preguntas del guion. Dejen abiertas las pestañas y los PDF antes de proyectar. |

## Qué cambió desde la evaluación 2

| Evaluación 2 | Evaluación 3 |
| --- | --- |
| Diseñamos la arquitectura con C4, patrones, dimensionamiento y estimación de costos con AWS Pricing Calculator. | Desplegamos el sistema en AWS EC2 con Docker Compose e incorporamos un modelo de inasistencia que responde por REST, muestra resultados en el CRM y publica eventos en RabbitMQ. |
| Definimos cómo operar y escalar el sistema. | Verificamos la integración con pruebas HTTP y una carga acotada. La configuración demostrada usa una instancia. |

**Qué mostrar en vivo.** La pauta EP3, página 4, pide el sistema funcionando en AWS, una predicción en tiempo real, el dashboard, el consumo REST y el flujo completo. Muestren **EC2 en ejecución → cita en el CRM → Estimar riesgo → probabilidad y recomendación → llamada a la API**. Usen la consola para mostrar que la instancia está en ejecución y acceder a la terminal. La carga y los eventos son evidencia adicional, no necesitan recorrer toda la consola.

## Abrir el CRM en la sala

### Antes de que los llamen

1. Una persona abre **AWS Academy → Entorno de pruebas → Start Lab → AWS** desde el equipo que tenga a mano. En la consola selecciona **N. Virginia** (`us-east-1`) y abre **CloudShell** (el icono de terminal). Espera que aparezca el cursor.
2. Pega este comando una vez en CloudShell. Enciende EC2 si estaba detenida y muestra el enlace y la clave. Si el laboratorio se reinició y la instancia desapareció, el mismo comando vuelve a desplegar MediFlow. En ese caso, dale unos minutos antes de pasar al frente.

   ```bash
   curl -fsSL https://raw.githubusercontent.com/colapso05/MediFlow-AI/evaluacion-3/deployment/ec2/preparar-proyector.sh -o ~/preparar-mediflow.sh && bash ~/preparar-mediflow.sh
   ```

3. En el **computador de la sala**, abran el enlace `https://…trycloudflare.com/crm`. Inicien sesión con usuario **`mediflow`** y la clave que mostró CloudShell. Dejen el CRM abierto junto a la presentación, con la sesión iniciada y una cita seleccionada. Basta el navegador de la sala, sin PEM, sin instalar programas y sin cambiar reglas de red.

El enlace HTTPS dura hasta dos horas y cambia cada vez que se abre un túnel nuevo. Pasa por Cloudflare y apunta al CRM con datos sintéticos que corre en EC2. [Documentación de Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

### Durante la demo

1. En **Agenda**, abran una **cita futura confirmada** y pulsen **Estimar riesgo**. Lean la probabilidad y la recomendación. Si no hay citas confirmadas en el día mostrado, cambien la fecha.
2. Para mostrar el consumo REST, tengan listo este bloque en **CloudShell**. Pedirá pegar el enlace completo del CRM y la clave. La clave no se muestra mientras se escribe. La respuesta corresponde al caso fijo de alto riesgo.

   ```bash
   {
     read -rp 'Enlace del CRM: ' crm
     read -rsp 'Clave del CRM: ' clave; printf '\n'
     curl -fsS -u "mediflow:$clave" -H 'Content-Type: application/json' \
       -d '{"dias_anticipacion":60,"dia_semana":6,"hora":8}' \
       "${crm%/crm}/api/predicciones/inasistencia"; printf '\n'
     unset crm clave
   }
   ```

3. En la lámina 5, muestren las 11 comprobaciones HTTPS y el resultado de carga registrado. El [JSON de la ejecución](RESULTADOS_EC2.json) contiene también la respuesta del caso fijo de riesgo bajo.

### Si algo falla

| Situación | Qué hacer |
| --- | --- |
| El enlace dejó de funcionar | Vuelvan a ejecutar `bash ~/preparar-mediflow.sh` en CloudShell para recuperar o renovar el enlace. |
| La red de la sala bloquea el enlace | Intenten desde otro equipo conectado al proyector. Si CloudShell sí lo alcanza, ejecuten ahí la llamada REST. Expliquen el uso del CRM con la lámina 6. |
| AWS Academy no abre | Abran el [respaldo visual descargado](RESPALDO_PROYECTOR.html) y la presentación PDF. Digan que corresponden a una corrida anterior. |

### Al terminar

En CloudShell, ejecuten `bash ~/preparar-mediflow.sh cerrar`. Esto corta el enlace y solicita detener EC2. Cierren el navegador de la sala. El disco EBS conserva el despliegue mientras el laboratorio mantenga los recursos. [Detener e iniciar una instancia EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html).

Para la entrega en AVA, renombren los PDF según su número de equipo y apellidos. La pauta indica `EP3_Presentacion_Equipo[N].pdf` para la presentación y `EP3_Equipo[N]_Apellidos.pdf` para el informe.
