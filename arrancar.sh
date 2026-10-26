#!/usr/bin/env bash
# Arranca MediFlow AI en macOS / Linux.
set -e
cd "$(dirname "$0")"

echo "==> MediFlow AI: arranque"

if [ ! -f .env ]; then
  echo "ERROR: falta el archivo .env"
  echo "Copia .env.example a .env y completa DEEPSEEK_API_KEY y POSTGRES_PASSWORD."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker no responde. Abre Docker Desktop y vuelve a intentar."
  exit 1
fi

echo "==> Levantando PostgreSQL"
docker compose up -d

echo "==> Esperando la base"
for _ in $(seq 1 40); do
  if docker exec mediflow-postgres pg_isready -U mediflow -d mediflow_db >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if [ ! -d .venv ]; then
  echo "==> Creando entorno de Python"
  python3.12 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "==> Compilando el simulador de WhatsApp"
    (cd frontend && npm install --no-audit --no-fund && npm run build)
  else
    echo "==> Sin Node: se usará el simulador simple en /demo"
  fi
fi

echo "==> Arrancando la API en http://127.0.0.1:8000"
echo "    WhatsApp: http://127.0.0.1:8000/app"
echo "    CRM     : http://127.0.0.1:8000/crm"
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
