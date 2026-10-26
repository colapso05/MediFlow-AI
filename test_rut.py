import unittest

from backend.rut import calcular_dv, formatear_rut, validar_rut


class TestDigitoVerificador(unittest.TestCase):
    def test_digito_numerico(self):
        self.assertEqual(calcular_dv("12345678"), "5")
        self.assertEqual(calcular_dv("76086423"), "4")
        self.assertEqual(calcular_dv("11111111"), "1")

    def test_digito_k(self):
        self.assertEqual(calcular_dv("12345684"), "K")

    def test_digito_cero(self):
        self.assertEqual(calcular_dv("19999999"), "0")


class TestNormalizacion(unittest.TestCase):
    def test_formatos_equivalentes(self):
        for escrito in ("12.345.678-5", "12345678-5", "123456785", "12 345 678 5",
                        "  12.345.678-5  "):
            with self.subTest(escrito=escrito):
                rut, error = validar_rut(escrito)
                self.assertIsNone(error)
                self.assertEqual(rut, "12345678-5")

    def test_k_minuscula(self):
        rut, error = validar_rut("12.345.684-k")
        self.assertIsNone(error)
        self.assertEqual(rut, "12345684-K")

    def test_cero_como_digito(self):
        rut, error = validar_rut("19999999-0")
        self.assertIsNone(error)
        self.assertEqual(rut, "19999999-0")

    def test_rut_corto_valido(self):
        rut, error = validar_rut("1234567-4")
        self.assertIsNone(error)
        self.assertEqual(rut, "1234567-4")


class TestRechazos(unittest.TestCase):
    def test_digito_incorrecto(self):
        _, error = validar_rut("12345678-9")
        self.assertIn("dígito verificador", error)

    def test_todos_ceros(self):
        _, error = validar_rut("00000000-0")
        self.assertIn("no existe", error)

    def test_muy_corto(self):
        _, error = validar_rut("123")
        self.assertIn("entre 6 y 8", error)

    def test_con_letras(self):
        _, error = validar_rut("abc123")
        self.assertIn("numérico", error)

    def test_vacio(self):
        for valor in ("", "   ", None):
            with self.subTest(valor=valor):
                rut, error = validar_rut(valor)
                self.assertIsNone(rut)
                self.assertIn("Falta", error)

    def test_dos_guiones(self):
        _, error = validar_rut("12-345-678-5")
        self.assertIn("un solo guion", error)

    def test_sin_digito(self):
        _, error = validar_rut("12.345.678")
        self.assertIsNotNone(error)

    def test_digito_fuera_de_rango(self):
        _, error = validar_rut("12345678-X")
        self.assertIn("dígito verificador", error)


class TestFormatoVisible(unittest.TestCase):
    def test_pone_puntos(self):
        self.assertEqual(formatear_rut("12345678-5"), "12.345.678-5")
        self.assertEqual(formatear_rut("1234567-4"), "1.234.567-4")

    def test_tolera_vacio(self):
        self.assertIsNone(formatear_rut(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
