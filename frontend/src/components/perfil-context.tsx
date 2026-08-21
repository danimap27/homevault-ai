"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { Perfil } from "@/lib/types";

const CLAVE_PERFIL = "hv_perfil_activo";

interface PerfilContextValue {
  perfil: Perfil | null;
  establecerPerfil: (perfil: Perfil | null) => void;
  cargando: boolean;
}

const PerfilContext = createContext<PerfilContextValue>({
  perfil: null,
  establecerPerfil: () => {},
  cargando: true,
});

export function PerfilProvider({ children }: { children: React.ReactNode }) {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(CLAVE_PERFIL);
      if (raw) setPerfil(JSON.parse(raw));
    } catch {
      // localStorage no disponible o JSON corrupto.
    } finally {
      setCargando(false);
    }
  }, []);

  const establecerPerfil = useCallback((nuevo: Perfil | null) => {
    setPerfil(nuevo);
    try {
      if (nuevo) localStorage.setItem(CLAVE_PERFIL, JSON.stringify(nuevo));
      else localStorage.removeItem(CLAVE_PERFIL);
    } catch {
      // localStorage no disponible.
    }
  }, []);

  return (
    <PerfilContext.Provider value={{ perfil, establecerPerfil, cargando }}>
      {children}
    </PerfilContext.Provider>
  );
}

export function usePerfil() {
  return useContext(PerfilContext);
}

export { CLAVE_PERFIL };
