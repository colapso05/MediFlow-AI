import hashlib
import json
from uuid import UUID

import psycopg


class HorarioNoDisponible(Exception):
    """El cupo no existe, ya pasó o ya está reservado."""


class CitaNoEncontrada(Exception):
    """La cita no existe, no pertenece al paciente o ya no está activa."""


class ClaveIdempotenciaEnConflicto(Exception):
    """La clave ya fue usada para una solicitud diferente."""


def _huella_reserva(
    *,
    horario_id: int,
    nombre: str,
    email: str | None,
    telefono: str | None,
) -> str:
    solicitud = json.dumps(
        [horario_id, nombre, email, telefono],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(solicitud.encode("utf-8")).hexdigest()


def _buscar_reserva_idempotente(
    conexion: psycopg.Connection,
    *,
    idempotency_key: UUID,
    huella: str,
) -> dict | None:
    cita = conexion.execute(
        """
        SELECT id, paciente_id, medico_id, horario_id, estado, creada_en,
               idempotency_fingerprint
        FROM citas
        WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()

    if not cita:
        return None
    if cita["idempotency_fingerprint"] != huella:
        raise ClaveIdempotenciaEnConflicto

    return {
        campo: valor
        for campo, valor in cita.items()
        if campo != "idempotency_fingerprint"
    }


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
    idempotency_key: UUID,
) -> dict:
    """Registra una cita confirmada con reintentos idempotentes."""
    nombre = nombre.strip()
    email = email.strip().lower() if email else None
    telefono = telefono.strip() if telefono else None

    if not nombre:
        raise ValueError("El nombre del paciente es obligatorio")
    if not email and not telefono:
        raise ValueError("Se requiere un correo o teléfono de contacto")

    huella = _huella_reserva(
        horario_id=horario_id,
        nombre=nombre,
        email=email,
        telefono=telefono,
    )

    try:
        with conexion.transaction():
            cita_existente = _buscar_reserva_idempotente(
                conexion,
                idempotency_key=idempotency_key,
                huella=huella,
            )
            if cita_existente:
                return cita_existente

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

            cita_existente = _buscar_reserva_idempotente(
                conexion,
                idempotency_key=idempotency_key,
                huella=huella,
            )
            if cita_existente:
                return cita_existente

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
                INSERT INTO citas (
                    paciente_id, medico_id, horario_id, idempotency_key,
                    idempotency_fingerprint
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, paciente_id, medico_id, horario_id, estado,
                          creada_en
                """,
                (
                    paciente_id,
                    horario["medico_id"],
                    horario_id,
                    idempotency_key,
                    huella,
                ),
            ).fetchone()

            return cita
    except psycopg.errors.UniqueViolation as error:
        if error.diag.constraint_name == "citas_horario_activo_idx":
            raise HorarioNoDisponible from error
        if error.diag.constraint_name == "citas_idempotency_key_idx":
            cita_existente = _buscar_reserva_idempotente(
                conexion,
                idempotency_key=idempotency_key,
                huella=huella,
            )
            if cita_existente:
                return cita_existente
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