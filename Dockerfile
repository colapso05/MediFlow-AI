# Imagen de referencia del servicio de API y del agente de MediFlow AI.
# Multi-stage: las dependencias se instalan en una etapa aparte para que la
# imagen final no lleve compiladores ni caché de pip.
FROM python:3.12-slim AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /tmp/build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Usuario sin privilegios: si un atacante entra al contenedor, no es root.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=deps /install /usr/local
COPY agente.py herramientas.py ./
COPY backend ./backend
COPY database ./database
COPY frontend/dist ./frontend/dist

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# El mismo endpoint que consulta el ALB: si falla, Kubernetes reinicia el pod.
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
