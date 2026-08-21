"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErrorApi } from "@/lib/api";

type EstadoEnvio =
  | { tipo: "idle" }
  | { tipo: "enviando" }
  | { tipo: "ok"; mensaje: string }
  | { tipo: "error"; mensaje: string };

/**
 * Command bar global (Ctrl+K / Cmd+K): entrada de texto en lenguaje natural
 * que se envía a POST /api/ingest/receipt, con botón de foto del ticket
 * (multipart) y placeholder para dictado por voz.
 */
export function BarraComandos() {
  const [abierta, setAbierta] = useState(false);
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<EstadoEnvio>({ tipo: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);
  const inputFotoRef = useRef<HTMLInputElement>(null);

  // Atajo global Ctrl+K / Cmd+K para abrir la command bar.
  useEffect(() => {
    const alTeclear = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        setAbierta((v) => !v);
      }
      if (ev.key === "Escape") setAbierta(false);
    };
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, []);

  useEffect(() => {
    if (abierta) {
      setEstado({ tipo: "idle" });
      // Pequeño retraso para que el modal termine de montarse.
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [abierta]);

  const enviarTexto = useCallback(async () => {
    const limpio = texto.trim();
    if (!limpio) return;
    setEstado({ tipo: "enviando" });
    try {
      await api.ingerirTicketTexto(limpio);
      setEstado({ tipo: "ok", mensaje: "Ticket registrado en el vault" });
      setTexto("");
    } catch (err) {
      setEstado({
        tipo: "error",
        mensaje:
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "No se pudo conectar con la API",
      });
    }
  }, [texto]);

  const enviarFoto = useCallback(
    async (archivo: File | undefined) => {
      if (!archivo) return;
      setEstado({ tipo: "enviando" });
      try {
        await api.ingerirTicketImagen(archivo);
        setEstado({ tipo: "ok", mensaje: "Foto del ticket procesada" });
      } catch (err) {
        setEstado({
          tipo: "error",
          mensaje:
            err instanceof ErrorApi
              ? `Error ${err.status}: ${err.message}`
              : "No se pudo subir la foto",
        });
      }
    },
    [],
  );

  if (!abierta) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command bar"
      className="fixed inset-0 z-50 flex items-start justify-center
        bg-carbon-950/50 p-4 pt-[15vh] backdrop-blur-sm"
      onClick={() => setAbierta(false)}
    >
      <div
        className="tarjeta-bento w-full max-w-lg"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={texto}
            onChange={(ev) => setTexto(ev.target.value)}
            onKeyDown={(ev) => ev.key === "Enter" && enviarTexto()}
            placeholder="Escribe, dicta (próximamente) o sube foto del ticket…"
            aria-label="Entrada en lenguaje natural"
            className="min-h-11 flex-1 rounded-xl border border-arena-200
              bg-arena-50 px-3 text-base outline-none
              focus:border-emerald-500 dark:border-carbon-800
              dark:bg-carbon-800 dark:placeholder:text-arena-100/40"
          />
          {/* Placeholder de voz: la Web Speech API se integrará después. */}
          <button
            type="button"
            disabled
            title="Dictado por voz (próximamente)"
            aria-label="Dictado por voz, próximamente"
            className="boton-secundario"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
              <rect x={9} y={2} width={6} height={12} rx={3} />
              <path strokeLinecap="round" d="M5 10a7 7 0 0 0 14 0M12 19v3" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => inputFotoRef.current?.click()}
            title="Subir foto del ticket"
            aria-label="Subir foto del ticket"
            className="boton-secundario"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 8a2 2 0 0 1 2-2h1.2a1 1 0 0 0 .9-.55l.8-1.6A1 1 0 0 1 8.8 3h6.4a1 1 0 0 1 .9.55l.8 1.6a1 1 0 0 0 .9.55H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
              <circle cx={12} cy={13} r={3.5} />
            </svg>
          </button>
          <input
            ref={inputFotoRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(ev) => {
              enviarFoto(ev.target.files?.[0]);
              ev.target.value = "";
            }}
          />
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <p className="text-xs text-carbon-950/50 dark:text-arena-100/50">
            Ctrl+K para abrir/cerrar · Enter para enviar · Esc para salir
          </p>
          <button
            type="button"
            onClick={enviarTexto}
            disabled={estado.tipo === "enviando" || !texto.trim()}
            className="boton-primario"
          >
            {estado.tipo === "enviando" ? "Enviando…" : "Enviar"}
          </button>
        </div>
        {estado.tipo === "ok" && (
          <p className="mt-2 text-sm text-emerald-600 dark:text-emerald-400">
            {estado.mensaje}
          </p>
        )}
        {estado.tipo === "error" && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">
            {estado.mensaje}
          </p>
        )}
      </div>
    </div>
  );
}
