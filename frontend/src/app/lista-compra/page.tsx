"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import type { EntradaListaCompra } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

const CATEGORIA_GENERAL = "general";

/**
 * Lista de la compra agrupada por categoría/pasillo, con checkboxes
 * (POST /api/shopping-list/check), exportación (Web Share API /
 * portapapeles / descarga) e impresión térmica (POST /api/print/receipt-list)
 * con fallback a window.print().
 */
export default function ListaCompraPage() {
  const [entradas, setEntradas] = useState<EntradaListaCompra[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(() => {
    setError(null);
    api
      .getListaCompra()
      .then(setEntradas)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  useEffect(cargar, [cargar]);

  const porCategoria = useMemo(() => {
    const grupos = new Map<string, EntradaListaCompra[]>();
    for (const entrada of entradas ?? []) {
      const clave = entrada.categoria ?? CATEGORIA_GENERAL;
      grupos.set(clave, [...(grupos.get(clave) ?? []), entrada]);
    }
    return Array.from(grupos.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [entradas]);

  const alternar = async (entrada: EntradaListaCompra) => {
    // Actualización optimista: se deshace si la API falla.
    setEntradas(
      (prev) =>
        prev?.map((e) =>
          e.item_id === entrada.item_id ? { ...e, comprado: !e.comprado } : e,
        ) ?? null,
    );
    try {
      await api.checkEntradaLista(entrada.item_id);
    } catch (err) {
      setEntradas(
        (prev) =>
          prev?.map((e) =>
            e.item_id === entrada.item_id ? { ...e, comprado: entrada.comprado } : e,
          ) ?? null,
      );
      setAviso(
        err instanceof ErrorApi && err.status === 404
          ? "La entrada ya no está pendiente en la lista"
          : "No se pudo marcar la entrada",
      );
    }
  };

  const textoLista = () =>
    porCategoria
      .map(([categoria, items]) => {
        const lineas = items.map(
          (e) =>
            `${e.comprado ? "[x]" : "[ ]"} ${e.nombre}` +
            (e.cantidad
              ? ` (${e.cantidad}${e.unidad ? ` ${e.unidad}` : ""})`
              : ""),
        );
        return `${categoria.toUpperCase()}\n${lineas.join("\n")}`;
      })
      .join("\n\n");

  const exportar = async () => {
    const texto = textoLista();
    try {
      if (navigator.share) {
        await navigator.share({ title: "Lista de la compra", text: texto });
        return;
      }
      await navigator.clipboard.writeText(texto);
      setAviso("Lista copiada al portapapeles");
    } catch {
      // Fallback final: descarga como .txt.
      const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = "lista-compra.txt";
      enlace.click();
      URL.revokeObjectURL(url);
      setAviso("Lista descargada como lista-compra.txt");
    }
  };

  const imprimir = async () => {
    try {
      const res = await api.imprimirListaCompra();
      setAviso(`Lista enviada a la impresora (${res.lineas} líneas)`);
    } catch {
      // Impresora no configurada: impresión del navegador.
      setAviso("Impresora térmica no disponible: usando impresión del navegador");
      setTimeout(() => window.print(), 300);
    }
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-semibold">Lista de la compra</h2>
        <button type="button" onClick={exportar} className="boton-secundario">
          Exportar
        </button>
        <button type="button" onClick={imprimir} className="boton-primario">
          Imprimir
        </button>
      </div>

      {aviso && (
        <p
          className="mb-3 rounded-xl border border-emerald-300 bg-emerald-50 p-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300"
          role="status"
        >
          {aviso}
        </p>
      )}
      {error && <ErrorWidget mensaje={error} />}
      {!error && entradas === null && <Cargando />}
      {entradas !== null && entradas.length === 0 && (
        <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
          La lista está vacía.
        </p>
      )}

      {/* .solo-print: al imprimir desde el navegador solo sale esta zona */}
      <div className="solo-print space-y-4">
        {porCategoria.map(([categoria, items]) => (
          <section
            key={categoria}
            aria-label={`Pasillo ${categoria}`}
            className="tarjeta-bento"
          >
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-carbon-950/60 dark:text-arena-100/60">
              {categoria.replace(/_/g, " ")}
            </h3>
            <ul className="space-y-1">
              {items.map((entrada) => (
                <li key={entrada.item_id}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-2 hover:bg-arena-50 dark:hover:bg-carbon-800">
                    <input
                      type="checkbox"
                      checked={entrada.comprado}
                      onChange={() => alternar(entrada)}
                      className="size-6 shrink-0 accent-emerald-600"
                    />
                    <span
                      className={
                        entrada.comprado ? "line-through opacity-50" : ""
                      }
                    >
                      {entrada.nombre}
                    </span>
                    {entrada.cantidad !== null && (
                      <span className="ml-auto shrink-0 text-sm text-carbon-950/60 dark:text-arena-100/60">
                        {entrada.cantidad} {entrada.unidad ?? ""}
                      </span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
