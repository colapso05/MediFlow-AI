import hashlib
import json
from uuid import UUID

import psycopg

from backend.rut import validar_rut


class HorarioNoDisponible(Exception):
    """El cupo no existe, ya pasó o ya está reservado."""


class CitaNoEncontrada(Exception):
    """La cita no existe, no pertenece al paciente o ya no está activa."""


class ClaveIdempotenciaEnConflicto(Exception):
    """La clave ya fue usada para una solicitud diferente."""


class RutInvalido(Exception):
    """El RUT no cumple el módulo 11 o no viene informado."""


class RutDeOtroPaciente(Exception):
    """El RUT ya está asociado a otra ficha o el número ya tiene otro RUT."""


class PacienteConCitaEnEseHorario(Exception):
    """El paciente ya tiene otra cita activa que se solapa con ese horario.

    Un paciente puede tener varias citas el mismo día con especialistas
    distintos, pero no dos a la misma hora: no puede estar en dos box a la vez.
    """

    def __init__(self, detalle: dict):
        self.detalle = detalle
        super().__init__(
            "El paciente ya tiene una cita a esa misma hora: "
            f"{detalle.get('medico')} ({detalle.get('especialidad')})."
        )


def _huella_reserva(
    *,
    horario_id: int,
    nombre: str,
    email: str | None,
    telefono: str | None,
    rut: str | None = None,
) -> str:
    solicitud = json.dumps(
        [horario_id, nombre, email, telefono, rut],
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
    rut: str | None = None,
) -> int:
    """Resuelve la ficha del paciente.

    Con RUT, la identidad manda el RUT y el teléfono solo confirma: si la ficha
    del número ya tiene otro RUT, o el RUT ya está en otra ficha, se rechaza la
    reserva en vez de mezclar historiales clínicos.
    """
    if rut:
        ficha_telefono = conexion.execute(
            """
            SELECT id, rut, nombre
            FROM pacientes
            WHERE telefono = %s
            ORDER BY id
            LIMIT 1
            FOR UPDATE
            """,
            (telefono,),
        ).fetchone()

        if ficha_telefono:
            if ficha_telefono["rut"] and ficha_telefono["rut"] != rut:
                raise RutDeOtroPaciente(
                    "Este número ya tiene una ficha con otro RUT. "
                    "Recepción debe verificarlo antes de agendar."
                )
            if not ficha_telefono["rut"]:
                ocupado = conexion.execute(
                    "SELECT 1 FROM pacientes WHERE rut = %s AND id <> %s",
                    (rut, ficha_telefono["id"]),
                ).fetchone()
                if ocupado:
                    raise RutDeOtroPaciente(
                        "Ese RUT ya está registrado en otra ficha."
                    )
                conexion.execute(
                    "UPDATE pacientes SET rut = %s WHERE id = %s",
                    (rut, ficha_telefono["id"]),
                )
            return ficha_telefono["id"]

        otra_ficha = conexion.execute(
            "SELECT id, telefono FROM pacientes WHERE rut = %s",
            (rut,),
        ).fetchone()
        if otra_ficha:
            raise RutDeOtroPaciente(
                "Ese RUT ya está registrado con otro número. "
                "Por seguridad, recepción debe verificarlo."
            )

        # El correo es único: si ya pertenece a otra ficha, no se duplica.
        email_libre = None
        if email:
            en_uso = conexion.execute(
                "SELECT 1 FROM pacientes WHERE email = %s", (email,)
            ).fetchone()
            email_libre = None if en_uso else email

        fila = conexion.execute(
            """
            INSERT INTO pacientes (nombre, rut, email, telefono)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (nombre, rut, email_libre, telefono),
        ).fetchone()
        return fila["id"]

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


def _cita_solapada(
    conexion: psycopg.Connection,
    *,
    paciente_id: int,
    inicio,
    fin,
    excluir_cita_id: int | None = None,
) -> dict | None:
    """Busca otra cita activa del paciente que se cruce con [inicio, fin)."""
    return conexion.execute(
        """
        SELECT c.id, h.inicio, h.fin, m.nombre AS medico,
               e.nombre AS especialidad
        FROM citas c
        JOIN horarios h ON h.id = c.horario_id
        JOIN medicos m ON m.id = c.medico_id
        JOIN especialidades e ON e.id = m.especialidad_id
        WHERE c.paciente_id = %s
          AND c.estado IN ('confirmada', 'completada')
          AND h.inicio < %s
          AND h.fin > %s
          AND c.id <> COALESCE(%s::int, -1)
        ORDER BY h.inicio
        LIMIT 1
        """,
        (paciente_id, fin, inicio, excluir_cita_id),
    ).fetchone()


def reservar_cita(
    conexion: psycopg.Connection,
    *,
    horario_id: int,
    nombre: str,
    email: str | None = None,
    telefono: str | None = None,
    rut: str | None = None,
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

    if rut is not None:
        rut, error = validar_rut(rut)
        if error:
            raise RutInvalido(error)

    huella = _huella_reserva(
        horario_id=horario_id,
        nombre=nombre,
        email=email,
        telefono=telefono,
        rut=rut,
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
                SELECT h.id, h.medico_id, h.inicio, h.fin
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
                rut=rut,
            )

            # Varias citas el mismo dia estan bien; a la misma hora no.
            choque = _cita_solapada(
                conexion,
                paciente_id=paciente_id,
                inicio=horario["inicio"],
                fin=horario["fin"],
            )
            if choque:
                raise PacienteConCitaEnEseHorario(dict(choque))

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
                SELECT h.id, h.medico_id, h.inicio, h.fin
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

            choque = _cita_solapada(
                conexion,
                paciente_id=paciente_id,
                inicio=horario["inicio"],
                fin=horario["fin"],
                excluir_cita_id=cita_id,
            )
            if choque:
                raise PacienteConCitaEnEseHorario(dict(choque))

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