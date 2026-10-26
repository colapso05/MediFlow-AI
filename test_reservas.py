import unittest
from contextlib import nullcontext
from uuid import UUID

from backend.reservas import (
    CitaNoEncontrada,
    ClaveIdempotenciaEnConflicto,
    HorarioNoDisponible,
    _huella_reserva,
    cancelar_cita,
    reagendar_cita,
    reservar_cita,
)


class ConexionPrueba:
    def __init__(
        self,
        *,
        ocupado=False,
        paciente_existente=False,
        aparece_idempotencia_despues_bloqueo=False,
    ):
        self.ocupado = ocupado
        self.paciente_existente = paciente_existente
        self.aparece_idempotencia_despues_bloqueo = (
            aparece_idempotencia_despues_bloqueo
        )
        self.consultas_idempotencia = 0
        self.sentencias = []
        self.cita_idempotente = None

    def transaction(self):
        return nullcontext()

    def execute(self, consulta, parametros=None):
        consulta = " ".join(consulta.split())
        self.sentencias.append((consulta, parametros))

        if "WHERE idempotency_key = %s" in consulta:
            self.consultas_idempotencia += 1
            if (
                self.aparece_idempotencia_despues_bloqueo
                and self.consultas_idempotencia == 2
            ):
                self.cita_idempotente = {
                    "id": 19,
                    "paciente_id": 11,
                    "medico_id": 3,
                    "horario_id": 7,
                    "estado": "confirmada",
                    "creada_en": None,
                    "idempotency_fingerprint": _huella_reserva(
                        horario_id=7,
                        nombre="Paciente Demo",
                        email="demo@example.com",
                        telefono=None,
                        rut=None,
                    ),
                }
            fila = self.cita_idempotente
            return Resultado(dict(fila) if fila else None)
        if consulta.startswith("SELECT id, paciente_id, medico_id, horario_id FROM citas"):
            if parametros == (19, 11):
                return Resultado({
                    "id": 19,
                    "paciente_id": 11,
                    "medico_id": 3,
                    "horario_id": 7,
                })
            return Resultado(None)
        if consulta.startswith("SELECT h.id, h.medico_id"):
            if parametros == (8, 3):
                return Resultado({"id": 8, "medico_id": 3})
            return Resultado({"id": 7, "medico_id": 3})
        if consulta.startswith("SELECT 1 FROM citas"):
            return Resultado({"?column?": 1} if self.ocupado else None)
        if consulta.startswith("UPDATE citas") and "RETURNING" in consulta:
            if parametros == (19, 11):
                return Resultado({
                    "id": 19,
                    "paciente_id": 11,
                    "estado": "cancelada",
                })
            return Resultado(None)
        if consulta.startswith("UPDATE citas"):
            return Resultado(None)
        if consulta.startswith("INSERT INTO pacientes"):
            if self.paciente_existente:
                return Resultado(None)
            return Resultado({"id": 11})
        if consulta.startswith("SELECT id FROM pacientes"):
            return Resultado({"id": 11})
        if consulta.startswith("INSERT INTO citas") and len(parametros) == 5:
            cita = {
                "id": 19,
                "paciente_id": parametros[0],
                "medico_id": parametros[1],
                "horario_id": parametros[2],
                "estado": "confirmada",
                "creada_en": None,
            }
            self.cita_idempotente = {
                **cita,
                "idempotency_fingerprint": parametros[4],
            }
            return Resultado(cita)
        if consulta.startswith("INSERT INTO citas"):
            return Resultado({
                "id": 20,
                "paciente_id": parametros[0],
                "medico_id": parametros[1],
                "horario_id": parametros[2],
                "estado": "confirmada",
                "creada_en": None,
            })
        raise AssertionError(f"Consulta inesperada: {consulta}")


class Resultado:
    def __init__(self, fila):
        self.fila = fila

    def fetchone(self):
        return self.fila


class ReservasTest(unittest.TestCase):
    def test_reserva_cupo_y_normaliza_email(self):
        conexion = ConexionPrueba()

        cita = reservar_cita(
            conexion,
            horario_id=7,
            nombre="  Paciente Demo  ",
            email=" Demo@Example.com ",
            idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )

        self.assertEqual(cita["id"], 19)
        self.assertTrue(any(
            consulta.startswith("SELECT 1 FROM citas")
            for consulta, _ in conexion.sentencias
        ))
        self.assertEqual(
            next(
                parametros
                for consulta, parametros in conexion.sentencias
                if consulta.startswith("INSERT INTO pacientes")
            ),
            ("Paciente Demo", "demo@example.com", None),
        )

    def test_cupo_ocupado_no_crea_paciente(self):
        conexion = ConexionPrueba(ocupado=True)

        with self.assertRaises(HorarioNoDisponible):
            reservar_cita(
                conexion,
                horario_id=7,
                nombre="Paciente Demo",
                email="demo@example.com",
                idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            )

        self.assertFalse(any(
            consulta.startswith("INSERT INTO pacientes")
            for consulta, _ in conexion.sentencias
        ))

    def test_requiere_dato_de_contacto(self):
        conexion = ConexionPrueba()

        with self.assertRaisesRegex(ValueError, "correo o teléfono"):
            reservar_cita(
                conexion,
                horario_id=7,
                nombre="Paciente Demo",
                idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            )

        self.assertEqual(conexion.sentencias, [])

    def test_reintento_idempotente_devuelve_la_misma_cita(self):
        conexion = ConexionPrueba()
        solicitud = {
            "horario_id": 7,
            "nombre": "Paciente Demo",
            "email": "demo@example.com",
            "idempotency_key": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        }

        primera = reservar_cita(conexion, **solicitud)
        segunda = reservar_cita(conexion, **solicitud)

        self.assertEqual(primera, segunda)
        self.assertEqual(sum(
            consulta.startswith("INSERT INTO citas")
            for consulta, _ in conexion.sentencias
        ), 1)

    def test_clave_idempotente_no_acepta_otra_solicitud(self):
        conexion = ConexionPrueba()
        clave = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        reservar_cita(
            conexion,
            horario_id=7,
            nombre="Paciente Demo",
            email="demo@example.com",
            idempotency_key=clave,
        )

        with self.assertRaises(ClaveIdempotenciaEnConflicto):
            reservar_cita(
                conexion,
                horario_id=8,
                nombre="Paciente Demo",
                email="demo@example.com",
                idempotency_key=clave,
            )

        self.assertEqual(sum(
            consulta.startswith("INSERT INTO citas")
            for consulta, _ in conexion.sentencias
        ), 1)

    def test_reintento_concurrente_revisa_clave_tras_bloquear_cupo(self):
        conexion = ConexionPrueba(
            aparece_idempotencia_despues_bloqueo=True,
        )

        cita = reservar_cita(
            conexion,
            horario_id=7,
            nombre="Paciente Demo",
            email="demo@example.com",
            idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )

        self.assertEqual(cita["id"], 19)
        self.assertEqual(conexion.consultas_idempotencia, 2)
        self.assertFalse(any(
            consulta.startswith("SELECT 1 FROM citas")
            for consulta, _ in conexion.sentencias
        ))

    def test_cancelacion_solo_pertenece_al_paciente(self):
        conexion = ConexionPrueba()

        with self.assertRaises(CitaNoEncontrada):
            cancelar_cita(conexion, cita_id=19, paciente_id=12)

        self.assertEqual(len(conexion.sentencias), 1)

    def test_reagenda_cita_a_un_cupo_libre(self):
        conexion = ConexionPrueba()

        cita = reagendar_cita(
            conexion,
            cita_id=19,
            paciente_id=11,
            nuevo_horario_id=8,
        )

        self.assertEqual(cita["horario_id"], 8)
        self.assertEqual(conexion.sentencias[-1][1], (19,))

    def test_reagenda_no_cambia_cita_si_el_nuevo_cupo_esta_ocupado(self):
        conexion = ConexionPrueba(ocupado=True)

        with self.assertRaises(HorarioNoDisponible):
            reagendar_cita(
                conexion,
                cita_id=19,
                paciente_id=11,
                nuevo_horario_id=8,
            )

        self.assertFalse(any(
            consulta.startswith("UPDATE citas")
            for consulta, _ in conexion.sentencias
        ))


if __name__ == "__main__":
    unittest.main()