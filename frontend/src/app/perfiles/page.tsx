"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, X } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Perfil } from "@/lib/types";
import { usePerfil } from "@/components/perfil-context";

const EMOJIS = [
  "👤", "🧑", "👩", "👨", "🧒", "👧", "👦", "👶",
  "🐶", "🐱", "🦊", "🐼", "🐨", "🐯", "🦁", "🐸",
  "🤖", "👽", "👻", "🎃", "🦄", "🐙", "🦋", "🌵",
];

const COLORES_ANILLO = [
  { nombre: "emerald", clase: "ring-emerald-500" },
  { nombre: "violet", clase: "ring-violet-500" },
  { nombre: "amber", clase: "ring-amber-500" },
  { nombre: "sky", clase: "ring-sky-500" },
  { nombre: "rose", clase: "ring-rose-500" },
  { nombre: "indigo", clase: "ring-indigo-500" },
  { nombre: "teal", clase: "ring-teal-500" },
  { nombre: "fuchsia", clase: "ring-fuchsia-500" },
];

export default function PerfilesPage() {
  const router = useRouter();
  const { perfil, establecerPerfil } = usePerfil();
  const [perfiles, setPerfiles] = useState<Perfil[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modoGestion, setModoGestion] = useState(false);
  const [perfilPin, setPerfilPin] = useState<Perfil | null>(null);
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [modalAbierto, setModalAbierto] = useState(false);
  const [perfilEditando, setPerfilEditando] = useState<Perfil | null>(null);

  const cargar = async () => {
    try {
      setCargando(true);
      const data = await api.getPerfiles();
      setPerfiles(data);
      setError(null);
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudieron cargar los perfiles");
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargar();
  }, []);

  const seleccionarPerfil = async (p: Perfil) => {
    if (p.pin) {
      setPerfilPin(p);
      setPin("");
      setPinError(null);
      return;
    }
    establecerPerfil(p);
    router.replace("/");
  };

  const verificarPin = async () => {
    if (!perfilPin) return;
    if (pin.length !== 4) {
      setPinError("El PIN tiene 4 dígitos");
      return;
    }
    try {
      const { valido } = await api.verificarPinPerfil(perfilPin.id, pin);
      if (valido) {
        establecerPerfil(perfilPin);
        setPerfilPin(null);
        router.replace("/");
      } else {
        setPin("");
        setPinError("PIN incorrecto");
      }
    } catch (err) {
      setPinError(err instanceof ErrorApi ? err.message : "Error al verificar PIN");
    }
  };

  const teclaPin = (digito: string) => {
    if (pin.length < 4) {
      const nuevo = pin + digito;
      setPin(nuevo);
      if (nuevo.length === 4) {
        setTimeout(() => {
          // Usamos el valor actual del closure mediante callback no disponible,
          // por eso verificamos con el nuevo pasado explícitamente.
          verificarPinConNuevo(nuevo);
        }, 100);
      }
    }
  };

  const verificarPinConNuevo = async (nuevoPin: string) => {
    if (!perfilPin) return;
    try {
      const { valido } = await api.verificarPinPerfil(perfilPin.id, nuevoPin);
      if (valido) {
        establecerPerfil(perfilPin);
        setPerfilPin(null);
        router.replace("/");
      } else {
        setPin("");
        setPinError("PIN incorrecto");
      }
    } catch (err) {
      setPinError(err instanceof ErrorApi ? err.message : "Error al verificar PIN");
    }
  };

  const borrarDigitoPin = () => setPin((p) => p.slice(0, -1));

  const abrirCrear = () => {
    setPerfilEditando(null);
    setModalAbierto(true);
  };

  const abrirEditar = (p: Perfil) => {
    setPerfilEditando(p);
    setModalAbierto(true);
  };

  const guardarPerfil = async (input: {
    nombre: string;
    avatar: string | null;
    color: string | null;
    pin: string | null;
  }) => {
    if (perfilEditando) {
      const actualizado = await api.actualizarPerfil(perfilEditando.id, {
        nombre: input.nombre,
        avatar: input.avatar,
        color: input.color,
        pin: input.pin,
      });
      setPerfiles((prev) =>
        prev.map((p) => (p.id === actualizado.id ? actualizado : p))
      );
      if (perfil?.id === actualizado.id) establecerPerfil(actualizado);
    } else {
      const creado = await api.crearPerfil({
        nombre: input.nombre,
        avatar: input.avatar,
        color: input.color,
        pin: input.pin,
      });
      setPerfiles((prev) => [...prev, creado]);
    }
    setModalAbierto(false);
  };

  const borrarPerfil = async (id: string) => {
    if (!confirm("¿Eliminar este perfil?")) return;
    await api.borrarPerfil(id);
    setPerfiles((prev) => prev.filter((p) => p.id !== id));
    if (perfil?.id === id) establecerPerfil(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-slate-950 px-6 py-12 text-slate-100">
      <div className="w-full max-w-4xl">
        <div className="mb-10 text-center">
          <h1 className="mb-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            HomeVault <span className="text-emerald-500">AI</span>
          </h1>
          <p className="text-slate-400">¿Quién eres?</p>
        </div>

        {cargando && (
          <div className="flex justify-center py-12">
            <Loader2 className="size-10 animate-spin text-emerald-500" />
          </div>
        )}

        {error && (
          <p className="mb-6 text-center text-red-400" role="alert">
            {error}
          </p>
        )}

        {!cargando && !error && (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
              {perfiles.map((p) => (
                <div key={p.id} className="relative flex flex-col items-center">
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() =>
                      modoGestion ? abrirEditar(p) : seleccionarPerfil(p)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        modoGestion ? abrirEditar(p) : seleccionarPerfil(p);
                      }
                    }}
                    className={`group relative flex aspect-square w-full max-w-[160px] cursor-pointer items-center justify-center rounded-full bg-gradient-to-br from-slate-800 to-slate-900 text-6xl shadow-lg ring-4 transition-all duration-300 hover:scale-105 hover:shadow-emerald-500/10 focus:outline-none ${
                      p.color ?? "ring-slate-700"
                    }`}
                  >
                    <span className="drop-shadow-md transition-transform duration-300 group-hover:scale-110">
                      {p.avatar || "👤"}
                    </span>
                    {!modoGestion && p.pin && (
                      <span className="absolute bottom-2 right-2 rounded-full bg-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-300">
                        PIN
                      </span>
                    )}
                  </div>
                  <span className="mt-4 text-center text-sm font-medium text-slate-300">
                    {p.nombre}
                  </span>
                  {modoGestion && (
                    <button
                      type="button"
                      onClick={() => borrarPerfil(p.id)}
                      className="mt-2 text-xs text-red-400 hover:text-red-300"
                    >
                      Eliminar
                    </button>
                  )}
                </div>
              ))}

              {!modoGestion && perfiles.length < 8 && (
                <button
                  type="button"
                  onClick={abrirCrear}
                  className="flex aspect-square w-full max-w-[160px] flex-col items-center justify-center rounded-full border-2 border-dashed border-slate-700 bg-slate-900/50 text-slate-400 transition-all duration-300 hover:border-emerald-500/50 hover:text-emerald-400"
                >
                  <Plus className="mb-2 size-10" />
                  <span className="text-sm">Añadir perfil</span>
                </button>
              )}
            </div>

            <div className="mt-12 flex justify-center gap-4">
              <button
                type="button"
                onClick={() => setModoGestion((m) => !m)}
                className="rounded-full border border-slate-700 bg-slate-900/60 px-6 py-2.5 text-sm font-medium text-slate-300 backdrop-blur transition-colors hover:border-slate-500 hover:text-white"
              >
                {modoGestion ? "Listo" : "Gestionar perfiles"}
              </button>
            </div>
          </>
        )}
      </div>

      {perfilPin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 px-6 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-3xl border border-slate-700/50 bg-slate-900/80 p-6 shadow-2xl backdrop-blur">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-3 flex size-20 items-center justify-center rounded-full bg-slate-800 text-4xl ring-4 ring-slate-700">
                {perfilPin.avatar || "👤"}
              </div>
              <h2 className="text-lg font-medium">Hola, {perfilPin.nombre}</h2>
              <p className="text-sm text-slate-400">Introduce tu PIN</p>
            </div>

            <div className="mb-6 flex justify-center gap-3">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className={`flex size-12 items-center justify-center rounded-xl border-2 text-xl font-semibold transition-colors ${
                    i < pin.length
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                      : "border-slate-700 bg-slate-800/50 text-slate-500"
                  }`}
                >
                  {i < pin.length ? "•" : ""}
                </div>
              ))}
            </div>

            {pinError && (
              <p className="mb-4 text-center text-sm text-red-400">{pinError}</p>
            )}

            <div className="grid grid-cols-3 gap-3">
              {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => teclaPin(d)}
                  className="aspect-square rounded-2xl bg-slate-800 text-xl font-medium text-slate-200 transition-colors hover:bg-slate-700"
                >
                  {d}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setPerfilPin(null)}
                className="aspect-square rounded-2xl text-sm text-slate-400 transition-colors hover:text-white"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => teclaPin("0")}
                className="aspect-square rounded-2xl bg-slate-800 text-xl font-medium text-slate-200 transition-colors hover:bg-slate-700"
              >
                0
              </button>
              <button
                type="button"
                onClick={borrarDigitoPin}
                className="aspect-square rounded-2xl text-sm text-slate-400 transition-colors hover:text-white"
              >
                ←
              </button>
            </div>
          </div>
        </div>
      )}

      {modalAbierto && (
        <ModalPerfil
          perfil={perfilEditando}
          onGuardar={guardarPerfil}
          onCerrar={() => setModalAbierto(false)}
        />
      )}
    </div>
  );
}

function ModalPerfil({
  perfil,
  onGuardar,
  onCerrar,
}: {
  perfil: Perfil | null;
  onGuardar: (input: {
    nombre: string;
    avatar: string | null;
    color: string | null;
    pin: string | null;
  }) => void;
  onCerrar: () => void;
}) {
  const [nombre, setNombre] = useState(perfil?.nombre ?? "");
  const [avatar, setAvatar] = useState(perfil?.avatar ?? "👤");
  const [color, setColor] = useState(perfil?.color ?? "ring-emerald-500");
  const [pin, setPin] = useState(perfil?.pin ?? "");

  const puedeGuardar = nombre.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-3xl border border-slate-700/50 bg-slate-900/90 p-6 shadow-2xl backdrop-blur">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-lg font-semibold">
            {perfil ? "Editar perfil" : "Nuevo perfil"}
          </h3>
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="space-y-5">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              Nombre
            </label>
            <input
              type="text"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej. Dani"
              className="w-full rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-2.5 text-sm text-slate-100 outline-none transition-colors focus:border-emerald-500"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300">
              Avatar
            </label>
            <div className="grid grid-cols-6 gap-2">
              {EMOJIS.map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => setAvatar(e)}
                  className={`flex aspect-square items-center justify-center rounded-xl text-xl transition-all ${
                    avatar === e
                      ? "bg-emerald-500/20 ring-2 ring-emerald-500"
                      : "bg-slate-800 hover:bg-slate-700"
                  }`}
                >
                  {e}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300">
              Color de anillo
            </label>
            <div className="flex flex-wrap gap-3">
              {COLORES_ANILLO.map((c) => (
                <button
                  key={c.nombre}
                  type="button"
                  onClick={() => setColor(c.clase)}
                  className={`size-10 rounded-full bg-slate-800 ring-2 ring-offset-2 ring-offset-slate-900 transition-all ${
                    c.clase
                  } ${color === c.clase ? "scale-110" : "opacity-60 hover:opacity-100"}`}
                  aria-label={c.nombre}
                />
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              PIN (opcional, 4 dígitos)
            </label>
            <input
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pin}
              onChange={(e) => {
                const val = e.target.value.replace(/\D/g, "").slice(0, 4);
                setPin(val || "");
              }}
              placeholder="Sin PIN"
              className="w-full rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-2.5 text-sm text-slate-100 outline-none transition-colors focus:border-emerald-500"
            />
          </div>
        </div>

        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={onCerrar}
            className="flex-1 rounded-xl border border-slate-700 bg-slate-800/50 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={!puedeGuardar}
            onClick={() =>
              onGuardar({
                nombre: nombre.trim(),
                avatar,
                color,
                pin: pin || null,
              })
            }
            className="flex-1 rounded-xl bg-emerald-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
          >
            Guardar
          </button>
        </div>
      </div>
    </div>
  );
}
