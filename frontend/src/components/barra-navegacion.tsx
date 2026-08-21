"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Barra de navegación inferior fija, optimizada para uso táctil en móvil
 * (pulgares). En pantallas grandes se mantiene abajo por consistencia PWA.
 */

const ENLACES = [
  { href: "/", etiqueta: "Inicio", icono: IconoCasa },
  { href: "/inventario", etiqueta: "Inventario", icono: IconoCaja },
  { href: "/planificador", etiqueta: "Menú", icono: IconoCalendario },
  { href: "/tareas", etiqueta: "Tareas", icono: IconoCheck },
  { href: "/lista-compra", etiqueta: "Compra", icono: IconoCarrito },
] as const;

export function BarraNavegacion() {
  const ruta = usePathname();

  return (
    <nav
      aria-label="Navegación principal"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-arena-200
        bg-white/90 pb-[env(safe-area-inset-bottom)] backdrop-blur
        dark:border-carbon-800 dark:bg-carbon-950/90"
    >
      <div className="mx-auto flex max-w-5xl items-stretch justify-around">
        {ENLACES.map(({ href, etiqueta, icono: Icono }) => {
          const activo =
            href === "/" ? ruta === "/" : ruta.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={activo ? "page" : undefined}
              className={`flex min-h-14 flex-1 flex-col items-center
                justify-center gap-0.5 text-xs transition-colors
                ${activo
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-carbon-950/60 hover:text-carbon-950 dark:text-arena-100/60 dark:hover:text-arena-100"
                }`}
            >
              <Icono className="size-6" />
              {etiqueta}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

function IconoCasa({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1Z" />
    </svg>
  );
}

function IconoCaja({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8m18 0-7.97-4.57a2 2 0 0 0-2.06 0L3 8m18 0-9 5.2L3 8m9 5.2V21" />
    </svg>
  );
}

function IconoCalendario({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <rect x={3} y={4} width={18} height={17} rx={2} />
      <path strokeLinecap="round" d="M8 2v4m8-4v4M3 10h18" />
    </svg>
  );
}

function IconoCheck({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <rect x={3} y={3} width={18} height={18} rx={4} />
      <path strokeLinecap="round" strokeLinejoin="round" d="m8 12 3 3 5-6" />
    </svg>
  );
}

function IconoCarrito({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3h2l2.4 12.4a1 1 0 0 0 1 .8h9.7a1 1 0 0 0 1-.8L21 7H6" />
      <circle cx={10} cy={20} r={1.5} />
      <circle cx={18} cy={20} r={1.5} />
    </svg>
  );
}
