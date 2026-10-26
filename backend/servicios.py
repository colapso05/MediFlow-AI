
"""Consultas de lectura para la API de negocio y el CRM.

Las escrituras (reservar, cancelar, reagendar) viven en backend/reservas.py
y son las únicas que toman bloqueos por cupo.
"""

from datetime import date

import psycopg
from psycopg.rows import dict_row


ESTADOS = ("confirmada", "cancelada", "completada")


def obtener_paciente_por_telefono(
    conexion: psycopg.Connection,
    telefono: str | None,
) -> dict | None:
    if not telefono:
        return None

    return conexion.execute(
        """
        SELECT id, nombre, email, telefono, verificado
        FROM pacientes
        WHERE telefono = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (telefono,),
    ).fetchone()


def citas_del_paciente(
    conexion: psycopg.Connection,
    *,
    paciente_id: int,
    solo_activas: bool = True,
) -> list[dict]:
    filtro = "AND c.estado = 'confirmada'" if solo_activas else ""

    return conexion.execute(
        f"""
        SELECT
            c.id,
            c.estado,
            c.canal,
            c.creada_en,
            m.nombre AS medico,
            e.nombre AS especialidad,
            h.id AS horario_id,
            h.inicio,
            h.fin
        FROM citas c
        JOIN horarios h ON h.id = c.horario_id
        JOIN medicos m ON m.id = c.medico_id
        JOIN especialidades e ON e.id = m.especialidad_id
        WHERE c.paciente_id = %s
          {filtro}
        ORDER BY h.inicio
        """,
        (paciente_id,),
    ).fetchall()


def listar_citas(
    conexion: psycopg.Connection,
    *,
    estado: str | None = None,
    medico_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    busqueda: str | None = None,
    limite: int = 200,
) -> list[dict]:
    """Listado para el CRM, con el paciente y el cupo ya resueltos."""
    if estado and estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")

    return conexion.execute(
        """
        SELECT
            c.id,
            c.estado,
            c.canal,
            c.creada_en,
            p.id AS paciente_id,
            p.nombre AS paciente,
            p.email,
            p.telefono,
            m.id AS medico_id,
            m.nombre AS medico,
            e.nombre AS especialidad,
            h.id AS horario_id,
            h.inicio,
            h.fin
        FROM citas c
        JOIN pacientes p ON p.id = c.paciente_id
        JOIN horarios h ON h.id = c.horario_id
        JOIN medicos m ON m.id = c.medico_id
        JOIN especialidades e ON e.id = m.especialidad_id
        WHERE (%(estado)s::text IS NULL OR c.estado = %(estado)s)
          AND (%(medico_id)s::integer IS NULL OR c.medico_id = %(medico_id)s)
          AND (
              %(desde)s::date IS NULL
              OR h.inicio >= (%(desde)s::date::timestamp AT TIME ZONE 'America/Santiago')
          )
          AND (
              %(hasta)s::date IS NULL
              OR h.inicio < ((%(hasta)s::date + 1)::timestamp AT TIME ZONE 'America/Santiago')
          )
          AND (
              %(busqueda)s::text IS NULL
              OR p.nombre ILIKE '%%' || %(busqueda)s || '%%'
              OR COALESCE(p.email, '') ILIKE '%%' || %(busqueda)s || '%%'
              OR COALESCE(p.telefono, '') ILIKE '%%' || %(busqueda)s || '%%'
          )
        ORDER BY h.inicio DESC
        LIMIT %(limite)s
        """,
        {
            "estado": estado,
            "medico_id": medico_id,
            "desde": desde,
            "hasta": hasta,
            "busqueda": busqueda,
            "limite": limite,
        },
    ).fetchall()


def resumen_crm(conexion: psycopg.Connection) -> dict:
    """Indicadores que se muestran arriba en el CRM."""
    return conexion.execute(
        """
        SELECT
            (SELECT count(*) FROM citas
              WHERE estado = 'confirmada') AS confirmadas,
            (SELECT count(*) FROM citas c
              JOIN horarios h ON h.id = c.horario_id
              WHERE c.estado = 'confirmada'
                AND (h.inicio AT TIME ZONE 'America/Santiago')::date
                    = (NOW() AT TIME ZONE 'America/Santiago')::date) AS hoy,
            (SELECT count(*) FROM citas c
              JOIN horarios h ON h.id = c.horario_id
              WHERE c.estado = 'confirmada'
                AND (h.inicio AT TIME ZONE 'America/Santiago')::date
                    BETWEEN (NOW() AT TIME ZONE 'America/Santiago')::date
                        AND ((NOW() AT TIME ZONE 'America/Santiago')::date + 7)) AS semana,
            (SELECT count(*) FROM citas
              WHERE estado = 'cancelada') AS canceladas,
            (SELECT count(*) FROM citas
              WHERE estado = 'completada') AS completadas,
            (SELECT count(*) FROM pacientes) AS pacientes,
            (SELECT count(*) FROM medicos WHERE activo) AS medicos,
            (SELECT count(*) FROM horarios h
              WHERE h.inicio > NOW()
                AND NOT EXISTS (
                    SELECT 1 FROM citas c
                    WHERE c.horario_id = h.id
                      AND c.estado IN ('confirmada', 'completada')
                )) AS cupos_libres,
            (SELECT count(*) FROM conversaciones) AS mensajes
        """
    ).fetchone()


def agenda_por_medico(conexion: psycopg.Connection) -> list[dict]:
    """Ocupación de los próximos 7 días por médico (para el CRM)."""
    return conexion.execute(
        """
        SELECT
            m.id,
            m.nombre AS medico,
            e.nombre AS especialidad,
            count(h.id) FILTER (
                WHERE h.inicio > NOW()
                  AND h.inicio < NOW() + INTERVAL '7 days'
            ) AS cupos_semana,
            count(c.id) FILTER (
                WHERE c.estado = 'confirmada'
                  AND h.inicio > NOW()
                  AND h.inicio < NOW() + INTERVAL '7 days'
            ) AS reservados_semana
        FROM medicos m
        JOIN especialidades e ON e.id = m.especialidad_id
        LEFT JOIN horarios h ON h.medico_id = m.id
        LEFT JOIN citas c ON c.horario_id = h.id
        WHERE m.activo
        GROUP BY m.id, m.nombre, e.nombre
        ORDER BY m.nombre
        """
    ).fetchall()


def conversaciones_recientes(
    conexion: psycopg.Connection,
    *,
    limite: int = 40,
) -> list[dict]:
    return conexion.execute(
        """
        SELECT id, telefono, sesion, rol, contenido, creada_en
        FROM conversaciones
        ORDER BY id DESC
        LIMIT %s
        """,
        (limite,),
    ).fetchall()


def agenda_del_dia(
    conexion: psycopg.Connection,
    *,
    medico_id: int,
    fecha: date,
) -> list[dict]:
    """Cupos de un médico en un día, con la cita activa si está tomado.

    Es la vista que usa la secretaria para agendar, completar o mover horas.
    """
    return conexion.execute(
        """
        SELECT
            h.id AS horario_id,
            h.inicio,
            h.fin,
            c.id AS cita_id,
            c.estado,
            c.canal,
            p.id AS paciente_id,
            p.nombre AS paciente,
            p.telefono,
            p.email
        FROM horarios h
        LEFT JOIN citas c
            ON c.horario_id = h.id
           AND c.estado IN ('confirmada', 'completada')
        LEFT JOIN pacientes p ON p.id = c.paciente_id
        WHERE h.medico_id = %s
          AND (h.inicio AT TIME ZONE 'America/Santiago')::date = %s
        ORDER BY h.inicio
        """,
        (medico_id, fecha),
    ).fetchall()


def completar_cita(
    conexion: psycopg.Connection,
    *,
    cita_id: int,
) -> dict | None:
    """Marca una cita confirmada como atendida (acción de recepción)."""
    return conexion.execute(
        """
        UPDATE citas
        SET estado = 'completada'
        WHERE id = %s
          AND estado = 'confirmada'
        RETURNING id, paciente_id, medico_id, horario_id, estado
        """,
        (cita_id,),
    ).fetchone()
