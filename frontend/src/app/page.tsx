import { WidgetCaducidades } from "@/components/dashboard/widget-caducidades";
import { WidgetTareasHoy } from "@/components/dashboard/widget-tareas-hoy";
import { WidgetFinanzas } from "@/components/dashboard/widget-finanzas";

/**
 * Dashboard principal: cuadrícula Bento con el semáforo de caducidades,
 * las tareas del día (con turno rotativo) y el resumen financiero mensual.
 * La command bar (Ctrl+K) vive en el layout raíz.
 */
export default function Dashboard() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <WidgetCaducidades />
      <WidgetTareasHoy />
      <WidgetFinanzas />
    </div>
  );
}
