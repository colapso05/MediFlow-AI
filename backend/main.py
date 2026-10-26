
import os
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
    historial: list[dict[str, str]] = Field(default_factory=list)
    telefono: str | None = None
    sesion: str | None = None


class NuevaCita(BaseModel):
    horario_id: int
    nombre: str
    email: str | None = None
    telefono: str | None = None
    canal: str = "web"


class Cancelacion(BaseModel):
    telefono: str | None = None


class Reagendamiento(BaseModel):
    nuevo_horario_id: int
    telefono: str | None = None


# ---------------------------------------------------------------------------
# Chat con el agente
# ---------------------------------------------------------------------------


@app.post("/api/chat")
def conversar(datos: MensajeChat):
    if not datos.mensaje.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

    mensajes = []
    for item in datos.historial[-20:]:
        rol = item.get("role")
        contenido = item.get("content", "")
        if rol == "user":
            mensajes.append(HumanMessage(content=contenido))
        elif rol == "assistant":
            mensajes.append(AIMessage(content=contenido))

    mensajes.append(HumanMessage(content=datos.mensaje))

    telefono = datos.telefono or "+56900000000"
    sesion = datos.sesion or uuid4().hex[:12]

    # La identidad del paciente queda fijada aquí: el modelo no puede cambiarla.
    token = TELEFONO_ACTUAL.set(telefono)

    try:
        resultado = agente.invoke(
            {"messages": mensajes},
            config={"recursion_limit": 14},
        )
        respuesta = resultado["messages"][-1].content
        if not (respuesta or "").strip():
            respuesta = (
                "Perdona, se me fue la respuesta. ¿Me repites lo que necesitas?"
            )

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
                (
                    telefono,
                    sesion,
                    datos.mensaje,
                    telefono,
                    sesion,
                    respuesta,
                ),
            )
            conexion.commit()

    except Exception as error:
        print("[ERROR MEDIFLOW AI]", type(error).__name__, error, flush=True)
        raise HTTPException(
            status_code=502,
            detail="No fue posible obtener respuesta del agente",
        ) from error
    finally:
        TELEFONO_ACTUAL.reset(token)

    return {
        "respuesta": respuesta,
        "sesion": sesion,
        "herramientas": herramientas,
    }


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
                p.id, p.nombre, p.email, p.telefono, p.verificado,
                count(c.id) FILTER (WHERE c.estado = 'confirmada') AS citas_activas,
                count(c.id) AS citas_total,
                max(c.creada_en) AS ultima_reserva
            FROM pacientes p
            LEFT JOIN citas c ON c.paciente_id = p.id
            WHERE (%(q)s::text IS NULL
                   OR p.nombre ILIKE '%%' || %(q)s || '%%'
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
