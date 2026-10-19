import psycopg


class HorarioNoDisponible(Exception):
    """El cupo no existe, ya pasó o ya está reservado."""


class CitaNoEncontrada(Exception):
    """La cita no existe, no pertenece al paciente o ya no está activa."""


def _obtener_o_crear_paciente(
    conexion: psycopg.Connection,
    *,
    nombre: str,
    email: str | None,
    telefono: str | None,
) -> int:
    if email:
        paciente = conexion.execute(
            """
            INSERT INTO pacientes (nombre, email, telefono)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id
            """,
            (nombre, email, telefono),
        ).fetchone()

        if paciente:
            return paciente["id"]

        paciente = conexion.execute(
            "SELECT id FROM pacientes WHERE email = %s",
            (email,),
        ).fetchone()
        return paciente["id"]

    conexion.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s), 0)",
        (telefono,),
    )
    paciente = conexion.execute(
        """
        SELECT id
        FROM pacientes
        WHERE telefono = %s
        ORDER BY id
        LIMIT 1
        FOR UPDATE
        """,
        (telefono,),
    ).fetchone()

    if paciente:
        return paciente["id"]

    paciente = conexion.execute(
        """
        INSERT INTO pacientes (nombre, telefono)
        VALUES (%s, %s)
        RETURNING id
        """,
        (nombre, telefono),
    ).fetchone()
    return paciente["id"]


def reservar_cita(
    conexion: psycopg.Connection,
    *,
    horario_id: int,
    nombre: str,
    email: str | None = None,
    telefono: str | None = None,
) -> dict:
    """Registra una cita confirmada dentro de una transacción PostgreSQL."""
    nombre = nombre.strip()
    email = email.strip().lower() if email else None
    telefono = telefono.strip() if telefono else None

    if not nombre:
        raise ValueError("El nombre del paciente es obligatorio")
    if not email and not telefono:
        raise ValueError("Se requiere un correo o teléfono de contacto")

    try:
        with conexion.transaction():
            horario = conexion.execute(
                """
                SELECT h.id, h.medico_id
                FROM horarios h
                JOIN medicos m ON m.id = h.medico_id
                WHERE h.id = %s
                  AND h.inicio > NOW()
                  AND m.activo = TRUE
                FOR UPDATE OF h
                """,
                (horario_id,),
            ).fetchone()

            if not horario:
                raise HorarioNoDisponible

            ocupado = conexion.execute(
                """
                SELECT 1
                FROM citas
                WHERE horario_id = %s
                  AND estado IN ('confirmada', 'completada')
                """,
                (horario_id,),
            ).fetchone()

            if ocupado:
                raise HorarioNoDisponible

            paciente_id = _obtener_o_crear_paciente(
                conexion,
                nombre=nombre,
                email=email,
                telefono=telefono,
            )
            cita = conexion.execute(
                """
                INSERT INTO citas (paciente_id, medico_id, horario_id)
                VALUES (%s, %s, %s)
                RETURNING id, paciente_id, medico_id, horario_id, estado,
                          creada_en
                """,
                (paciente_id, horario["medico_id"], horario_id),
            ).fetchone()

            return cita
    except psycopg.errors.UniqueViolation as error:
        if error.diag.constraint_name == "citas_horario_activo_idx":
            raise HorarioNoDisponible from error
        raise


def cancelar_cita(
    conexion: psycopg.Connection,
    *,
    cita_id: int,
    paciente_id: int,
) -> dict:
    """Cancela una cita activa únicamente si pertenece al paciente indicado."""
    with conexion.transaction():
        cita = conexion.execute(
            """
            UPDATE citas
            SET estado = 'cancelada'
            WHERE id = %s
              AND paciente_id = %s
              AND estado = 'confirmada'
            RETURNING id, paciente_id, medico_id, horario_id, estado,
                      creada_en
            """,
            (cita_id, paciente_id),
        ).fetchone()

        if not cita:
            raise CitaNoEncontrada

        return cita


def reagendar_cita(
    conexion: psycopg.Connection,
    *,
    cita_id: int,
    paciente_id: int,
    nuevo_horario_id: int,
) -> dict:
    """Cambia el cupo de una cita en una sola transacción."""
    try:
        with conexion.transaction():
            cita = conexion.execute(
                """
                SELECT id, paciente_id, medico_id, horario_id
                FROM citas
                WHERE id = %s
                  AND paciente_id = %s
                  AND estado = 'confirmada'
                FOR UPDATE
                """,
                (cita_id, paciente_id),
            ).fetchone()

            if not cita:
                raise CitaNoEncontrada
            if cita["horario_id"] == nuevo_horario_id:
                return cita

            horario = conexion.execute(
                """
                SELECT h.id, h.medico_id
                FROM horarios h
                JOIN medicos m ON m.id = h.medico_id
                WHERE h.id = %s
                  AND h.medico_id = %s
                  AND h.inicio > NOW()
                  AND m.activo = TRUE
                FOR UPDATE OF h
                """,
                (nuevo_horario_id, cita["medico_id"]),
            ).fetchone()

            if not horario:
                raise HorarioNoDisponible

            ocupado = conexion.execute(
                """
                SELECT 1
                FROM citas
                WHERE horario_id = %s
                  AND estado IN ('confirmada', 'completada')
                """,
                (nuevo_horario_id,),
            ).fetchone()

            if ocupado:
                raise HorarioNoDisponible

            nueva_cita = conexion.execute(
                """
                INSERT INTO citas (paciente_id, medico_id, horario_id)
                VALUES (%s, %s, %s)
                RETURNING id, paciente_id, medico_id, horario_id, estado,
                          creada_en
                """,
                (paciente_id, cita["medico_id"], nuevo_horario_id),
            ).fetchone()
            conexion.execute(
                "UPDATE citas SET estado = 'cancelada' WHERE id = %s",
                (cita_id,),
            )

            return nueva_cita
    except psycopg.errors.UniqueViolation as error:
        if error.diag.constraint_name == "citas_horario_activo_idx":
            raise HorarioNoDisponible from error
        raise