
import os
from contextvars import ContextVar
from datetime import date
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from langchain_core.tools import tool

from backend.agenda import consultar_horarios
from backend.reservas import (
    CitaNoEncontrada,
    HorarioNoDisponible,
    PacienteConCitaEnEseHorario,
    RutDeOtroPaciente,
    RutInvalido,
    cancelar_cita,
    reagendar_cita,
    reservar_cita,
)
from backend.rut import formatear_rut, validar_rut
from backend.servicios import citas_del_paciente, obtener_paciente_por_telefono

load_dotenv()

ZONA_CHILE = ZoneInfo("America/Santiago")

# Identidad del paciente durante la conversación. La fija la API antes de
# invocar al grafo; el modelo nunca la puede cambiar ni inventar.
TELEFONO_ACTUAL: ContextVar[str | None] = ContextVar(
    "telefono_actual",
    default=None,
)


def _conexion():
    return psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
        connect_timeout=5,
    )


def _formatear(horario: dict) -> dict:
    return {
        "horario_id": horario["id"],
        "medico": horario["medico"],
        "especialidad": horario["especialidad"],
        "inicio": horario["inicio"].astimezone(ZONA_CHILE).strftime("%d/%m/%Y %H:%M"),
        "fin": horario["fin"].astimezone(ZONA_CHILE).strftime("%H:%M"),
    }


def _formatear_cita(cita: dict) -> dict:
    return {
        "cita_id": cita["id"],
        "estado": cita["estado"],
        "especialidad": cita["especialidad"],
        "medico": cita["medico"],
        "inicio": cita["inicio"].astimezone(ZONA_CHILE).strftime("%d/%m/%Y %H:%M"),
        "fin": cita["fin"].astimezone(ZONA_CHILE).strftime("%H:%M"),
    }


@tool
def buscar_especialidades() -> list[dict]:
    """Consulta las especialidades médicas disponibles en MediFlow."""

    with _conexion() as conexion:
        return conexion.execute(
            """
            SELECT id, nombre
            FROM especialidades
            ORDER BY nombre
            """
        ).fetchall()


@tool
def buscar_medicos(especialidad_id: int | None = None) -> list[dict]:
    """Consulta los médicos activos de MediFlow.
    Si se proporciona especialidad_id, filtra por especialidad.
    Usa buscar_especialidades para conocer los identificadores.
    """

    with _conexion() as conexion:
        return conexion.execute(
            """
            SELECT
                m.id,
                m.nombre,
                m.especialidad_id,
                e.nombre AS especialidad
            FROM medicos m
            JOIN especialidades e ON e.id = m.especialidad_id
            WHERE (
                %(especialidad_id)s::integer IS NULL
                OR m.especialidad_id = %(especialidad_id)s
            )
            AND m.activo = TRUE
            ORDER BY m.nombre
            """,
            {"especialidad_id": especialidad_id},
        ).fetchall()


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

    with _conexion() as conexion:
        horarios = consultar_horarios(
            conexion,
            medico_id=medico_id,
            desde=desde,
            hasta=hasta,
            limite=10,
        )

    return [_formatear(horario) for horario in horarios]


@tool
def reservar(
    horario_id: int,
    nombre: str,
    rut: str,
    email: str | None = None,
) -> dict:
    """Registra y confirma la cita del paciente en el horario indicado.

    Requiere el horario_id que devolvió buscar_horarios, el nombre completo del
    paciente y su RUT (el RUT es obligatorio para agendar en Chile). Acepta el
    RUT con o sin puntos y con o sin guion: 12.345.678-5, 12345678-5 o
    123456785. El teléfono se toma de la conversación de WhatsApp. Si el RUT no
    es válido, la herramienta lo indica y no agenda: pide el dato de nuevo.
    """

    telefono = TELEFONO_ACTUAL.get()

    if not telefono:
        return {
            "ok": False,
            "error": "No hay un número de contacto asociado a esta conversación.",
        }

    rut_limpio, error_rut = validar_rut(rut)
    if error_rut:
        return {
            "ok": False,
            "campo": "rut",
            "error": f"El RUT no se pudo usar. {error_rut} Pídelo otra vez al paciente.",
        }

    # Clave determinista: si el modelo repite la misma reserva, la base
    # devuelve la misma cita en lugar de duplicarla.
    clave = uuid5(
        NAMESPACE_URL,
        f"mediflow|{telefono}|{horario_id}|{nombre.strip().lower()}|{rut_limpio}",
    )

    try:
        with _conexion() as conexion:
            # En WhatsApp la identidad es el teléfono: si el paciente ya existe,
            # la reserva se cuelga de ese registro y no se duplica la ficha.
            paciente_previo = obtener_paciente_por_telefono(conexion, telefono)
            email_efectivo = None if paciente_previo else email

            if paciente_previo and paciente_previo["nombre"].strip().lower() != nombre.strip().lower():
                # El paciente se identifica por teléfono; si escribe su nombre, se actualiza la ficha.
                conexion.execute(
                    "UPDATE pacientes SET nombre = %s WHERE id = %s",
                    (nombre.strip(), paciente_previo["id"]),
                )

            cita = reservar_cita(
                conexion,
                horario_id=horario_id,
                nombre=nombre,
                email=email_efectivo,
                telefono=telefono,
                rut=rut_limpio,
                idempotency_key=clave,
            )
            detalle = conexion.execute(
                """
                SELECT
                    c.id, c.estado, m.nombre AS medico,
                    e.nombre AS especialidad, h.inicio, h.fin
                FROM citas c
                JOIN horarios h ON h.id = c.horario_id
                JOIN medicos m ON m.id = c.medico_id
                JOIN especialidades e ON e.id = m.especialidad_id
                WHERE c.id = %s
                """,
                (cita["id"],),
            ).fetchone()

            conexion.execute(
                "UPDATE citas SET canal = 'whatsapp' WHERE id = %s",
                (cita["id"],),
            )
            conexion.commit()

    except HorarioNoDisponible:
        return {
            "ok": False,
            "error": "Ese horario ya no está disponible. Ofrece otro al paciente.",
        }
    except RutInvalido as error:
        return {
            "ok": False,
            "campo": "rut",
            "error": f"{error} Pídelo otra vez al paciente.",
        }
    except PacienteConCitaEnEseHorario as error:
        detalle = error.detalle
        return {
            "ok": False,
            "campo": "horario",
            "error": (
                "El paciente ya tiene una cita a esa misma hora: "
                f"{detalle.get('medico')} ({detalle.get('especialidad')}). "
                "Un paciente puede tener varias citas el mismo día, pero no dos "
                "a la misma hora. Dile que esa otra cita existe y ofrécele "
                "moverla o cancelarla, o proponle otro horario."
            ),
        }
    except RutDeOtroPaciente as error:
        return {
            "ok": False,
            "campo": "rut",
            "error": f"{error} Derivar a recepción humana.",
        }
    except Exception as error:  # noqa: BLE001 - se informa al agente, no se propaga
        print("[TOOL reservar]", type(error).__name__, flush=True)
        return {
            "ok": False,
            "error": "No fue posible registrar la cita en este momento.",
        }

    return {
        "ok": True,
        "cita": _formatear_cita(detalle),
        "paciente": nombre.strip(),
        "rut": formatear_rut(rut_limpio),
    }


@tool
def mis_citas() -> dict:
    """Lista las citas activas del paciente que está conversando.
    Úsala antes de cancelar o reagendar para conocer el cita_id.
    """

    telefono = TELEFONO_ACTUAL.get()

    with _conexion() as conexion:
        paciente = obtener_paciente_por_telefono(conexion, telefono)

        if not paciente:
            return {"ok": True, "paciente": None, "citas": []}

        citas = citas_del_paciente(
            conexion,
            paciente_id=paciente["id"],
            solo_activas=True,
        )

    return {
        "ok": True,
        "paciente": paciente["nombre"],
        "rut": formatear_rut(paciente.get("rut")),
        "citas": [_formatear_cita(cita) for cita in citas],
    }


@tool
def cancelar(cita_id: int) -> dict:
    """Cancela una cita activa del paciente que está conversando."""

    telefono = TELEFONO_ACTUAL.get()

    try:
        with _conexion() as conexion:
            paciente = obtener_paciente_por_telefono(conexion, telefono)

            if not paciente:
                return {"ok": False, "error": "No encuentro reservas con este número."}

            cita = cancelar_cita(
                conexion,
                cita_id=cita_id,
                paciente_id=paciente["id"],
            )
            conexion.commit()

    except CitaNoEncontrada:
        return {
            "ok": False,
            "error": "Esa cita no existe, ya fue cancelada o no pertenece al paciente.",
        }
    except Exception as error:  # noqa: BLE001
        print("[TOOL cancelar]", type(error).__name__, flush=True)
        return {"ok": False, "error": "No fue posible cancelar la cita."}

    return {"ok": True, "cita_id": cita["id"], "estado": "cancelada"}


@tool
def reagendar(cita_id: int, nuevo_horario_id: int) -> dict:
    """Mueve una cita activa del paciente a otro horario del mismo médico.

    Usa mis_citas para el cita_id y buscar_horarios para el nuevo_horario_id.
    """

    telefono = TELEFONO_ACTUAL.get()

    try:
        with _conexion() as conexion:
            paciente = obtener_paciente_por_telefono(conexion, telefono)

            if not paciente:
                return {"ok": False, "error": "No encuentro reservas con este número."}

            nueva = reagendar_cita(
                conexion,
                cita_id=cita_id,
                paciente_id=paciente["id"],
                nuevo_horario_id=nuevo_horario_id,
            )
            detalle = conexion.execute(
                """
                SELECT
                    c.id, c.estado, m.nombre AS medico,
                    e.nombre AS especialidad, h.inicio, h.fin
                FROM citas c
                JOIN horarios h ON h.id = c.horario_id
                JOIN medicos m ON m.id = c.medico_id
                JOIN especialidades e ON e.id = m.especialidad_id
                WHERE c.id = %s
                """,
                (nueva["id"],),
            ).fetchone()
            conexion.execute(
                "UPDATE citas SET canal = 'whatsapp' WHERE id = %s",
                (nueva["id"],),
            )
            conexion.commit()

    except (HorarioNoDisponible, CitaNoEncontrada):
        return {
            "ok": False,
            "error": "El cambio no se pudo hacer: la cita o el horario ya no están disponibles.",
        }
    except Exception as error:  # noqa: BLE001
        print("[TOOL reagendar]", type(error).__name__, flush=True)
        return {"ok": False, "error": "No fue posible reagendar la cita."}

    return {"ok": True, "cita": _formatear_cita(detalle)}


HERRAMIENTAS = [
    buscar_especialidades,
    buscar_medicos,
    buscar_horarios,
    reservar,
    mis_citas,
    cancelar,
    reagendar,
]
