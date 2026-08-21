import { CalendarDays, Package, Wallet } from "lucide-react";
import { WidgetCaducidades } from "@/components/dashboard/widget-caducidades";
import { WidgetTareasHoy } from "@/components/dashboard/widget-tareas-hoy";
import { WidgetFinanzas } from "@/components/dashboard/widget-finanzas";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="tarjeta-bento-premium sm:col-span-2">
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400">
              <CalendarDays className="size-6" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Bienvenido a HomeVault AI</h2>
              <p className="text-sm text-slate-400">
                Gestión inteligente del hogar, inventario y tareas.
              </p>
            </div>
          </div>
        </div>

        <WidgetCaducidades />
        <WidgetTareasHoy />
        <WidgetFinanzas />

        <div className="tarjeta-bento flex items-center gap-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-violet-500/15 text-violet-400">
            <Package className="size-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-300">Inventario</p>
            <p className="text-xs text-slate-500">Escanea, consume y compra.</p>
          </div>
        </div>

        <div className="tarjeta-bento flex items-center gap-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400">
            <Wallet className="size-5" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-300">Finanzas</p>
            <p className="text-xs text-slate-500">Resumen mensual de gastos.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
