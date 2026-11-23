# EP3 de MediFlow AI · guía para presentar

**Si tienen 30 minutos, descarguen la presentación, abran el guion y hagan un ensayo completo.** En la defensa usen un solo computador y dejen listas las pestañas de presentación, EC2 y CRM.

| Material | Para qué sirve |
| --- | --- |
| [Presentación PDF](MediFlow_AI_EP3_Defensa_AWS.pdf) · [PowerPoint editable](MediFlow_AI_EP3_Defensa_AWS.pptx) | Las 6 diapositivas. Descarguen el PDF para proyectar sin depender de PowerPoint. |
| [Guion para Demis, Bruno y Matías](GUION_DEFENSA.md) | Qué dice cada uno, en qué lámina y qué responder al docente. |
| [Informe técnico PDF](MediFlow_AI_EP3_Informe_AWS.pdf) | Arquitectura, validación, limitaciones y operación. Guarden una copia local. |
| [Resultados HTTP registrados en EC2](RESULTADOS_EC2.json) | Evidencia de dos predicciones, 11 comprobaciones y 50 solicitudes. Respaldo para explicar los resultados si falla la demo en vivo. |

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

## Abrir la demo desde el computador de la universidad

1. Entren a **AWS Academy → Learner Lab**. Si está inactivo, pulsen **Start Lab**. Cuando esté habilitado, pulsen **AWS**. En la consola seleccionen **N. Virginia (`us-east-1`)**.
2. Abran **EC2 → Instancias → mediflow-ep3**. Si está detenida, pulsen **Estado de la instancia → Iniciar instancia**. Esperen **En ejecución** y que pasen las comprobaciones de estado. El arranque puede tomar unos minutos.
3. Elijan **Conectar → EC2 Instance Connect → En el navegador web** y conecten con el usuario `ec2-user`. Esta ruta se probó en el lab y no necesita instalar Docker, Python ni Postman en el computador de la universidad. [Documentación de EC2 Instance Connect](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-methods.html).
4. En la terminal de AWS ejecuten:

   ```bash
   sudo mediflow-demo
   ```

   Tarda alrededor de diez segundos. Muestra 11 comprobaciones, dos predicciones, las respuestas HTTP de la prueba de carga y los últimos eventos del consumidor de RabbitMQ. El CRM también se comprueba como ruta autenticada. La latencia varía entre corridas.

5. Para mostrar una llamada REST por separado, preparen este bloque en la terminal de AWS. El comando lee la clave sin imprimirla y devuelve el JSON del caso de alto riesgo.

   ```bash
   sudo bash -c 'cd /opt/mediflow/deployment/ec2 && curl -fsS --cacert privado/tls.crt -u "mediflow:$(cat privado/clave-demo)" -H "Content-Type: application/json" -d "{\"dias_anticipacion\":60,\"dia_semana\":6,\"hora\":8}" https://localhost:8443/api/predicciones/inasistencia && printf "\n"'
   ```

### Abrir el CRM visual antes de proyectar

Háganlo en el ensayo. Requiere OpenSSH en el computador de la universidad y que la red permita el puerto 22. Mantengan lista la demo del navegador de AWS del paso anterior por si la red bloquea esta conexión.

1. En **AWS Academy → AWS Details**, descarguen la clave PEM del laboratorio. Guárdenla temporalmente en el perfil del usuario y revisen el nombre del archivo.
2. En **EC2 → mediflow-ep3 → Seguridad**, abran el grupo de seguridad de la instancia. Agreguen una regla **SSH (22) → Mi IP**, solo para la IP del computador que hará la demo. Conserven la regla existente de EC2 Instance Connect. Copien la **IPv4 pública actual** desde los detalles de EC2.
3. En **PowerShell del computador**, reemplacen `IP_ACTUAL` y, si corresponde, el nombre de la clave. El túnel queda abierto mientras siga activa esa ventana.

   ```powershell
   ssh -i "$env:USERPROFILE\Downloads\labsuser.pem" -o HostKeyAlgorithms=ssh-ed25519 -o ExitOnForwardFailure=yes -N -L 8080:127.0.0.1:8080 ec2-user@IP_ACTUAL
   ```

   Si SSH pregunta por la huella, compárenla con `sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` en la terminal de AWS. Si el puerto 8080 ya está ocupado, cambien solo el primer `8080` del comando a `8081` y usen ese mismo puerto en el navegador.
4. Abran `http://127.0.0.1:8080/crm` en el computador. Usuario `mediflow`. Antes de compartir pantalla, consulten la clave en la terminal de AWS con `sudo cat /opt/mediflow/deployment/ec2/privado/clave-demo`. El navegador se conecta al puerto local y SSH cifra la conexión hasta EC2.
5. En **Agenda**, abran una **cita futura confirmada** y pulsen **Estimar riesgo**. Lean la probabilidad y la acción sugerida. Si el día actual no tiene citas confirmadas, cambien a otra fecha de la agenda. El caso fijado en la prueba de terminal sirve para mostrar ambos resultados aunque el porcentaje de la cita del CRM sea distinto.

### Si algo falla

| Situación | Qué mostrar o hacer |
| --- | --- |
| EC2 abre, pero los servicios todavía no responden | En la terminal de AWS, ejecuten `cd /opt/mediflow/deployment/ec2 && sudo docker compose up -d --wait`. Vuelvan a ejecutar `sudo mediflow-demo`. |
| La red bloquea el túnel del CRM | Ejecuten en vivo `sudo mediflow-demo` y la llamada REST en la terminal de AWS. Usen la lámina 6 para explicar cómo recepción usa el resultado en el CRM. Indiquen que el tablero interactivo no pudo abrirse desde ese computador. |
| AWS Academy o la conexión web falla | Abran el PDF descargado, vayan a las láminas 5 y 6 y muestren los resultados de la ejecución registrada. Indiquen al docente que están usando evidencia de respaldo. |

### Al terminar

Cierren el túnel con `Ctrl+C`, eliminen la regla temporal SSH de **Mi IP** si la agregaron y borren la copia de la PEM del computador compartido. En EC2, pulsen **Estado de la instancia → Detener instancia** y esperen **Detenida**. La próxima vez, la IPv4 pública puede cambiar. El disco EBS conserva el despliegue y puede seguir usando presupuesto de almacenamiento. [Detener e iniciar una instancia EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html).

Para la entrega en AVA, renombren los PDF según su número de equipo y apellidos. La pauta indica `EP3_Presentacion_Equipo[N].pdf` para la presentación y `EP3_Equipo[N]_Apellidos.pdf` para el informe.
