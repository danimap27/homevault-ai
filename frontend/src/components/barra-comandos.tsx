"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Mic, Send, Store } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Supermercado } from "@/lib/types";

type EstadoEnvio =
  | { tipo: "idle" }
  | { tipo: "enviando" }
  | { tipo: "ok"; mensaje: string }
  | { tipo: "error"; mensaje: string };

const SUPER_AUTO = "";

export function BarraComandos() {
  const [abierta, setAbierta] = useState(false);
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<EstadoEnvio>({ tipo: "idle" });
  const [supermercados, setSupermercados] = useState<Supermercado[]>([]);
  const [supermercado, setSupermercado] = useState<string>(SUPER_AUTO);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputFotoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const alTeclear = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        setAbierta((v) => !v);
      }
      if (ev.key === "Escape") setAbierta(false);
    };
    // La UI (botón «Añadir») también puede abrir la barra en móvil.
    const alAbrirDesdeUI = () => setAbierta(true);
    window.addEventListener("keydown", alTeclear);
    window.addEventListener("hv:comandos", alAbrirDesdeUI);
    return () => {
      window.removeEventListener("keydown", alTeclear);
      window.removeEventListener("hv:comandos", alAbrirDesdeUI);
    };
  }, []);

  useEffect(() => {
    if (abierta) {
      setEstado({ tipo: "idle" });
      setTexto("");
      setSupermercado(SUPER_AUTO);
      setTimeout(() => inputRef.current?.focus(), 50);
      api.getSupermercados().then((lista) => {
        setSupermercados(lista);
        const predeterminado = lista.find((s) => s.predeterminado);
        if (predeterminado) setSupermercado(predeterminado.id);
      });
    }
  }, [abierta]);

  const enviarTexto = useCallback(async () => {
    const limpio = texto.trim();
    if (!limpio) return;
    setEstado({ tipo: "enviando" });
    try {
      await api.ingerirTicketTexto(
        limpio,
        undefined,
        undefined,
        supermercado || undefined,
      );
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
  }, [texto, supermercado]);

  const enviarFoto = useCallback(
    async (archivo: File | undefined) => {
      if (!archivo) return;
      setEstado({ tipo: "enviando" });
      try {
        await api.ingerirTicketImagen(archivo, supermercado || undefined);
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
    [supermercado],
  );

  if (!abierta) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command bar"
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/70 p-4 pt-[15vh] backdrop-blur-sm"
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
            className="input-premium min-h-11 flex-1"
          />
          <button
            type="button"
            disabled
            title="Dictado por voz (próximamente)"
            aria-label="Dictado por voz, próximamente"
            className="boton-secundario"
          >
            <Mic className="size-5" />
          </button>
          <button
            type="button"
            onClick={() => inputFotoRef.current?.click()}
            title="Subir foto del ticket"
            aria-label="Subir foto del ticket"
            className="boton-secundario"
          >
            <Camera className="size-5" />
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

        <div className="mt-3 flex items-center gap-2">
          <Store className="size-4 text-slate-500" />
          <select
            value={supermercado}
            onChange={(ev) => setSupermercado(ev.target.value)}
            aria-label="Supermercado del ticket"
            className="input-premium max-w-[14rem] text-sm"
          >
            <option value={SUPER_AUTO}>Detectar automáticamente</option>
            {supermercados.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nombre}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <p className="text-xs text-slate-500">
            Ctrl+K para abrir/cerrar · Enter para enviar · Esc para salir
          </p>
          <button
            type="button"
            onClick={enviarTexto}
            disabled={estado.tipo === "enviando" || !texto.trim()}
            className="boton-primario"
          >
            {estado.tipo === "enviando" ? (
              "Enviando…"
            ) : (
              <Send className="size-4" />
            )}
          </button>
        </div>
        {estado.tipo === "ok" && (
          <p className="mt-2 text-sm text-emerald-400">{estado.mensaje}</p>
        )}
        {estado.tipo === "error" && (
          <p className="mt-2 text-sm text-rose-400">{estado.mensaje}</p>
        )}
      </div>
    </div>
  );
}
