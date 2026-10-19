
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START
from langgraph.graph.message import MessagesState

from herramientas import HERRAMIENTAS

load_dotenv()

if not os.getenv("DEEPSEEK_API_KEY"):
    raise RuntimeError(
        "Falta DEEPSEEK_API_KEY en .env"
    )

llm = ChatOpenAI(
    model=os.getenv(
        "DEEPSEEK_MODEL",
        "deepseek-flash"
    ),
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com"
    ),
    temperature=0.3,
)

llm_con_herramientas = llm.bind_tools(HERRAMIENTAS)

SYSTEM_PROMPT = """
Eres MediFlow AI, asistente administrativo de
una clínica ficticia en Chile.

REGLAS:
- Responde de forma amable y profesional.
- Para consultar especialidades utiliza
  buscar_especialidades.
- Para consultar médicos utiliza buscar_medicos.
- Nunca inventes nombres de médicos.
- Nunca inventes horarios disponibles.
- No confirmes reservas sin una herramienta
  que realmente las registre.
- Si una herramienta falla, informa que no
  puedes verificar los datos en ese momento.
- No entregues diagnósticos ni prescripciones.
- Solicita solamente los datos personales
  necesarios para la gestión administrativa.
"""


def responder(state: MessagesState):
    print(
        "[LANGGRAPH] Consultando DeepSeek...",
        flush=True
    )

    mensajes = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"]
    ]

    respuesta = llm_con_herramientas.invoke(mensajes)

    print(
        "[LANGGRAPH] Respuesta recibida",
        flush=True
    )

    print(
        "[LANGGRAPH] Herramientas solicitadas:",
        [t["name"] for t in respuesta.tool_calls],
        flush=True
    )

    return {"messages": [respuesta]}


builder = StateGraph(MessagesState)

builder.add_node("agente", responder)
builder.add_node(
    "tools",
    ToolNode(HERRAMIENTAS)
)

builder.add_edge(START, "agente")

builder.add_conditional_edges(
    "agente",
    tools_condition
)

builder.add_edge(
    "tools",
    "agente"
)

agente = builder.compile()


if __name__ == "__main__":
    print("MediFlow AI iniciado.")
    print("Escribe 'salir' para terminar.")

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
                config={"recursion_limit": 12}
            )

            historial = resultado["messages"]

            print(
                "\nMediFlow:",
                historial[-1].content
            )

        except Exception as error:
            print("Error:", error)
            historial.pop()
