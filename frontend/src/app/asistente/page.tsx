"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, Sparkles, User } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";

interface Mensaje {
  rol: "user" | "bot";
  texto: string;
  meta?: string;
}

const SUGERENCIAS = [
  "¿Qué se caduca esta semana?",
  "¿Qué puedo cocinar con lo que tengo?",
  "¿Qué me falta comprar?",
  "¿Cómo va el reparto de tareas de casa?",
];

/**
 * Asistente del hogar: chat con el LLM local (Ollama) alimentado con el
 * contexto real del vault (inventario, compra, tareas y plan semanal).
 */
export default function AsistentePage() {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensajes, enviando]);

  const enviar = async (pregunta: string) => {
    const limpio = pregunta.trim();
    if (!limpio || enviando) return;
    setMensajes((prev) => [
      ...prev,
      { rol: "user", texto: limpio },
      { rol: "bot", texto: "" },
    ]);
    setTexto("");
    setEnviando(true);
    setError(null);

    const actualizarUltimo = (cambio: (m: Mensaje) => Mensaje) =>
      setMensajes((prev) => {
        const copia = [...prev];
        copia[copia.length - 1] = cambio(copia[copia.length - 1]);
        return copia;
      });

    try {
      await api.chatearStream(limpio, {
        onMeta: ({ items, tareas }) =>
          actualizarUltimo((m) => ({
            ...m,
            meta: `${items} ítems · ${tareas} tareas en contexto`,
          })),
        onToken: (trozo) =>
          actualizarUltimo((m) => ({ ...m, texto: m.texto + trozo })),
      });
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "El asistente no está disponible ahora mismo",
      );
      // Retira la burbuja vacía si el fallo ocurrió antes del primer token
      setMensajes((prev) => {
        const ultimo = prev[prev.length - 1];
        return ultimo?.rol === "bot" && ultimo.texto === ""
          ? prev.slice(0, -1)
          : prev;
      });
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100dvh-9rem)] max-w-3xl flex-col">
      <header className="mb-3 flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-violet-500/15 text-violet-400">
          <Sparkles className="size-5" />
        </div>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Asistente de casa
          </h1>
          <p className="text-xs text-slate-500">
            Pregunta sobre tu inventario, compra, tareas o menú. Sin salir de
            aquí.
          </p>
        </div>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-2xl border border-slate-700/30 bg-slate-900/40 p-4 backdrop-blur">
        {mensajes.length === 0 && !enviando && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-400">
              <Bot className="size-7" />
            </div>
            <p className="max-w-sm text-sm text-slate-400">
              Hola. Conozco tu inventario, la lista de la compra, las tareas y
              el menú de la semana. ¿Qué quieres saber?
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGERENCIAS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => enviar(s)}
                  className="rounded-full border border-slate-700/50 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-violet-500/40 hover:text-violet-200"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {mensajes.map((m, indice) => (
          <div
            key={indice}
            className={`flex items-start gap-2 ${
              m.rol === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {m.rol === "bot" && (
              <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-400">
                <Bot className="size-4" />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                m.rol === "user"
                  ? "bg-emerald-600/20 text-emerald-50"
                  : "bg-slate-800/70 text-slate-200"
              }`}
            >
              {m.texto ? (
                <p className="whitespace-pre-wrap">
                  {m.texto}
                  {enviando && indice === mensajes.length - 1 && (
                    <span className="ml-0.5 inline-block animate-pulse text-violet-300">
                      ▍
                    </span>
                  )}
                </p>
              ) : (
                <p className="text-slate-400">
                  <Loader2 className="inline size-4 animate-spin" /> Pensando…
                  el modelo corre en local, puede tardar un poco
                </p>
              )}
              {m.meta && (
                <p className="mt-1.5 text-[10px] uppercase tracking-wide text-slate-500">
                  {m.meta}
                </p>
              )}
            </div>
            {m.rol === "user" && (
              <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
                <User className="size-4" />
              </div>
            )}
          </div>
        ))}

        {error && (
          <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-center text-sm text-rose-200">
            {error}
          </p>
        )}
        <div ref={finRef} />
      </div>

      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(ev) => {
          ev.preventDefault();
          enviar(texto);
        }}
      >
        <input
          value={texto}
          onChange={(ev) => setTexto(ev.target.value)}
          placeholder="Ej: ¿tengo leche? ¿qué ceno mañana?"
          className="input-premium flex-1"
          aria-label="Pregunta al asistente"
          maxLength={2000}
        />
        <button
          type="submit"
          disabled={enviando || texto.trim().length === 0}
          className="boton-primario justify-center px-4"
          aria-label="Enviar pregunta"
        >
          {enviando ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
        </button>
      </form>
    </div>
  );
}
