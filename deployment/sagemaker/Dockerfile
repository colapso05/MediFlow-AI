FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN pip install fastapi==0.148.0 pydantic==2.14.1 uvicorn==0.54.0 pika==1.3.2
COPY backend/prediccion.py backend/modelo_inasistencia.json ./backend/
COPY deployment/sagemaker/inferencia.py deployment/sagemaker/eventos.py ./deployment/sagemaker/
EXPOSE 8080
ENTRYPOINT ["python", "-m", "deployment.sagemaker.inferencia"]
