"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { usePerfil } from "@/components/perfil-context";

/**
 * Redirige a /perfiles cuando no hay perfil activo y la ruta actual no es
 * la pantalla de selección de perfiles. Se monta en el layout raíz.
 */
export function PerfilGate({ children }: { children: React.ReactNode }) {
  const { perfil, cargando } = usePerfil();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (cargando) return;
    if (!perfil && pathname !== "/perfiles") {
      router.replace("/perfiles");
    }
  }, [perfil, cargando, pathname, router]);

  if (cargando) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-emerald-500" />
      </div>
    );
  }

  if (!perfil && pathname !== "/perfiles") {
    return null;
  }

  return <>{children}</>;
}
