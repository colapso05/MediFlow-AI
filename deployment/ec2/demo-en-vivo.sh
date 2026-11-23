#!/usr/bin/env bash
set -euo pipefail
cd /opt/mediflow/deployment/ec2

printf 'MediFlow AI en AWS EC2. Ejecutando pruebas HTTPS y una carga de 50 solicitudes.\n'
python3 verificar.py | python3 -c '
import json
import sys

r = json.load(sys.stdin)
carga = r["carga"]
casos = len(r["pruebas"])
print(f"Comprobaciones funcionales aprobadas: {casos}")
for nombre, resultado in r["predicciones"].items():
    riesgo = resultado["probabilidad"] * 100
    accion = "priorizar" if resultado["priorizar_recordatorio"] else "recordatorio habitual"
    print(f"{nombre.capitalize()}: {riesgo:.2f}% | {accion}")
respuestas = carga["estados_http"].get("200", 0)
latencia = carga["latencia_ms"].get("p95", 0)
solicitudes = carga["solicitudes"]
print(f"Carga: {respuestas}/{solicitudes} HTTP 200 | p95 {latencia:.2f} ms")
'

printf '\nÚltimos eventos recibidos por RabbitMQ\n'
docker compose logs --no-color --tail 2 consumidor
