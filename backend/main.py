
import os
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from backend.agenda import consultar_horarios
from agente import agente
load_dotenv()

app = FastAPI(
    title="MediFlow AI API",
    description="API administrativa para la clínica MediFlow",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class MensajeChat(BaseModel):
    mensaje: str
    historial: list[dict[str, str]] = []


@app.post("/api/chat")
def conversar(datos: MensajeChat):
    if not datos.mensaje.strip():
        raise HTTPException(
            status_code=400,
            detail="El mensaje no puede estar vacío"
        )

    mensajes = []

    # Historial enviado por el frontend.
    # Es temporal: después lo guardaremos en PostgreSQL.
    for item in datos.historial[-20:]:
        rol = item.get("role")
        contenido = item.get("content", "")

        if rol == "user":
            mensajes.append(HumanMessage(content=contenido))
        elif rol == "assistant":
            mensajes.append(AIMessage(content=contenido))

    mensajes.append(HumanMessage(content=datos.mensaje))

    try:
        resultado = agente.invoke({"messages": mensajes})
        respuesta = resultado["messages"][-1].content

        return {"respuesta": respuesta}

    except Exception as error:
        print(
            "[ERROR MEDIFLOW AI]",
            type(error).__name__,
            flush=True,
        )
        raise HTTPException(
            status_code=502,
            detail="No fue posible obtener respuesta del agente",
        ) from error

@contextmanager
def obtener_conexion():
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row
    ) as conexion:
        yield conexion


@app.get("/")
def inicio():
    return {
        "mensaje": "Bienvenido a MediFlow AI",
        "estado": "funcionando"
    }


@app.get("/api/health")
def health():
    try:
        with obtener_conexion() as conexion:
            conexion.execute("SELECT 1")

        return {
            "api": "online",
            "database": "connected"
        }

    except psycopg.Error:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible"
        )


@app.get("/api/especialidades")
def listar_especialidades():
    with obtener_conexion() as conexion:
        return conexion.execute(
            """
            SELECT id, nombre
            FROM especialidades
            ORDER BY nombre
            """
        ).fetchall()


@app.get("/api/medicos")
def listar_medicos(
    especialidad_id: int | None = Query(
        default=None,
        gt=0
    )
):
    with obtener_conexion() as conexion:
        return conexion.execute(
            """
            SELECT
                m.id,
                m.nombre,
                e.id AS especialidad_id,
                e.nombre AS especialidad
            FROM medicos m
            JOIN especialidades e
                ON e.id = m.especialidad_id
            WHERE m.activo = TRUE
              AND (
                  %(especialidad_id)s IS NULL
                  OR m.especialidad_id = %(especialidad_id)s
              )
            ORDER BY m.nombre
            """,
            {"especialidad_id": especialidad_id}
        ).fetchall()


@app.get("/api/horarios")
def listar_horarios(
    medico_id: int | None = Query(default=None, gt=0),
    especialidad_id: int | None = Query(default=None, gt=0),
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = Query(default=50, ge=1, le=200),
):
    if desde and hasta and hasta < desde:
        raise HTTPException(
            status_code=400,
            detail="La fecha final no puede ser anterior a la inicial",
        )

    with obtener_conexion() as conexion:
        return consultar_horarios(
            conexion,
            medico_id=medico_id,
            especialidad_id=especialidad_id,
            desde=desde,
            hasta=hasta,
            limite=limite,
        )
