import base64
import json
import ssl
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PRIVADO = Path(__file__).with_name("privado")
URL = "https://localhost:8443"
PREDICCION = "/api/predicciones/inasistencia"
CITA = {"dias_anticipacion": 60, "dia_semana": 6, "hora": 8}


def main():
    ssl_contexto = ssl.create_default_context(cafile=str(PRIVADO / "tls.crt"))
    clave = (PRIVADO / "clave-demo").read_text().strip()
    token = base64.b64encode(f"mediflow:{clave}".encode()).decode()

    def consultar(ruta, datos=None, autenticar=True):
        headers = {"Authorization": "Basic " + token} if autenticar else {}
        if datos is not None:
            headers["Content-Type"] = "application/json"
        carga = json.dumps(datos).encode() if datos is not None else None
        solicitud = Request(URL + ruta, data=carga, headers=headers)
        inicio = time.perf_counter()
        try:
            with urlopen(solicitud, context=ssl_contexto, timeout=15) as respuesta:
                return respuesta.status, respuesta.read(), (time.perf_counter() - inicio) * 1_000
        except HTTPError as error:
            return error.code, error.read(), (time.perf_counter() - inicio) * 1_000

    casos = [
        ("salud y PostgreSQL", "/api/health", None, True, 200),
        ("CRM", "/crm", None, True, 200),
        ("OpenAPI", "/openapi.json", None, True, 200),
        ("especialidades", "/api/especialidades", None, True, 200),
        ("resumen CRM", "/api/crm/resumen", None, True, 200),
        ("protección CRM", "/crm", None, False, 401),
        ("protección predicción", PREDICCION, CITA, False, 401),
        ("predicción con riesgo alto", PREDICCION, CITA, True, 200),
        ("predicción con riesgo bajo", PREDICCION, {**CITA, "dias_anticipacion": 0, "dia_semana": 0, "hora": 15}, True, 200),
        ("rechazo de hora inválida", PREDICCION, {**CITA, "hora": 24}, True, 422),
        ("rechazo de día inválido", PREDICCION, {**CITA, "dia_semana": 7}, True, 422),
    ]
    pruebas = []
    estimaciones = {}
    for nombre, ruta, datos, autenticar, esperado in casos:
        codigo, cuerpo, _ = consultar(ruta, datos, autenticar)
        assert codigo == esperado, (nombre, codigo, esperado)
        if nombre.startswith("predicción con"):
            estimacion = json.loads(cuerpo)
            assert estimacion["datos_entrenamiento"] == "sinteticos"
            assert estimacion["priorizar_recordatorio"] == nombre.endswith("alto")
            estimaciones[nombre] = estimacion
        pruebas.append({"caso": nombre, "estado_http": codigo})

    inicio = time.perf_counter()
    tiempos = []
    codigos = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        for _ in range(10):
            inicio_lote = time.perf_counter()
            for codigo, _, milisegundos in pool.map(lambda _: consultar(PREDICCION, CITA), range(5)):
                codigos[codigo] = codigos.get(codigo, 0) + 1
                if codigo == 200:
                    tiempos.append(milisegundos)
            time.sleep(max(0, 1 - (time.perf_counter() - inicio_lote)))

    percentiles = statistics.quantiles(tiempos, n=100, method="inclusive") if len(tiempos) > 1 else []
    informe = {
        "pruebas": pruebas,
        "predicciones": estimaciones,
        "carga": {
            "solicitudes": 50,
            "concurrencia": 5,
            "estados_http": codigos,
            "errores_pct": 100 * (1 - len(tiempos) / 50),
            "solicitudes_por_segundo": round(50 / (time.perf_counter() - inicio), 2),
            "latencia_ms": {f"p{p}": round(percentiles[p - 1], 2) for p in (50, 95, 99)} if percentiles else {},
        },
    }
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    assert len(tiempos) == 50, codigos


if __name__ == "__main__":
    main()
