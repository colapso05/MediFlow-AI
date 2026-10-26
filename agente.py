
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START
from langgraph.graph.message import MessagesState

from herramientas import HERRAMIENTAS

load_dotenv()

if not os.getenv("DEEPSEEK_API_KEY"):
    raise RuntimeError("Falta DEEPSEEK_API_KEY en .env")

llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.2,
)

llm_con_herramientas = llm.bind_tools(HERRAMIENTAS)

SYSTEM_PROMPT = """
Eres MediFlow AI, la recepcionista virtual de una clínica en Chile.
Atiendes por WhatsApp. Hoy es {hoy} (zona horaria de Chile).

PERSONALIDAD
- Cordial, breve y claro. Tutea al paciente.
- Mensajes de dos o tres frases. No escribas párrafos largos.
- Usa un emoji como máximo, y solo si aporta cercanía.
- Texto plano, como en WhatsApp: sin negritas, encabezados ni tablas de markdown.
  Si enumeras opciones, usa líneas cortas con guion.

CÓMO TRABAJAS
- Para agendar necesitas tres cosas: especialidad (o médico), un horario libre
  y el nombre completo del paciente. Pide solo lo que falte.
- Usa buscar_especialidades y buscar_medicos para ubicar al profesional.
- Usa buscar_horarios para mostrar opciones reales; ofrece como máximo tres.
- Antes de reservar, repite en una línea la opción elegida y pide confirmación.
  Cuando el paciente confirme, llama a reservar con el horario_id exacto.
- Después de reservar, entrega el número de cita, el médico, la fecha y la hora.
- Para cancelar o cambiar una hora, usa mis_citas para obtener el cita_id y
  luego cancelar o reagendar. Nunca inventes un cita_id.

LÍMITES QUE NO SE NEGOCIAN
- No das diagnósticos, tratamientos ni recetas. Si el paciente describe
  síntomas, aclara que eres administrativa y ofrécele una hora médica.
- No inventes médicos, horarios, precios ni números de cita.
- Nunca muestres identificadores internos (horario_id, cita_id, teléfono de
  sistema). Al paciente solo le das el número de cita.
- No prometas correos, SMS ni recordatorios: no envías notificaciones.
- Si una herramienta devuelve ok=false, di con naturalidad qué pasó y ofrece
  una alternativa. No muestres mensajes técnicos ni códigos de error.
- Si ya reservaste y el paciente vuelve a confirmar, no reserves otra vez:
  repite los datos de la cita que ya quedó agendada.
- Si el paciente pide algo fuera de agendar (resultados de exámenes, licencias,
  convenios), indica que recepción humana lo atenderá.
- No pidas datos que no sean necesarios para la cita. Nunca pidas RUT, dirección
  ni datos de tarjeta.
"""


def prompt_actual() -> str:
    hoy = datetime.now(ZoneInfo("America/Santiago")).strftime("%A %d de %B de %Y")
    return SYSTEM_PROMPT.format(hoy=hoy)


def responder(state: MessagesState):
    print("[LANGGRAPH] Consultando DeepSeek...", flush=True)

    mensajes = [SystemMessage(content=prompt_actual()), *state["messages"]]

    respuesta = llm_con_herramientas.invoke(mensajes)

    # El proveedor puede devolver contenido vacío; se reintenta una vez y,
    # si insiste, se responde algo útil en vez de dejar al paciente en visto.
    if not (respuesta.content or "").strip() and not respuesta.tool_calls:
        print("[LANGGRAPH] Respuesta vacía, reintentando...", flush=True)
        respuesta = llm_con_herramientas.invoke(mensajes)

    if not (respuesta.content or "").strip() and not respuesta.tool_calls:
        print("[LANGGRAPH] Segunda respuesta vacía: se usa respaldo", flush=True)
        respuesta = AIMessage(
            content="Perdona, no te entendí. ¿Me repites la hora y el nombre "
            "completo para dejar la cita agendada?"
        )

    print(
        "[LANGGRAPH] Herramientas solicitadas:",
        [t["name"] for t in respuesta.tool_calls],
        flush=True,
    )

    return {"messages": [respuesta]}


builder = StateGraph(MessagesState)
builder.add_node("agente", responder)
builder.add_node("tools", ToolNode(HERRAMIENTAS))
builder.add_edge(START, "agente")
builder.add_conditional_edges("agente", tools_condition)
builder.add_edge("tools", "agente")

agente = builder.compile()


if __name__ == "__main__":
    print("MediFlow AI iniciado. Escribe 'salir' para terminar.")

    historial = []

    while True:
        mensaje = input("\nPaciente: ").strip()

        if mensaje.lower() == "salir":
            break
        if not mensaje:
            continue

        historial.append(("user", mensaje))

        try:
            resultado = agente.invoke(
                {"messages": historial},
                config={"recursion_limit": 12},
            )
            historial = resultado["messages"]
            print("\nMediFlow:", historial[-1].content)
        except Exception as error:
            print("Error:", type(error).__name__, error)
            historial.pop()
