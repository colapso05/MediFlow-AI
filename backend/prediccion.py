import json
from functools import lru_cache
from math import exp
from pathlib import Path

from pydantic import BaseModel, Field


MODELO = Path(__file__).with_name("modelo_inasistencia.json")
VARIABLES = ("anticipacion", "fin_de_semana", "primera_hora")
FACTORES = ("Anticipación de la reserva", "Cita en fin de semana", "Cita antes de las 10:00")


class DatosPrediccion(BaseModel):
    dias_anticipacion: float = Field(ge=0, allow_inf_nan=False)
    dia_semana: int = Field(ge=0, le=6, description="Lunes = 0, domingo = 6")
    hora: int = Field(ge=0, le=23, description="Hora de la cita en Chile")


class ResultadoPrediccion(BaseModel):
    probabilidad: float = Field(ge=0, le=1)
    priorizar_recordatorio: bool
    factores: list[str]
    version_modelo: str
    datos_entrenamiento: str


def variables_modelo(dias_anticipacion: float, dia_semana: int, hora: int) -> tuple[float, ...]:
    return min(dias_anticipacion, 60) / 30, float(dia_semana >= 5), float(hora < 10)


@lru_cache(maxsize=1)
def cargar_modelo() -> dict:
    return json.loads(MODELO.read_text(encoding="utf-8"))


def predecir_inasistencia(dias_anticipacion: float, dia_semana: int, hora: int) -> dict:
    modelo = cargar_modelo()
    valores = variables_modelo(dias_anticipacion, dia_semana, hora)
    aportes = [peso * valor for peso, valor in zip(modelo["coeficientes"], valores, strict=True)]
    log_odds = modelo["intercepto"] + sum(aportes)
    probabilidad = 1 / (1 + exp(-log_odds))
    return {
        "probabilidad": round(probabilidad, 4),
        "priorizar_recordatorio": probabilidad >= modelo["umbral"],
        "factores": [
            factor for aporte, factor in sorted(zip(aportes, FACTORES, strict=True), reverse=True)
            if aporte > 0
        ],
        "version_modelo": modelo["version"],
        "datos_entrenamiento": modelo["datos_entrenamiento"],
    }
