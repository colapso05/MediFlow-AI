
import logging
import os
import re
import threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage

from backend.agenda import consultar_horarios
from backend.reservas import (
    CitaNoEncontrada,
    ClaveIdempotenciaEnConflicto,
    HorarioNoDisponible,
    cancelar_cita,
    reagendar_cita,
    reservar_cita,
)
from backend.servicios import (
    agenda_del_dia,
    agenda_por_medico,
    citas_del_paciente,
    completar_cita,
    conversaciones_recientes,
    listar_citas,
    obtener_paciente_por_telefono,
    resumen_crm,
)
from herramientas import HERRAMIENTAS, TELEFONO_ACTUAL  # noqa: F401
from agente import agente

load_dotenv()

ESTATICOS = Path(__file__).parent / "static"
RAIZ = Path(__file__).resolve().parent.parent

# Registro de fallos del agente en archivo: si algo falla durante una demo,
# queda el rastro completo en logs/errores.log en vez de perderse en la consola.
CARPETA_LOGS = RAIZ / "logs"
CARPETA_LOGS.mkdir(exist_ok=True)
registro = logging.getLogger("mediflow")
if not registro.handlers:
    manejador = logging.FileHandler(CARPETA_LOGS / "errores.log", encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    registro.addHandler(manejador)
    registro.setLevel(logging.INFO)

app = FastAPI(
    title="MediFlow AI API",
    description="API administrativa para la clínica MediFlow",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@contextmanager
def obtener_conexion():
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        row_factory=dict_row,
    ) as conexion:
        yield conexion


# ---------------------------------------------------------------------------
# Modelos de entrada
# ---------------------------------------------------------------------------


class MensajeChat(BaseModel):
    mensaje: str
    # Tolerante a campos extra: un cliente puede mandar metadatos del mensaje
    # (por ejemplo las herramientas usadas) y la conversación no debe romperse.
    historial: list[dict] = Field(default_factory=list)
    telefono: str | None = None
    sesion: str | None = None


class NuevaCita(BaseModel):
    horario_id: int
    nombre: str
    rut: str | None = None
    email: str | None = None
    telefono: str | None = None
    canal: str = "web"


class Cancelacion(BaseModel):
    telefono: str | None = None


class Reagendamiento(BaseModel):
    nuevo_horario_id: int
    telefono: str | None = None


# ---------------------------------------------------------------------------
# Guardrails deterministas (no dependen del modelo)
# ---------------------------------------------------------------------------

# Intentos de cambiar el rol, las reglas o el formato de salida del agente.
PATRONES_ENTRADA = [
    r"ignora\s+(todas\s+)?(tus|las)\s+instrucciones",
    r"olvida\s+(que\s+eres|tus\s+instrucciones|todo\s+lo\s+anterior)",
    r"responde\s+(solo|solamente|únicamente|unicamente)\s+con",
    r"(modo|eres)\s+dan\b",
    r"(revela|mu[eé]stra|dime|ense[nñ]ame)\s+(tu|el)\s+(prompt|system\s*prompt|instrucciones)",
    r"sin\s+(reglas|restricciones|filtros|limites|l[ií]mites)",
    r"ahora\s+eres\s+",
    r"(jailbreak|prompt\s*injection|modo\s+desarrollador)",
]

# Lo que una respuesta NUNCA debe contener, aunque el modelo se equivoque.
PATRONES_SALIDA = [
    r"system\s*prompt",
    r"(mis|tus)\s+instrucciones\s+(son|internas)",
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}",
    r"\b(horario_id|cita_id|paciente_id)\b",
    r"\bsk-[A-Za-z0-9]{10,}",
]

RESPUESTA_GUARDRAIL = (
    "No puedo cambiar mi rol ni mis instrucciones: sigo siendo la recepcionista "
    "virtual de MediFlow. Sí puedo agendar, reagendar o cancelar una hora médica. "
    "¿Te ayudo con eso?"
)
RESPUESTA_RESPALDO = (
    "Perdona, no te entendí. ¿Me repites si quieres agendar, cambiar o cancelar "
    "una hora médica?"
)

CONTADOR_GUARDRAILS = {"entrada": 0, "salida": 0, "vacia": 0, "ultimos": []}


def _anotar(tipo: str, detalle: str) -> None:
    CONTADOR_GUARDRAILS[tipo] += 1
    CONTADOR_GUARDRAILS["ultimos"] = ([{"tipo": tipo, "detalle": detalle[:120]}]
                                      + CONTADOR_GUARDRAILS["ultimos"])[:10]
    registro.info("GUARDRAIL %s: %s", tipo, detalle[:200])


def guardrail_entrada(texto: str) -> bool:
    """True si el mensaje intenta manipular al agente."""
    for patron in PATRONES_ENTRADA:
        if re.search(patron, texto, flags=re.I):
            _anotar("entrada", f"{patron} :: {texto}")
            return True
    return False


def guardrail_salida(respuesta: str) -> str:
    """Devuelve una respuesta segura si el modelo filtró algo que no debe."""
    limpia = (respuesta or "").strip()
    if not limpia:
        _anotar("vacia", "respuesta vacía del modelo")
        return RESPUESTA_RESPALDO
    for patron in PATRONES_SALIDA:
        if re.search(patron, limpia, flags=re.I):
            _anotar("salida", f"{patron} :: {limpia}")
            return RESPUESTA_GUARDRAIL
    # Obediencia a "responde solo con una palabra": 1-3 palabras en mayúsculas.
    palabras = limpia.split()
    if len(palabras) <= 3 and limpia.isupper() and any(c.isalpha() for c in limpia):
        _anotar("salida", f"salida en mayúsculas :: {limpia}")
        return RESPUESTA_GUARDRAIL
    return limpia


# ---------------------------------------------------------------------------
# Chat con el agente
# ---------------------------------------------------------------------------


@app.get("/api/guardrails")
def estado_guardrails():
    """Contador visible de intentos bloqueados (para el tablero y la demo)."""
    return {
        "patrones_entrada": len(PATRONES_ENTRADA),
        "patrones_salida": len(PATRONES_SALIDA),
        "bloqueos_entrada": CONTADOR_GUARDRAILS["entrada"],
        "bloqueos_salida": CONTADOR_GUARDRAILS["salida"],
        "respuestas_vacias_corregidas": CONTADOR_GUARDRAILS["vacia"],
        "ultimos": CONTADOR_GUARDRAILS["ultimos"],
    }


# ---------------------------------------------------------------------------
# Cola de mensajes con ventana de agrupacion
# ---------------------------------------------------------------------------
# En WhatsApp real una persona escribe "hola" / "necesito hora" / "con el doctor
# rojas" en tres mensajes seguidos. El agente debe responder una vez, no tres.
# Esta ventana agrupa los mensajes del mismo telefono que llegan dentro de
# VENTANA_AGRUPACION segundos y los procesa como un solo turno del agente.

VENTANA_AGRUPACION = float(os.getenv("VENTANA_AGRUPACION", "5"))


class _Grupo:
    """Mensajes de un mismo telefono esperando procesarse en un solo turno."""

    __slots__ = (
        "textos", "sesion", "historial", "lote", "evento",
        "respuesta", "herramientas", "error", "timer",
    )

    def __init__(self, sesion, historial):
        self.textos = []
        self.sesion = sesion
        self.historial = historial
        self.lote = uuid4().hex[:8]
        self.evento = threading.Event()
        self.respuesta = None
        self.herramientas = []
        self.error = None
        self.timer = None


_GRUPOS = {}
_GRUPOS_LOCK = threading.Lock()


def _cerrar_grupo(telefono, grupo):
    """Procesa el lote una sola vez, cuando pasa la ventana sin mensajes nuevos."""
    with _GRUPOS_LOCK:
        if _GRUPOS.get(telefono) is grupo:
            del _GRUPOS[telefono]
    try:
        grupo.respuesta, grupo.herramientas = _procesar_turno(
            telefono, grupo.textos, grupo.sesion, grupo.historial
        )
    except Exception as error:  # noqa: BLE001
        grupo.error = error
    finally:
        grupo.evento.set()


def _agrupar(telefono, texto, sesion, historial):
    """Anade el mensaje al grupo del telefono y reinicia la ventana."""
    with _GRUPOS_LOCK:
        grupo = _GRUPOS.get(telefono)
        if grupo is None:
            grupo = _Grupo(sesion, historial)
            _GRUPOS[telefono] = grupo
        grupo.textos.append(texto)
        if grupo.timer is not None:
            grupo.timer.cancel()
        temporizador = threading.Timer(
            VENTANA_AGRUPACION, _cerrar_grupo, args=(telefono, grupo)
        )
        temporizador.daemon = True
        grupo.timer = temporizador
        temporizador.start()
    return grupo


@app.post("/api/chat")
def conversar(datos: MensajeChat):
    if not datos.mensaje.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    # Sin telefono explicito se genera uno nuevo por turno: con un valor fijo,
    # todas las pruebas compartian la misma ficha y chocaban por RUT.
    telefono = datos.telefono or f"+569{uuid4().int % 90000000 + 10000000}"
    sesion = datos.sesion or uuid4().hex[:12]

    # Guardrail de entrada: no se gasta una llamada al modelo si es manipulacion.
    if guardrail_entrada(datos.mensaje):
        return {
            "respuesta": RESPUESTA_GUARDRAIL,
            "sesion": sesion,
            "herramientas": [],
            "lote": None,
            "agrupados": 1,
        }

    grupo = _agrupar(telefono, datos.mensaje.strip(), sesion, list(datos.historial))

    # El request espera a que la ventana cierre y el lote se procese: el cliente
    # recibe la respuesta sin cambiar la forma de llamar a la API.
    if not grupo.evento.wait(timeout=180):
        raise HTTPException(status_code=504, detail="El turno no se proceso a tiempo")
    if grupo.error is not None:
        registro.exception("Fallo al procesar el turno de %s: %s", telefono, grupo.error)
        print("[ERROR MEDIFLOW AI]", type(grupo.error).__name__, grupo.error, flush=True)
        raise HTTPException(
            status_code=502, detail="No fue posible obtener respuesta del agente"
        )

    return {
        "respuesta": grupo.respuesta,
        "sesion": grupo.sesion,
        "herramientas": grupo.herramientas,
        "lote": grupo.lote,
        "agrupados": len(grupo.textos),
    }


def _procesar_turno(telefono, textos, sesion, historial):
    """Llama al agente una sola vez con todos los mensajes del lote."""
    mensajes = []
    for item in historial[-20:]:
        rol = item.get("role")
        contenido = item.get("content", "")
        if rol == "user":
            mensajes.append(HumanMessage(content=contenido))
        elif rol == "assistant":
            mensajes.append(AIMessage(content=contenido))

    texto = "\n".join(textos)
    mensajes.append(HumanMessage(content=texto))

    # La identidad del paciente queda fijada aqui: el modelo no puede cambiarla.
    token = TELEFONO_ACTUAL.set(telefono)
    try:
        resultado = agente.invoke(
            {"messages": mensajes},
            config={"recursion_limit": 14},
        )
        respuesta = guardrail_salida(resultado["messages"][-1].content)

        herramientas = [
            mensaje.name
            for mensaje in resultado["messages"]
            if getattr(mensaje, "type", "") == "tool"
        ]

        with obtener_conexion() as conexion:
            conexion.execute(
                """
                INSERT INTO conversaciones (telefono, sesion, rol, contenido)
                VALUES (%s, %s, 'user', %s), (%s, %s, 'assistant', %s)
                """,
                (telefono, sesion, texto, telefono, sesion, respuesta),
            )
            conexion.commit()
    finally:
        TELEFONO_ACTUAL.reset(token)

    return respuesta, herramientas


# ---------------------------------------------------------------------------
# API de negocio: citas
# ---------------------------------------------------------------------------


@app.get("/")
def inicio():
    return {
        "mensaje": "Bienvenido a MediFlow AI",
        "estado": "funcionando",
        "demo_whatsapp": "/demo",
        "crm": "/crm",
    }


@app.get("/api/health")
def health():
    try:
        with obtener_conexion() as conexion:
            conexion.execute("SELECT 1")
        return {"api": "online", "database": "connected"}
    except psycopg.Error as error:
        raise HTTPException(
            status_code=503, detail="Base de datos no disponible"
        ) from error


@app.post("/api/citas")
def crear_cita(datos: NuevaCita):
    if not (datos.email or datos.telefono):
        raise HTTPException(
            status_code=400,
            detail="Se requiere correo o teléfono de contacto",
        )

    try:
        with obtener_conexion() as conexion:
            cita = reservar_cita(
                conexion,
                horario_id=datos.horario_id,
                nombre=datos.nombre,
                email=datos.email,
                telefono=datos.telefono,
                rut=datos.rut,
                idempotency_key=uuid4(),
            )
            conexion.execute(
                "UPDATE citas SET canal = %s WHERE id = %s",
                (datos.canal if datos.canal in ("agente", "whatsapp", "web", "recepcion") else "web", cita["id"]),
            )
            conexion.commit()
    except HorarioNoDisponible as error:
        raise HTTPException(
            status_code=409, detail="El horario ya no está disponible"
        ) from error
    except ClaveIdempotenciaEnConflicto as error:
        raise HTTPException(status_code=409, detail="Solicitud duplicada") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"ok": True, "cita": cita}


@app.get("/api/citas")
def obtener_citas(
    estado: str | None = None,
    medico_id: int | None = Query(default=None, gt=0),
    desde: date | None = None,
    hasta: date | None = None,
    q: str | None = None,
    limite: int = Query(default=200, ge=1, le=500),
):
    try:
        with obtener_conexion() as conexion:
            return listar_citas(
                conexion,
                estado=estado,
                medico_id=medico_id,
                desde=desde,
                hasta=hasta,
                busqueda=q,
                limite=limite,
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/citas/{cita_id}/cancelar")
def cancelar(cita_id: int, datos: Cancelacion | None = None):
    datos = datos or Cancelacion()
    try:
        with obtener_conexion() as conexion:
            paciente = obtener_paciente_por_telefono(conexion, datos.telefono)
            if not paciente and not datos.telefono:
                # Acción de recepción: el dueño se resuelve desde la propia cita.
                fila = conexion.execute(
                    "SELECT paciente_id FROM citas WHERE id = %s", (cita_id,)
                ).fetchone()
                paciente = {"id": fila["paciente_id"]} if fila else None
            if not paciente:
                raise HTTPException(status_code=404, detail="Paciente no encontrado")

            cita = cancelar_cita(
                conexion,
                cita_id=cita_id,
                paciente_id=paciente["id"],
            )
            conexion.commit()
            return {"ok": True, "cita": cita}
    except CitaNoEncontrada as error:
        raise HTTPException(
            status_code=404, detail="La cita no existe o no está activa"
        ) from error


@app.post("/api/citas/{cita_id}/reagendar")
def reagendar(cita_id: int, datos: Reagendamiento):
    try:
        with obtener_conexion() as conexion:
            paciente = obtener_paciente_por_telefono(conexion, datos.telefono)
            if not paciente and not datos.telefono:
                fila = conexion.execute(
                    "SELECT paciente_id FROM citas WHERE id = %s", (cita_id,)
                ).fetchone()
                paciente = {"id": fila["paciente_id"]} if fila else None
            if not paciente:
                raise HTTPException(status_code=404, detail="Paciente no encontrado")

            cita = reagendar_cita(
                conexion,
                cita_id=cita_id,
                paciente_id=paciente["id"],
                nuevo_horario_id=datos.nuevo_horario_id,
            )
            conexion.commit()
            return {"ok": True, "cita": cita}
    except (HorarioNoDisponible, CitaNoEncontrada) as error:
        raise HTTPException(
            status_code=409, detail="La cita o el horario ya no están disponibles"
        ) from error


@app.get("/api/pacientes")
def listar_pacientes(q: str | None = None):
    with obtener_conexion() as conexion:
        return conexion.execute(
            """
            SELECT
                p.id, p.nombre, p.rut, p.email, p.telefono, p.verificado,
                count(c.id) FILTER (WHERE c.estado = 'confirmada') AS citas_activas,
                count(c.id) AS citas_total,
                max(c.creada_en) AS ultima_reserva
            FROM pacientes p
            LEFT JOIN citas c ON c.paciente_id = p.id
            WHERE (%(q)s::text IS NULL
                   OR p.nombre ILIKE '%%' || %(q)s || '%%'
                   OR COALESCE(p.rut, '') ILIKE '%%' || %(q)s || '%%'
                   OR COALESCE(p.email, '') ILIKE '%%' || %(q)s || '%%'
                   OR COALESCE(p.telefono, '') ILIKE '%%' || %(q)s || '%%')
            GROUP BY p.id
            ORDER BY p.nombre
            """,
            {"q": q},
        ).fetchall()


@app.get("/api/pacientes/{paciente_id}/citas")
def citas_paciente(paciente_id: int, solo_activas: bool = False):
    with obtener_conexion() as conexion:
        return citas_del_paciente(
            conexion,
            paciente_id=paciente_id,
            solo_activas=solo_activas,
        )


# ---------------------------------------------------------------------------
# Especialidades, médicos y horarios
# ---------------------------------------------------------------------------


@app.get("/api/especialidades")
def listar_especialidades():
    with obtener_conexion() as conexion:
        return conexion.execute(
            "SELECT id, nombre FROM especialidades ORDER BY nombre"
        ).fetchall()


@app.get("/api/medicos")
def listar_medicos(especialidad_id: int | None = Query(default=None, gt=0)):
    with obtener_conexion() as conexion:
        return conexion.execute(
            """
            SELECT m.id, m.nombre, e.id AS especialidad_id, e.nombre AS especialidad
            FROM medicos m
            JOIN especialidades e ON e.id = m.especialidad_id
            WHERE m.activo = TRUE
              AND (%(especialidad_id)s::integer IS NULL
                   OR m.especialidad_id = %(especialidad_id)s)
            ORDER BY m.nombre
            """,
            {"especialidad_id": especialidad_id},
        ).fetchall()


@app.get("/api/horarios")
def listar_horarios(
    medico_id: int | None = Query(default=None, gt=0),
    especialidad_id: int | None = Query(default=None, gt=0),
    desde: date | None = None,
    hasta: date | None = None,
    limite: int = Query(default=50, ge=1, le=200),
):
    if desde and hasta and hasta < desde:
        raise HTTPException(
            status_code=400,
            detail="La fecha final no puede ser anterior a la inicial",
        )

    with obtener_conexion() as conexion:
        return consultar_horarios(
            conexion,
            medico_id=medico_id,
            especialidad_id=especialidad_id,
            desde=desde,
            hasta=hasta,
            limite=limite,
        )


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------


@app.get("/api/crm/resumen")
def crm_resumen():
    with obtener_conexion() as conexion:
        resumen = resumen_crm(conexion)
        resumen["agenda"] = agenda_por_medico(conexion)
        return resumen


@app.get("/api/agenda")
def agenda(
    medico_id: int = Query(gt=0),
    fecha: date | None = None,
):
    """Agenda de un médico para un día (por defecto, hoy en Chile)."""
    if fecha is None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fecha = datetime.now(ZoneInfo("America/Santiago")).date()

    with obtener_conexion() as conexion:
        return agenda_del_dia(conexion, medico_id=medico_id, fecha=fecha)


@app.post("/api/citas/{cita_id}/completar")
def completar(cita_id: int):
    with obtener_conexion() as conexion:
        cita = completar_cita(conexion, cita_id=cita_id)
        conexion.commit()

    if not cita:
        raise HTTPException(
            status_code=404,
            detail="La cita no existe o no está confirmada",
        )
    return {"ok": True, "cita": cita}


@app.get("/api/conversaciones")
def conversaciones(limite: int = Query(default=40, ge=1, le=200)):
    with obtener_conexion() as conexion:
        return conversaciones_recientes(conexion, limite=limite)


# ---------------------------------------------------------------------------
# Simulador de WhatsApp y CRM (páginas estáticas servidas por la misma API)
# ---------------------------------------------------------------------------


@app.get("/demo")
def demo_whatsapp():
    return FileResponse(ESTATICOS / "demo.html")


@app.get("/crm")
def crm():
    return FileResponse(ESTATICOS / "crm.html")


# El frontend React compilado se sirve desde la misma API: un solo puerto, sin CORS.
DIST = RAIZ / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/app", StaticFiles(directory=DIST, html=True), name="frontend")


@app.middleware("http")
async def sin_cache_en_html(request, call_next):
    """Evita que el navegador guarde una versión vieja del simulador o del CRM."""
    respuesta = await call_next(request)
    ruta = request.url.path
    if ruta in ("/", "/crm", "/demo") or ruta.startswith("/app"):
        if respuesta.headers.get("content-type", "").startswith("text/html"):
            respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return respuesta


@app.get("/")
def raiz():
    return RedirectResponse(url="/app" if DIST.is_dir() else "/crm")
