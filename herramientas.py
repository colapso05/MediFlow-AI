
import os

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from langchain_core.tools import tool

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


HERRAMIENTAS = [
    buscar_especialidades,
    buscar_medicos
]
