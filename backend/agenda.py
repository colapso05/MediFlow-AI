from datetime import date

import psycopg


def consultar_horarios(
    conexion: psycopg.Connection,
    *,
    medico_id: int | None = None,
    especialidad_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = 50,
) -> list[dict]:
    """Consulta cupos libres reales en la zona horaria de Santiago."""
    if desde and hasta and hasta < desde:
        raise ValueError("La fecha final no puede ser anterior a la inicial")

    return conexion.execute(
        """
        SELECT
            h.id,
            h.medico_id,
            m.nombre AS medico,
            e.id AS especialidad_id,
            e.nombre AS especialidad,
            h.inicio,
            h.fin
        FROM horarios h
        JOIN medicos m ON m.id = h.medico_id
        JOIN especialidades e ON e.id = m.especialidad_id
        WHERE m.activo = TRUE
          AND (%(medico_id)s IS NULL OR h.medico_id = %(medico_id)s)
          AND (
              %(especialidad_id)s IS NULL
              OR m.especialidad_id = %(especialidad_id)s
          )
          AND (
              %(desde)s::date IS NULL
              OR h.inicio >= (
                  %(desde)s::date::timestamp
                  AT TIME ZONE 'America/Santiago'
              )
          )
          AND (
              %(hasta)s::date IS NULL
              OR h.inicio < (
                  (%(hasta)s::date + 1)::timestamp
                  AT TIME ZONE 'America/Santiago'
              )
          )
          AND h.inicio > NOW()
          AND NOT EXISTS (
              SELECT 1
              FROM citas c
              WHERE c.horario_id = h.id
                AND c.estado IN ('confirmada', 'completada')
          )
        ORDER BY h.inicio
        LIMIT %(limite)s
        """,
        {
            "medico_id": medico_id,
            "especialidad_id": especialidad_id,
            "desde": desde,
            "hasta": hasta,
            "limite": limite,
        },
    ).fetchall()