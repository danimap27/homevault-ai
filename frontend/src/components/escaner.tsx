"use client";

import { useEffect, useRef, useState } from "react";
import type { Html5Qrcode } from "html5-qrcode";

/**
 * Escáner de códigos de barras/EAN con la cámara usando html5-qrcode.
 * Se importa de forma perezosa (solo en cliente y al abrir el modal) para
 * no romper el SSR ni inflar el bundle inicial.
 */
export function Escaner({
  alDetectar,
  alCerrar,
}: {
  alDetectar: (codigo: string) => void;
  alCerrar: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const contenedorRef = useRef<HTMLDivElement>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  useEffect(() => {
    let cancelado = false;

    async function iniciar() {
      try {
        const { Html5Qrcode } = await import("html5-qrcode");
        if (cancelado || !contenedorRef.current) return;
        const scanner = new Html5Qrcode("qr-reader");
        scannerRef.current = scanner;
        await scanner.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 250, height: 150 } },
          (codigo) => {
            alDetectar(codigo);
          },
          () => {
            // Fallos de decodificación por frame: se ignoran.
          },
        );
      } catch {
        if (!cancelado) {
          setError("No se pudo acceder a la cámara (¿permiso denegado?)");
        }
      }
    }
    iniciar();

    return () => {
      cancelado = true;
      scannerRef.current
        ?.stop()
        .catch(() => {})
        .finally(() => scannerRef.current?.clear());
    };
  }, [alDetectar]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Escáner de código de barras"
      className="fixed inset-0 z-50 flex items-center justify-center
        bg-carbon-950/70 p-4 backdrop-blur-sm"
      onClick={alCerrar}
    >
      <div
        className="tarjeta-bento w-full max-w-md"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Escanear código</h2>
          <button
            type="button"
            onClick={alCerrar}
            aria-label="Cerrar escáner"
            className="boton-secundario"
          >
            Cerrar
          </button>
        </div>
        <div ref={contenedorRef} id="qr-reader" className="w-full" />
        {error && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}
        <p className="mt-2 text-xs text-carbon-950/50 dark:text-arena-100/50">
          Apunta la cámara al código de barras del producto.
        </p>
      </div>
    </div>
  );
}
