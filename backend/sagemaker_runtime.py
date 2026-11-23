import os
from contextlib import closing
from functools import lru_cache

import boto3
from botocore.config import Config

from backend.prediccion import DatosPrediccion, ResultadoPrediccion


@lru_cache(maxsize=1)
def cliente_runtime():
    return boto3.client(
        "sagemaker-runtime",
        region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        config=Config(connect_timeout=3, read_timeout=65, retries={"total_max_attempts": 1}),
    )


def invocar_endpoint(endpoint: str, datos: DatosPrediccion) -> ResultadoPrediccion:
    respuesta = cliente_runtime().invoke_endpoint(
        EndpointName=endpoint,
        ContentType="application/json",
        Accept="application/json",
        Body=datos.model_dump_json().encode("utf-8"),
    )
    with closing(respuesta["Body"]) as cuerpo:
        return ResultadoPrediccion.model_validate_json(cuerpo.read())
