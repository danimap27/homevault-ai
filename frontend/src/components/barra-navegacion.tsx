"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Barcode,
  BookOpen,
  CalendarDays,
  CheckSquare,
  FolderOpen,
  Home,
  Refrigerator,
  ShoppingCart,
} from "lucide-react";

const ENLACES = [
  { href: "/", etiqueta: "Inicio", icono: Home },
  { href: "/inventario", etiqueta: "Inventario", icono: Refrigerator },
  { href: "/categorias", etiqueta: "Categorías", icono: FolderOpen },
  { href: "/recetas", etiqueta: "Recetas", icono: BookOpen },
  { href: "/planificador", etiqueta: "Menú", icono: CalendarDays },
  { href: "/tareas", etiqueta: "Tareas", icono: CheckSquare },
  { href: "/lista-compra", etiqueta: "Compra", icono: ShoppingCart },
  { href: "/barcodes", etiqueta: "Barcodes", icono: Barcode },
] as const;

export function BarraNavegacion() {
  const ruta = usePathname();

  if (ruta === "/perfiles") return null;

  return (
    <nav
      aria-label="Navegación principal"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800/60 bg-slate-950/80 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl"
    >
      <div className="mx-auto flex max-w-5xl items-stretch justify-around px-2">
        {ENLACES.map(({ href, etiqueta, icono: Icono }) => {
          const activo = href === "/" ? ruta === "/" : ruta.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={activo ? "page" : undefined}
              className={`group relative flex min-h-16 flex-1 flex-col items-center justify-center gap-1 text-xs font-medium transition-colors ${
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
  );
}
