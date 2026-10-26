
import { useState, useRef, useEffect } from "react";
import {
  Send,
  Bot,
  MessageCircle,
  MoreVertical,
  Search,
  CheckCheck,
} from "lucide-react";
import "./App.css";

const API_URL = "";   // mismo origen: la API sirve también el frontend compilado
const TELEFONO = "+56911110009";

export default function App() {
  const [mensajes, setMensajes] = useState([
    {
      role: "assistant",
      content:
        "¡Hola! 👋 Soy MediFlow AI, el asistente administrativo de la clínica. ¿En qué puedo ayudarte hoy?",
    },
  ]);

  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const finalChat = useRef(null);

  useEffect(() => {
    finalChat.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, cargando]);

  async function enviarMensaje(e) {
    e.preventDefault();

    const mensaje = texto.trim();
    if (!mensaje || cargando) return;

    const historial = mensajes;

    setMensajes((prev) => [
      ...prev,
      { role: "user", content: mensaje },
    ]);

    setTexto("");
    setCargando(true);

    try {
      const pedir = () =>
        fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            mensaje,
            historial,
            telefono: TELEFONO,
          }),
        });

      // Si la API está arrancando o se cayó un instante, se reintenta una vez.
      let respuesta;
      try {
        respuesta = await pedir();
      } catch (red) {
        await new Promise((r) => setTimeout(r, 1500));
        respuesta = await pedir();
      }

      if (!respuesta.ok) {
        throw new Error(`Error HTTP ${respuesta.status}`);
      }

      const datos = await respuesta.json();

      setMensajes((prev) => [
        ...prev,
        {
          role: "assistant",
          content: datos.respuesta,
          herramientas: datos.herramientas || [],
        },
      ]);
    } catch (error) {
      console.error(error);

      setMensajes((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "No pude conectar con el servidor. Revisa que la ventana \"MediFlow API\" siga abierta y vuelve a intentarlo.",
        },
      ]);
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>MediFlow</h2>
          <MessageCircle size={22} />
        </div>

        <div className="search">
          <Search size={17} />
          <span>Buscar conversación</span>
        </div>

        <div className="conversation selected">
          <div className="avatar">
            <Bot size={25} />
          </div>

          <div>
            <strong>MediFlow AI</strong>
            <p>Asistente administrativo</p>
          </div>
        </div>
      </aside>

      <main className="chat">
        <header className="chat-header">
          <div className="avatar">
            <Bot size={25} />
          </div>

          <div className="chat-contact">
            <strong>MediFlow AI</strong>
            <span>Asistente virtual · {TELEFONO}</span>
          </div>

          <MoreVertical size={21} />
        </header>

        <section className="messages">
          <div className="chat-notice">
            Simulación de WhatsApp · Entorno de pruebas
          </div>

          {mensajes.map((mensaje, index) => (
            <div
              key={index}
              className={`message ${
                mensaje.role === "user" ? "outgoing" : "incoming"
              }`}
            >
              <div className="message-content">
                {mensaje.content}
                {mensaje.herramientas?.length > 0 && (
                  <span className="tools">
                    {mensaje.herramientas.map((h) => (
                      <span key={h} className="tool-chip">
                        ⚙ {h}
                      </span>
                    ))}
                  </span>
                )}
              </div>

              {mensaje.role === "user" && (
                <CheckCheck size={14} className="checks" />
              )}
            </div>
          ))}

          {cargando && (
            <div className="message incoming typing">
              MediFlow está escribiendo...
            </div>
          )}

          <div ref={finalChat} />
        </section>

        <form className="composer" onSubmit={enviarMensaje}>
          <input
            type="text"
            placeholder="Escribe un mensaje..."
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            disabled={cargando}
          />

          <button
            type="submit"
            disabled={cargando || !texto.trim()}
            aria-label="Enviar mensaje"
          >
            <Send size={20} />
          </button>
        </form>
      </main>
    </div>
  );
}
