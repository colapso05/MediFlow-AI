
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

    // Solo role y content: el backend valida el historial como texto y rechaza
    // campos extra como `herramientas` (devolvía 422 en el segundo mensaje).
    const historial = mensajes
      .slice(-20)
      .map(({ role, content }) => ({ role, content }));

    setMensajes((prev) => [
      ...prev,
      { role: "user", content: mensaje },
    ]);

    setTexto("");
    setCargando(true);
    let ultimoError = null;

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

      // La API puede estar arrancando (tarda ~10 s en cargar el agente) o haberse
      // reiniciado: se reintenta con espera progresiva antes de declarar el fallo.
      let respuesta = null;
      const esperas = [1500, 3000, 5000];

      for (let intento = 0; intento <= esperas.length; intento++) {
        try {
          respuesta = await pedir();
          if (respuesta.ok) break;
          if (respuesta.status === 502 && intento < esperas.length) {
            await new Promise((r) => setTimeout(r, esperas[intento]));
            continue;
          }
          throw new Error(`Error HTTP ${respuesta.status}`);
        } catch (red) {
          ultimoError = red;
          if (intento >= esperas.length) throw red;
          await new Promise((r) => setTimeout(r, esperas[intento]));
        }
      }

      if (!respuesta || !respuesta.ok) {
        throw new Error(`Error HTTP ${respuesta ? respuesta.status : "sin respuesta"}`);
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
      console.error(ultimoError || error);

      const esHttp = String(error.message || "").startsWith("Error HTTP");
      const pista = window.location.protocol === "file:"
        ? "Estás abriendo el archivo directo (file://). Entra por http://127.0.0.1:8000/app"
        : esHttp
          ? `El servidor respondió ${error.message.replace("Error HTTP ", "")} en ${window.location.origin}/api/chat`
          : `No hubo respuesta de ${window.location.origin}/api/chat tras varios intentos. Revisa que la ventana "MediFlow API" siga abierta.`;

      setMensajes((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `No pude conectar con el servidor. ${pista}`,
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
