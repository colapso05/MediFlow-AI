import unittest
from datetime import date

from backend.agenda import consultar_horarios


class ConexionPrueba:
    def __init__(self):
        self.consulta = None
        self.parametros = None

    def execute(self, consulta, parametros):
        self.consulta = consulta
        self.parametros = parametros
        return self

    def fetchall(self):
        return []


class AgendaTest(unittest.TestCase):
    def test_consulta_aplica_filtros_de_fecha_y_santiago(self):
        conexion = ConexionPrueba()

        resultado = consultar_horarios(
            conexion,
            medico_id=4,
            especialidad_id=2,
            desde=date(2026, 10, 20),
            hasta=date(2026, 10, 24),
            limite=12,
        )

        self.assertEqual(resultado, [])
        self.assertEqual(conexion.parametros["medico_id"], 4)
        self.assertEqual(conexion.parametros["especialidad_id"], 2)
        self.assertEqual(conexion.parametros["limite"], 12)
        self.assertIn("America/Santiago", conexion.consulta)
        self.assertIn("NOT EXISTS", conexion.consulta)

    def test_rechaza_intervalo_invertido_sin_consultar(self):
        conexion = ConexionPrueba()

        with self.assertRaisesRegex(ValueError, "fecha final"):
            consultar_horarios(
                conexion,
                desde=date(2026, 10, 24),
                hasta=date(2026, 10, 20),
            )

        self.assertIsNone(conexion.consulta)


if __name__ == "__main__":
    unittest.main()