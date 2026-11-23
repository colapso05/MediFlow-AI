import io
import json
import os
import unittest
from unittest.mock import patch

import boto3
import httpx
from botocore.response import StreamingBody
from botocore.stub import Stubber
from fastapi.testclient import TestClient

from deployment.sagemaker.inferencia import app as app_inferencia

with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "clave-local-sin-uso"}):
    from backend.main import app


RUTA_API = "/api/predicciones/inasistencia"
CITA = {"dias_anticipacion": 60.0, "dia_semana": 6, "hora": 8}
ENDPOINT = "mediflow-prueba"


class InferenciaTest(unittest.TestCase):
    def setUp(self):
        self.modelo = TestClient(app_inferencia)
        self.api = TestClient(app)
        self.addCleanup(self.modelo.close)
        self.addCleanup(self.api.close)

    def test_ping_responde_sin_cuerpo(self):
        respuesta = self.modelo.get("/ping")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.content, b"")

    def test_prediccion_explica_prioridad(self):
        respuesta = self.modelo.post("/invocations", json=CITA)
        self.assertEqual(respuesta.status_code, 200)
        prediccion = respuesta.json()
        self.assertTrue(prediccion["priorizar_recordatorio"])
        self.assertEqual(len(prediccion["factores"]), 3)
        self.assertEqual(prediccion["datos_entrenamiento"], "sinteticos")

    def test_validacion_de_entrada(self):
        for cambio in ({"dias_anticipacion": -1}, {"dia_semana": 7}, {"hora": 24}):
            with self.subTest(cambio=cambio):
                respuesta = self.modelo.post("/invocations", json={**CITA, **cambio})
                self.assertEqual(respuesta.status_code, 422)

    def test_api_local_usa_el_mismo_modelo(self):
        with patch.dict(os.environ, {"SAGEMAKER_ENDPOINT": "", "INFERENCIA_URL": ""}):
            respuesta = self.api.post(RUTA_API, json=CITA)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), self.modelo.post("/invocations", json=CITA).json())

    def test_api_ec2_usa_el_contenedor_de_inferencia(self):
        servicio = "http://inferencia:8080/invocations"
        resultado = self.modelo.post("/invocations", json=CITA).json()
        solicitud = httpx.Request("POST", servicio)
        respuesta_remota = httpx.Response(200, json=resultado, request=solicitud)
        with patch.dict(os.environ, {"INFERENCIA_URL": servicio}):
            with patch("backend.main.httpx.post", return_value=respuesta_remota) as enviar:
                respuesta = self.api.post(RUTA_API, json=CITA)
                enviar.assert_called_once_with(servicio, json=CITA, timeout=10)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), resultado)

    def test_api_ec2_informa_indisponibilidad_del_contenedor(self):
        with patch.dict(os.environ, {"INFERENCIA_URL": "http://inferencia:8080/invocations"}):
            with patch("backend.main.httpx.post", side_effect=httpx.ConnectError("sin conexión")):
                respuesta = self.api.post(RUTA_API, json=CITA)
        self.assertEqual(respuesta.status_code, 502)

    def test_inferencia_publica_el_resultado_cuando_hay_cola(self):
        url = "amqp://rabbitmq/%2F"
        with patch.dict(os.environ, {"AMQP_URL": url}):
            with patch("deployment.sagemaker.inferencia.publicar") as publicar:
                respuesta = self.modelo.post("/invocations", json=CITA)
                publicar.assert_called_once_with(url, respuesta.json())
        self.assertEqual(respuesta.status_code, 200)

    def test_api_invoca_sagemaker_con_el_contrato_esperado(self):
        resultado = self.modelo.post("/invocations", json=CITA).json()
        datos = json.dumps(resultado).encode()
        cliente = self._runtime_de_prueba()

        with Stubber(cliente) as stub:
            stub.add_response("invoke_endpoint", {
                "Body": StreamingBody(io.BytesIO(datos), len(datos)),
                "ContentType": "application/json",
            }, {
                "EndpointName": ENDPOINT,
                "ContentType": "application/json",
                "Accept": "application/json",
                "Body": json.dumps(CITA, separators=(",", ":")).encode(),
            })
            with patch.dict(os.environ, {"SAGEMAKER_ENDPOINT": ENDPOINT, "INFERENCIA_URL": ""}):
                with patch("backend.sagemaker_runtime.cliente_runtime", return_value=cliente):
                    respuesta = self.api.post(RUTA_API, json=CITA)
            stub.assert_no_pending_responses()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), resultado)

    def test_falla_remota_devuelve_502(self):
        cliente = self._runtime_de_prueba()
        with Stubber(cliente) as stub:
            stub.add_client_error("invoke_endpoint", service_error_code="ServiceUnavailable", http_status_code=503)
            with patch.dict(os.environ, {"SAGEMAKER_ENDPOINT": ENDPOINT, "INFERENCIA_URL": ""}):
                with patch("backend.sagemaker_runtime.cliente_runtime", return_value=cliente):
                    respuesta = self.api.post(RUTA_API, json=CITA)
            stub.assert_no_pending_responses()

        self.assertEqual(respuesta.status_code, 502)

    def _runtime_de_prueba(self):
        return boto3.client(
            "sagemaker-runtime", region_name="us-east-1", aws_access_key_id="prueba",
            aws_secret_access_key="prueba",
        )
