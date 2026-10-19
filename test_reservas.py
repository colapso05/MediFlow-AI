import unittest
from contextlib import nullcontext

from backend.reservas import (
    CitaNoEncontrada,
    HorarioNoDisponible,
    cancelar_cita,
    reagendar_cita,
    reservar_cita,
)


class ConexionPrueba:
    def __init__(self, *, ocupado=False, paciente_existente=False):
        self.ocupado = ocupado
        self.paciente_existente = paciente_existente
        self.sentencias = []

    def transaction(self):
        return nullcontext()

    def execute(self, consulta, parametros=None):
        consulta = " ".join(consulta.split())
        self.sentencias.append((consulta, parametros))

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
        if consulta.startswith("INSERT INTO citas"):
            return Resultado({
                "id": 19,
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
        )

        self.assertEqual(cita["id"], 19)
        self.assertEqual(conexion.sentencias[1][0], "SELECT 1 FROM citas WHERE horario_id = %s AND estado IN ('confirmada', 'completada')")
        self.assertEqual(
            conexion.sentencias[2][1],
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
            )

        self.assertEqual(len(conexion.sentencias), 2)

    def test_requiere_dato_de_contacto(self):
        conexion = ConexionPrueba()

        with self.assertRaisesRegex(ValueError, "correo o teléfono"):
            reservar_cita(
                conexion,
                horario_id=7,
                nombre="Paciente Demo",
            )

        self.assertEqual(conexion.sentencias, [])

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