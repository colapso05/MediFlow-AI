import os

import pika
import uvicorn
from fastapi import FastAPI, HTTPException, Response

from backend.prediccion import (
    DatosPrediccion,
    ResultadoPrediccion,
    cargar_modelo,
    predecir_inasistencia,
)
from deployment.sagemaker.eventos import publicar


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/ping", response_class=Response)
@app.post("/ping", response_class=Response)
def ping():
    cargar_modelo()
    return Response()


@app.post("/invocations", response_model=ResultadoPrediccion)
def predecir(datos: DatosPrediccion):
    resultado = predecir_inasistencia(datos.dias_anticipacion, datos.dia_semana, datos.hora)
    url = os.getenv("AMQP_URL")
    if url:
        try:
            publicar(url, resultado)
        except (OSError, pika.exceptions.AMQPError) as error:
            raise HTTPException(status_code=503, detail="Cola de predicciones no disponible") from error
    return resultado


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
