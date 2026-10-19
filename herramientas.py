
import os
from datetime import date
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from langchain_core.tools import tool
from backend.agenda import consultar_horarios

load_dotenv()


@tool
def buscar_especialidades() -> list[dict]:
    """Consulta las especialidades médicas disponibles en MediFlow."""

    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        connect_timeout=5,
    ) as conexion:

        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id, nombre
                FROM especialidades
                ORDER BY nombre
            """)

            return cursor.fetchall()


@tool
def buscar_medicos(
    especialidad_id: int | None = None
) -> list[dict]:
    """Consulta los médicos activos de MediFlow.
    Si se proporciona especialidad_id, filtra por especialidad.
    Usa buscar_especialidades para conocer los identificadores.
    """

    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        connect_timeout=5,
    ) as conexion:

        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                    m.id,
                    m.nombre,
                    e.nombre AS especialidad
                FROM medicos m
                JOIN especialidades e
                    ON e.id = m.especialidad_id
                WHERE (
                    %(especialidad_id)s IS NULL
                    OR m.especialidad_id = %(especialidad_id)s
                )
                ORDER BY m.nombre
            """, {
                "especialidad_id": especialidad_id
            })

            return cursor.fetchall()


@tool
def buscar_horarios(
    medico_id: int,
    desde: date | None = None,
    hasta: date | None = None,
) -> list[dict]:
    """Consulta los próximos horarios libres de un médico.
    Usa buscar_medicos para obtener su identificador. Las fechas son días
    locales de Chile e incluyen ambos extremos.
    """

    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        connect_timeout=5,
    ) as conexion:
        horarios = consultar_horarios(
            conexion,
            medico_id=medico_id,
            desde=desde,
            hasta=hasta,
            limite=10,
        )

    zona_chile = ZoneInfo("America/Santiago")
    return [
        {
            "id": horario["id"],
            "medico_id": horario["medico_id"],
            "medico": horario["medico"],
            "especialidad": horario["especialidad"],
            "inicio": horario["inicio"].astimezone(zona_chile).strftime(
                "%d/%m/%Y %H:%M"
            ),
            "fin": horario["fin"].astimezone(zona_chile).strftime("%H:%M"),
        }
        for horario in horarios
    ]


HERRAMIENTAS = [
    buscar_especialidades,
    buscar_medicos,
    buscar_horarios,
]

