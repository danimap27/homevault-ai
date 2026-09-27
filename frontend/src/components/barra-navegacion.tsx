"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Barcode,
  BookOpen,
  CheckSquare,
  FolderOpen,
  Home,
  MoreHorizontal,
  Refrigerator,
  ShoppingCart,
  Sparkles,
  UtensilsCrossed,
  X,
} from "lucide-react";

/** Secciones principales: siempre visibles en la barra inferior. */
const PRINCIPALES = [
  { href: "/", etiqueta: "Inicio", icono: Home },
  { href: "/asistente", etiqueta: "Asistente", icono: Sparkles },
  { href: "/inventario", etiqueta: "Inventario", icono: Refrigerator },
  { href: "/tareas", etiqueta: "Tareas", icono: CheckSquare },
  { href: "/lista-compra", etiqueta: "Compra", icono: ShoppingCart },
] as const;

/** Secciones secundarias: en móvil viven en la hoja «Más». */
const SECUNDARIAS = [
  { href: "/categorias", etiqueta: "Categorías", icono: FolderOpen },
  { href: "/recetas", etiqueta: "Recetas", icono: BookOpen },
  { href: "/planificador", etiqueta: "Menú", icono: UtensilsCrossed },
  { href: "/barcodes", etiqueta: "Códigos", icono: Barcode },
] as const;

export function BarraNavegacion() {
  const ruta = usePathname();
  const [masAbierto, setMasAbierto] = useState(false);

  if (ruta === "/perfiles") return null;

  const esActivo = (href: string) =>
    href === "/" ? ruta === "/" : ruta.startsWith(href);
  const secundariaActiva = SECUNDARIAS.some((e) => esActivo(e.href));

  return (
    <>
      <nav
        aria-label="Navegación principal"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800/60 bg-slate-950/80 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl"
      >
        <div className="mx-auto flex max-w-5xl items-stretch justify-around px-1 sm:px-2">
          {PRINCIPALES.map(({ href, etiqueta, icono: Icono }) => {
            const activo = esActivo(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={activo ? "page" : undefined}
                className={`group relative flex min-h-16 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors min-[360px]:text-[11px] sm:text-xs ${
                  activo
                    ? "text-emerald-400"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {activo && (
                  <span className="absolute top-1.5 h-1 w-8 rounded-full bg-emerald-500/80 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                )}
                <Icono
                  className={`size-5 transition-transform duration-200 ${
                    activo ? "scale-110" : "group-hover:scale-105"
                  }`}
                />
                {etiqueta}
              </Link>
            );
          })}

          {/* Móvil: botón que abre la hoja con las secciones secundarias */}
          <button
            type="button"
            onClick={() => setMasAbierto(true)}
            aria-haspopup="dialog"
            aria-expanded={masAbierto}
            className={`group relative flex min-h-16 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors min-[360px]:text-[11px] md:hidden ${
              secundariaActiva
                ? "text-emerald-400"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {secundariaActiva && (
              <span className="absolute top-1.5 h-1 w-8 rounded-full bg-emerald-500/80 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            )}
            <MoreHorizontal className="size-5" />
            Más
          </button>

          {/* Escritorio: las secundarias van en la propia barra */}
          {SECUNDARIAS.map(({ href, etiqueta, icono: Icono }) => {
            const activo = esActivo(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={activo ? "page" : undefined}
                className={`group relative hidden min-h-16 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-xs font-medium transition-colors md:flex ${
                  activo
                    ? "text-emerald-400"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {activo && (
                  <span className="absolute top-1.5 h-1 w-8 rounded-full bg-emerald-500/80 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                )}
                <Icono
                  className={`size-5 transition-transform duration-200 ${
                    activo ? "scale-110" : "group-hover:scale-105"
                  }`}
                />
                {etiqueta}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Hoja «Más» (solo móvil) */}
      {masAbierto && (
        <div
          className="fixed inset-0 z-50 md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Más secciones"
        >
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => setMasAbierto(false)}
            className="absolute inset-0 h-full w-full bg-slate-950/70 backdrop-blur-sm"
          />
          <div className="absolute inset-x-0 bottom-0 rounded-t-3xl border-t border-slate-700/50 bg-slate-900 p-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)]">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-200">
                Más secciones
              </p>
              <button
                type="button"
                onClick={() => setMasAbierto(false)}
                aria-label="Cerrar"
                className="rounded-lg p-1.5 text-slate-400 transition-colors hover:text-slate-100"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {SECUNDARIAS.map(({ href, etiqueta, icono: Icono }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMasAbierto(false)}
                  aria-current={esActivo(href) ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-2xl border px-4 py-3.5 text-sm font-medium transition-colors ${
                    esActivo(href)
                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                      : "border-slate-700/40 bg-slate-800/40 text-slate-200 active:bg-slate-700/50"
                  }`}
                >
                  <Icono className="size-5 text-emerald-400" />
                  {etiqueta}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
