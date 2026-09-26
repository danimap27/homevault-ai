"""Gestor atómico del vault Markdown de HomeVault AI.

Corazón de la Fase 1: lectura/escritura atómica con bloqueo async por archivo,
validación estricta con los modelos Pydantic, motor FIFO de lotes, trigger de
lista de la compra, detector de huérfanos y consultas de caducidad.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, TypeVar, cast, get_args

import frontmatter
import portalocker
from pydantic import BaseModel, ValidationError

from backend.categorias import CategoriaManager
from backend.models import (
    Consumible,
    ConsumoRegistrado,
    DesperdicioRegistrado,
    EntradaListaCompra,
    Ingrediente,
    ItemCaducidad,
    ItemHuerfano,
    Lote,
    Receta,
    ResumenDesperdicio,
    ResultadoCompra,
    ResultadoConsumo,
    Tarea,
    Ubicacion,
    Unidad,
)

ModeloT = TypeVar("ModeloT", bound=BaseModel)

# Formato de línea de la lista de la compra:
# - [ ] Nombre <!-- item_id:X; cantidad:1.0; unidad:litros; categoria:lacteos -->
_REGEX_LINEA_COMPRA = re.compile(
    r"^- \[(?P<marcado>[ xX])\] (?P<nombre>.*?)"
    r"(?: <!-- item_id:(?P<item_id>[^;]+);"
    r" cantidad:(?P<cantidad>[^;]*);"
    r" unidad:(?P<unidad>[^;]*);"
    r" categoria:(?P<categoria>[^;]*?) -->)?\s*$"
)

CABECERA_LISTA_COMPRA = "# Lista de la compra\n\n"


def ahora_utc() -> datetime:
    """Devuelve el instante actual en UTC con tzinfo."""
    return datetime.now(timezone.utc)


# --- Historial de consumo (base de las predicciones) --------------------------

_MAX_HISTORIAL_CONSUMO = 100  # entradas máximas conservadas por ítem
_PODA_HISTORIAL_DIAS = 365


def podar_historial_consumo(
    historial: list[ConsumoRegistrado], ahora: datetime
) -> list[ConsumoRegistrado]:
    """Recorta el historial: sin entradas de más de un año y máx. 100."""
    limite = ahora - timedelta(days=_PODA_HISTORIAL_DIAS)
    recientes = [c for c in historial if c.fecha >= limite]
    return recientes[-_MAX_HISTORIAL_CONSUMO:]


def recalcular_dias_promedio(
    historial: list[ConsumoRegistrado],
) -> Optional[float]:
    """Media de días entre consumos consecutivos (últimos 20 registros).

    Devuelve ``None`` si no hay al menos 3 consumos (2 intervalos), en cuyo
    caso el valor existente del ítem se conserva.
    """
    fechas = sorted(c.fecha for c in historial)[-20:]
    if len(fechas) < 3:
        return None
    intervalos = [
        (b - a).total_seconds() / 86400 for a, b in zip(fechas, fechas[1:])
    ]
    return round(sum(intervalos) / len(intervalos), 2)


class VaultManager:
    """Gestor async del vault Markdown.

    Garantiza escritura atómica (archivo .tmp + os.replace) y ausencia de
    condiciones de carrera mediante un asyncio.Lock por ruta de archivo más
    un bloqueo de proceso con portalocker durante la escritura.
    """

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path)
        self.categoria_manager = CategoriaManager(self.vault_path)
        self._locks: dict[Path, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    # --- Infraestructura de bloqueo y E/S atómica -----------------------------

    async def _get_lock(self, path: Path) -> asyncio.Lock:
        """Devuelve (creando si hace falta) el lock async de una ruta."""
        async with self._locks_guard:
            if path not in self._locks:
                self._locks[path] = asyncio.Lock()
            return self._locks[path]

    @staticmethod
    def _escritura_atomica_sync(path: Path, contenido: str) -> None:
        """Escritura atómica síncrona con lock de proceso (portalocker)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        # Lock de proceso sobre un sidecar .lock para escrituras seguras
        # entre procesos distintos del backend.
        with portalocker.Lock(
            str(path) + ".lock", mode="w", timeout=10
        ):
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(contenido)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)

    async def _write_text(self, path: Path, contenido: str) -> None:
        """Escritura atómica async (delega el bloqueo de SO a un hilo)."""
        await asyncio.to_thread(self._escritura_atomica_sync, path, contenido)

    # --- Parseo y serialización con validación Pydantic -----------------------

    @staticmethod
    def _parsear_doc(
        texto: str, model_cls: type[ModeloT]
    ) -> tuple[ModeloT, str]:
        """Separa frontmatter y cuerpo, y valida el frontmatter."""
        post = frontmatter.loads(texto)
        modelo = model_cls.model_validate(post.metadata)
        return modelo, post.content

    async def _read_doc(
        self, path: Path, model_cls: type[ModeloT]
    ) -> tuple[ModeloT, str]:
        """Lee y valida un documento Markdown del vault."""
        texto = await asyncio.to_thread(
            path.read_text, encoding="utf-8"
        )
        return self._parsear_doc(texto, model_cls)

    async def _write_doc(
        self, path: Path, modelo: BaseModel, cuerpo: str
    ) -> None:
        """Serializa el frontmatter desde el modelo preservando el cuerpo."""
        metadata = modelo.model_dump(mode="json")
        post = frontmatter.Post(cuerpo, **metadata)
        await self._write_text(path, frontmatter.dumps(post))

    # --- Localización de ítems de inventario ----------------------------------

    def _archivos_inventario(self) -> list[Path]:
        """Lista todos los .md bajo inventario/ (recursivo)."""
        raiz = self.vault_path / "inventario"
        if not raiz.exists():
            return []
        return sorted(raiz.rglob("*.md"))

    async def list_items(
        self, ubicacion: Optional[str] = None
    ) -> list[Consumible]:
        """Devuelve todos los consumibles, con filtro opcional de ubicación."""
        items: list[Consumible] = []
        for path in self._archivos_inventario():
            item, _ = await self._read_doc(path, Consumible)
            if ubicacion is None or item.ubicacion == ubicacion:
                items.append(item)
        return items

    async def _find_item_path(self, item_id: str) -> Optional[Path]:
        """Localiza la ruta del archivo de un ítem por su id."""
        for path in self._archivos_inventario():
            item, _ = await self._read_doc(path, Consumible)
            if item.id == item_id:
                return path
        return None

    async def get_item(self, item_id: str) -> Optional[Consumible]:
        """Busca un ítem por id."""
        path = await self._find_item_path(item_id)
        if path is None:
            return None
        item, _ = await self._read_doc(path, Consumible)
        return item

    async def get_item_by_ean(self, ean_barcode: str) -> Optional[Consumible]:
        """Busca un ítem por código de barras EAN."""
        for path in self._archivos_inventario():
            item, _ = await self._read_doc(path, Consumible)
            if item.ean_barcode == ean_barcode:
                return item
        return None

    async def search_by_name(self, texto: str) -> list[Consumible]:
        """Búsqueda fuzzy simple: substring case-insensitive en el nombre."""
        aguja = texto.casefold()
        return [
            item
            for item in await self.list_items()
            if aguja in item.nombre.casefold()
        ]

    async def resolve_item(self, identificador: str) -> Optional[Consumible]:
        """Resuelve un identificador (id, EAN o nombre) a un Consumible."""
        path = await self.resolve_item_path(identificador)
        if path is None:
            return None
        item, _ = await self._read_doc(path, Consumible)
        return item

    async def resolve_item_path(self, identificador: str) -> Optional[Path]:
        """Resuelve un identificador (id, EAN o nombre) a una ruta de archivo.

        Orden de resolución: id exacto, EAN exacto, nombre (substring).
        """
        path = await self._find_item_path(identificador)
        if path is not None:
            return path
        por_ean = await self.get_item_by_ean(identificador)
        if por_ean is not None:
            return await self._find_item_path(por_ean.id)
        por_nombre = await self.search_by_name(identificador)
        if por_nombre:
            return await self._find_item_path(por_nombre[0].id)
        return None

    # --- Motor FIFO de lotes ---------------------------------------------------

    async def consume_item(
        self, item_id: str, cantidad: float
    ) -> ResultadoConsumo:
        """Consume N unidades de un ítem siguiendo FIFO por fecha de caducidad.

        Descuenta primero del lote con fecha_caducidad más cercana; si los
        lotes se agotan, descuenta el resto de stock_actual. Actualiza
        ultimo_consumo, ultima_actualizacion y fecha_caducidad_proxima, y
        dispara el trigger de lista de la compra si cae bajo el mínimo.
        """
        path = await self._find_item_path(item_id)
        if path is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")

        lock = await self._get_lock(path)
        async with lock:
            item, cuerpo = await self._read_doc(path, Consumible)

            restante = cantidad
            consumido_lotes = 0.0
            # FIFO: lotes ordenados por caducidad ascendente (None al final)
            lotes_ordenados = sorted(
                item.lotes,
                key=lambda l: (l.fecha_caducidad is None, l.fecha_caducidad),
            )
            for lote in lotes_ordenados:
                if restante <= 0:
                    break
                tomado = min(lote.cantidad, restante)
                lote.cantidad = round(lote.cantidad - tomado, 6)
                restante = round(restante - tomado, 6)
                consumido_lotes += tomado
            # Eliminar lotes agotados
            item.lotes = [l for l in lotes_ordenados if l.cantidad > 0]

            # Lo que no cubrieron los lotes sale del stock_actual
            consumido_stock = 0.0
            if restante > 0:
                consumido_stock = min(restante, item.stock_actual)
                item.stock_actual = round(
                    max(item.stock_actual - restante, 0.0), 6
                )

            ahora = ahora_utc()
            item.ultimo_consumo = ahora
            item.ultima_actualizacion = ahora
            item.fecha_caducidad_proxima = self._caducidad_proxima(item.lotes)

            # Historial para predicciones: registrar el consumo y acotarlo
            item.historial_consumo.append(
                ConsumoRegistrado(fecha=ahora, cantidad=cantidad)
            )
            item.historial_consumo = podar_historial_consumo(
                item.historial_consumo, ahora
            )
            promedio = recalcular_dias_promedio(item.historial_consumo)
            if promedio is not None and promedio > 0:
                item.dias_promedio_consumo = promedio

            await self._write_doc(path, item, cuerpo)

        bajo_minimo = item.stock_actual <= item.stock_minimo
        anadido = False
        if bajo_minimo and item.auto_lista_compra:
            anadido = await self._add_to_shopping_list(item)

        return ResultadoConsumo(
            item_id=item.id,
            cantidad_solicitada=cantidad,
            cantidad_consumida_lotes=round(consumido_lotes, 6),
            cantidad_consumida_stock=round(consumido_stock, 6),
            stock_actual=item.stock_actual,
            stock_minimo=item.stock_minimo,
            bajo_minimo=bajo_minimo,
            anadido_a_lista_compra=anadido,
        )

    @staticmethod
    def _caducidad_proxima(lotes: list[Lote]) -> Optional[date]:
        """Mínima fecha de caducidad entre los lotes restantes."""
        fechas = [l.fecha_caducidad for l in lotes if l.fecha_caducidad]
        return min(fechas) if fechas else None

    # --- Compras ----------------------------------------------------------------

    async def add_purchase(
        self,
        item_id: str,
        cantidad: float,
        precio_unitario: float,
        fecha_caducidad: Optional[date] = None,
        supermercado: Optional[str] = None,
    ) -> ResultadoCompra:
        """Registra una compra: nuevo lote, incremento de stock y [x] en lista."""
        path = await self._find_item_path(item_id)
        if path is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")

        lock = await self._get_lock(path)
        async with lock:
            item, cuerpo = await self._read_doc(path, Consumible)

            id_lote = f"lot_{uuid.uuid4().hex[:8]}"
            item.lotes.append(
                Lote(
                    id_lote=id_lote,
                    cantidad=cantidad,
                    fecha_caducidad=fecha_caducidad,
                    fecha_adquisicion=ahora_utc().date(),
                    supermercado=supermercado,
                )
            )
            item.stock_actual = round(item.stock_actual + cantidad, 6)
            item.precio_unitario_estimado = precio_unitario
            item.ultima_actualizacion = ahora_utc()
            item.fecha_caducidad_proxima = self._caducidad_proxima(item.lotes)

            await self._write_doc(path, item, cuerpo)

        tachado = await self._mark_purchased(item.id)

        return ResultadoCompra(
            item_id=item.id,
            id_lote=id_lote,
            cantidad=cantidad,
            stock_actual=item.stock_actual,
            tachado_de_lista_compra=tachado,
            supermercado=supermercado,
        )

    # --- Merma / desperdicio (gastos/desperdicio-YYYY-MM.md) -------------------

    def _path_desperdicio(self, mes: str) -> Path:
        return self.vault_path / "gastos" / f"desperdicio-{mes}.md"

    @staticmethod
    def _parsear_tabla_desperdicio(cuerpo: str) -> list[DesperdicioRegistrado]:
        """Extrae los registros de la tabla Markdown de un mes de desperdicio."""
        registros: list[DesperdicioRegistrado] = []
        for linea in cuerpo.splitlines():
            if not linea.startswith("|"):
                continue
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if len(celdas) != 7 or celdas[0] in {"fecha", "-------"}:
                continue
            if set(celdas[0]) <= {"-"}:
                continue
            try:
                registros.append(
                    DesperdicioRegistrado(
                        fecha=datetime.fromisoformat(celdas[0]),
                        item_id=celdas[1],
                        nombre=celdas[2],
                        cantidad=float(celdas[3]),
                        unidad=cast("Unidad", celdas[4]),
                        motivo=celdas[5],
                        valor_estimado=float(celdas[6]),
                    )
                )
            except (ValueError, ValidationError):
                # Línea corrupta o de otra versión del formato: se ignora
                continue
        return registros

    @staticmethod
    def _formato_documento_desperdicio(
        mes: str, registros: list[DesperdicioRegistrado]
    ) -> str:
        """Serializa el documento completo de desperdicio de un mes."""
        total = round(sum(r.valor_estimado for r in registros), 2)
        lineas = [
            "---",
            f'mes: "{mes}"',
            f"total_registros: {len(registros)}",
            f"valor_total_estimado: {total}",
            f"ultima_actualizacion: '{ahora_utc().isoformat()}'",
            "---",
            "",
            f"# Desperdicio {mes}",
            "",
            "| fecha | item_id | nombre | cantidad | unidad | motivo | valor |",
            "|-------|---------|--------|----------|--------|--------|-------|",
        ]
        for r in registros:
            nombre = r.nombre.replace("|", "/")
            motivo = r.motivo.replace("|", "/")
            lineas.append(
                f"| {r.fecha.isoformat()} | {r.item_id} | {nombre} | "
                f"{r.cantidad:g} | {r.unidad} | {motivo} | {r.valor_estimado:.2f} |"
            )
        lineas.append("")
        return "\n".join(lineas)

    async def register_waste(
        self, item_id: str, cantidad: float, motivo: str = "otro"
    ) -> tuple[DesperdicioRegistrado, Consumible]:
        """Registra una merma: descuenta stock (FIFO de lotes) y anota el gasto.

        Mismo descuento que ``consume_item`` (lotes por caducidad ascendente y
        después el stock suelto) pero sin tocar ``ultimo_consumo``. Devuelve el
        registro creado y el ítem actualizado. Lanza ``ValueError`` si la
        cantidad supera el stock disponible.
        """
        if cantidad <= 0:
            raise ValueError("La cantidad de merma debe ser mayor que cero")

        path = await self._find_item_path(item_id)
        if path is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")

        lock = await self._get_lock(path)
        async with lock:
            item, cuerpo = await self._read_doc(path, Consumible)

            disponible = round(item.stock_actual, 6)
            if cantidad - disponible > 1e-6:
                raise ValueError(
                    f"Stock insuficiente de '{item.nombre}': "
                    f"{disponible:g} {item.unidad} disponibles"
                )

            restante = cantidad
            lotes_ordenados = sorted(
                item.lotes,
                key=lambda l: (l.fecha_caducidad is None, l.fecha_caducidad),
            )
            for lote in lotes_ordenados:
                if restante <= 0:
                    break
                tomado = min(lote.cantidad, restante)
                lote.cantidad = round(lote.cantidad - tomado, 6)
                restante = round(restante - tomado, 6)
            item.lotes = [l for l in lotes_ordenados if l.cantidad > 0]

            if restante > 0:
                item.stock_actual = round(
                    max(item.stock_actual - restante, 0.0), 6
                )

            item.ultima_actualizacion = ahora_utc()
            item.fecha_caducidad_proxima = self._caducidad_proxima(item.lotes)

            await self._write_doc(path, item, cuerpo)

        registro = DesperdicioRegistrado(
            fecha=ahora_utc(),
            item_id=item.id,
            nombre=item.nombre,
            cantidad=cantidad,
            unidad=item.unidad,
            motivo=motivo,
            valor_estimado=round(
                cantidad * (item.precio_unitario_estimado or 0.0), 2
            ),
        )
        await self._anadir_registro_desperdicio(registro)
        return registro, item

    async def _anadir_registro_desperdicio(
        self, registro: DesperdicioRegistrado
    ) -> None:
        """Añade un registro al documento mensual de desperdicio."""
        mes = registro.fecha.strftime("%Y-%m")
        path = self._path_desperdicio(mes)
        lock = await self._get_lock(path)
        async with lock:
            registros: list[DesperdicioRegistrado] = []
            if path.exists():
                texto = await asyncio.to_thread(path.read_text, encoding="utf-8")
                partes = texto.split("---")
                cuerpo = partes[-1] if len(partes) >= 3 else texto
                registros = self._parsear_tabla_desperdicio(cuerpo)
            registros.append(registro)
            contenido = self._formato_documento_desperdicio(mes, registros)
            await self._write_text(path, contenido)

    async def resumen_desperdicio(self, mes: str) -> ResumenDesperdicio:
        """Resumen del desperdicio de un mes (vacío si no hay registros)."""
        path = self._path_desperdicio(mes)
        if not path.exists():
            return ResumenDesperdicio(mes=mes)
        texto = await asyncio.to_thread(path.read_text, encoding="utf-8")
        partes = texto.split("---")
        cuerpo = partes[-1] if len(partes) >= 3 else texto
        registros = self._parsear_tabla_desperdicio(cuerpo)
        por_motivo: dict[str, int] = {}
        for r in registros:
            por_motivo[r.motivo] = por_motivo.get(r.motivo, 0) + 1
        return ResumenDesperdicio(
            mes=mes,
            total_registros=len(registros),
            valor_total=round(sum(r.valor_estimado for r in registros), 2),
            por_motivo=por_motivo,
            ultimos=list(reversed(registros[-10:])),
        )

    # --- Lista de la compra (listas/compra.md) ----------------------------------

    @property
    def _path_lista_compra(self) -> Path:
        return self.vault_path / "listas" / "compra.md"

    async def _leer_lineas_compra(self) -> list[str]:
        """Lee las líneas de la lista de la compra (crea el archivo si falta)."""
        path = self._path_lista_compra
        if not path.exists():
            await self._write_text(path, CABECERA_LISTA_COMPRA)
            return CABECERA_LISTA_COMPRA.splitlines(keepends=True)
        texto = await asyncio.to_thread(path.read_text, encoding="utf-8")
        return texto.splitlines(keepends=True)

    def _esta_pendiente_en_lista(
        self, lineas: list[str], item_id: str
    ) -> bool:
        """True si el ítem ya está como pendiente ([ ]) en la lista."""
        for linea in lineas:
            match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
            if (
                match
                and match.group("item_id") == item_id
                and match.group("marcado") == " "
            ):
                return True
        return False

    async def _add_to_shopping_list(self, item: Consumible) -> bool:
        """Añade el ítem a listas/compra.md si no está ya pendiente.

        Devuelve True si se añadió una línea nueva.
        """
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            if self._esta_pendiente_en_lista(lineas, item.id):
                return False
            cantidad_sugerida = round(
                max(item.stock_minimo - item.stock_actual + 1.0, 1.0), 2
            )
            lineas.append(
                self._formato_linea_compra(
                    item.nombre,
                    item.id,
                    cantidad_sugerida,
                    item.unidad,
                    item.categoria,
                )
            )
            await self._write_text(self._path_lista_compra, "".join(lineas))
            return True

    async def _mark_purchased(self, item_id: str) -> bool:
        """Tacha ([x]) el ítem de la lista de la compra si estaba pendiente."""
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            tachado = False
            nuevas: list[str] = []
            for linea in lineas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if (
                    match
                    and match.group("item_id") == item_id
                    and match.group("marcado") == " "
                ):
                    nuevas.append(linea.replace("- [ ]", "- [x]", 1))
                    tachado = True
                else:
                    nuevas.append(linea)
            if tachado:
                await self._write_text(
                    self._path_lista_compra, "".join(nuevas)
                )
            return tachado

    async def get_shopping_list(self) -> list[EntradaListaCompra]:
        """Parsea listas/compra.md y devuelve sus entradas estructuradas."""
        lineas = await self._leer_lineas_compra()
        entradas: list[EntradaListaCompra] = []
        for linea in lineas:
            match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
            if not match:
                continue
            cantidad_raw = match.group("cantidad")
            entradas.append(
                EntradaListaCompra(
                    item_id=match.group("item_id") or "",
                    nombre=match.group("nombre").strip(),
                    cantidad=(
                        float(cantidad_raw)
                        if cantidad_raw not in (None, "")
                        else None
                    ),
                    unidad=match.group("unidad") or None,
                    categoria=match.group("categoria") or None,
                    comprado=match.group("marcado").lower() == "x",
                )
            )
        return entradas

    @staticmethod
    def _coincide_linea(match: re.Match, nombre_o_id: str) -> bool:
        """True si la línea coincide por item_id exacto o nombre (substring)."""
        if match.group("item_id") and match.group("item_id") == nombre_o_id:
            return True
        return (
            nombre_o_id.strip().casefold()
            in match.group("nombre").strip().casefold()
        )

    async def add_shopping_list_entry(
        self,
        nombre: str,
        item_id: Optional[str] = None,
        cantidad: Optional[float] = None,
        unidad: Optional[str] = None,
        categoria: Optional[str] = None,
    ) -> bool:
        """Añade una línea pendiente a listas/compra.md.

        Si ya existe una línea pendiente con el mismo nombre o item_id, no
        duplica. Devuelve True si se añadió una línea nueva.
        """
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            for linea in lineas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if not match or match.group("marcado") != " ":
                    continue
                mismo_id = item_id and match.group("item_id") == item_id
                mismo_nombre = (
                    match.group("nombre").strip().casefold()
                    == nombre.strip().casefold()
                )
                if mismo_id or mismo_nombre:
                    return False
            lineas.append(
                self._formato_linea_compra(
                    nombre, item_id or "", cantidad, unidad, categoria
                )
            )
            await self._write_text(self._path_lista_compra, "".join(lineas))
            return True

    async def remove_shopping_list_entry(self, item_id: str) -> int:
        """Elimina las líneas que coincidan con ``item_id``.

        Eliminan tanto líneas pendientes como tachadas. Si ninguna línea
        tiene ese ``item_id``, se intenta una coincidencia por nombre exacto
        (case-insensitive) para mantener compatibilidad con líneas añadidas
        manualmente sin metadata.

        Devuelve el número de líneas eliminadas.
        """
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            # Primera pasada: coincidencia exacta por item_id
            eliminadas_id = 0
            candidatas: list[str] = []
            for linea in lineas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if match and match.group("item_id") == item_id:
                    eliminadas_id += 1
                    continue
                candidatas.append(linea)
            if eliminadas_id:
                await self._write_text(
                    self._path_lista_compra, "".join(candidatas)
                )
                return eliminadas_id
            # Fallback por nombre exacto (líneas sin item_id)
            nombre_buscado = item_id.strip().casefold()
            nuevas: list[str] = []
            eliminadas_nombre = 0
            for linea in candidatas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if (
                    match
                    and match.group("nombre").strip().casefold()
                    == nombre_buscado
                ):
                    eliminadas_nombre += 1
                    continue
                nuevas.append(linea)
            if eliminadas_nombre:
                await self._write_text(
                    self._path_lista_compra, "".join(nuevas)
                )
            return eliminadas_nombre

    async def update_shopping_list_entry(
        self,
        item_id: str,
        cantidad: Optional[float] = None,
        unidad: Optional[str] = None,
        categoria: Optional[str] = None,
    ) -> int:
        """Edita las líneas pendientes ([ ]) que coincidan con ``item_id``.

        Si no existe una línea pendiente para ese ``item_id`` no crea nada.
        Devuelve el número de líneas editadas.
        """
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            editadas = 0
            nuevas: list[str] = []
            for linea in lineas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if (
                    match
                    and match.group("marcado") == " "
                    and match.group("item_id") == item_id
                ):
                    nombre = match.group("nombre").strip()
                    nueva_cantidad = (
                        cantidad
                        if cantidad is not None
                        else (
                            float(match.group("cantidad"))
                            if match.group("cantidad") not in (None, "")
                            else None
                        )
                    )
                    nueva_unidad = (
                        unidad if unidad is not None else match.group("unidad")
                    )
                    nueva_categoria = (
                        categoria
                        if categoria is not None
                        else match.group("categoria")
                    )
                    nuevas.append(
                        self._formato_linea_compra(
                            nombre,
                            item_id,
                            nueva_cantidad,
                            nueva_unidad,
                            nueva_categoria,
                        )
                    )
                    editadas += 1
                else:
                    nuevas.append(linea)
            if editadas:
                await self._write_text(self._path_lista_compra, "".join(nuevas))
            return editadas

    @staticmethod
    def _formato_linea_compra(
        nombre: str,
        item_id: str,
        cantidad: Optional[float],
        unidad: Optional[str],
        categoria: Optional[str],
    ) -> str:
        """Construye una línea de lista de la compra con su comentario HTML."""
        if not item_id:
            return f"- [ ] {nombre}\n"
        return (
            f"- [ ] {nombre} <!-- item_id:{item_id};"
            f" cantidad:{cantidad if cantidad is not None else ''};"
            f" unidad:{unidad or ''};"
            f" categoria:{categoria or ''} -->\n"
        )

    async def check_shopping_list_entry(self, nombre_o_id: str) -> int:
        """Tacha ([x]) las líneas pendientes que coincidan (id o nombre).

        Devuelve el número de líneas tachadas.
        """
        lock = await self._get_lock(self._path_lista_compra)
        async with lock:
            lineas = await self._leer_lineas_compra()
            tachadas = 0
            nuevas: list[str] = []
            for linea in lineas:
                match = _REGEX_LINEA_COMPRA.match(linea.rstrip("\n"))
                if (
                    match
                    and match.group("marcado") == " "
                    and self._coincide_linea(match, nombre_o_id)
                ):
                    nuevas.append(linea.replace("- [ ]", "- [x]", 1))
                    tachadas += 1
                else:
                    nuevas.append(linea)
            if tachadas:
                await self._write_text(self._path_lista_compra, "".join(nuevas))
            return tachadas

    # --- Detector de huérfanos ---------------------------------------------------

    async def find_orphan_items(self) -> list[ItemHuerfano]:
        """Detecta ítems sin consumo reciente (candidatos a revisión).

        Un ítem es huérfano si han pasado más de dias_promedio_consumo * 2.0
        días desde su ultimo_consumo.
        """
        huerfanos: list[ItemHuerfano] = []
        ahora = ahora_utc()
        for item in await self.list_items():
            if item.dias_promedio_consumo and item.ultimo_consumo:
                delta = ahora - item.ultimo_consumo
                dias_desde = delta.total_seconds() / 86400.0
                umbral = item.dias_promedio_consumo * 2.0
                if dias_desde > umbral:
                    huerfanos.append(
                        ItemHuerfano(
                            item_id=item.id,
                            nombre=item.nombre,
                            dias_desde_ultimo_consumo=round(dias_desde, 1),
                            dias_exceso=round(dias_desde - umbral, 1),
                        )
                    )
        huerfanos.sort(
            key=lambda h: h.dias_exceso, reverse=True
        )
        return huerfanos

    # --- Caducidades --------------------------------------------------------------

    async def query_expiring(self, days_ahead: int) -> list[ItemCaducidad]:
        """Ítems con caducidad (propia o de algún lote) dentro de days_ahead.

        Ordenados por urgencia (fecha de caducidad ascendente).
        """
        hoy = ahora_utc().date()
        limite = hoy + timedelta(days=days_ahead)
        resultados: list[ItemCaducidad] = []
        for item in await self.list_items():
            candidatas: list[tuple[date, str]] = []
            if item.fecha_caducidad_proxima:
                candidatas.append((item.fecha_caducidad_proxima, "item"))
            for lote in item.lotes:
                if lote.fecha_caducidad:
                    candidatas.append((lote.fecha_caducidad, lote.id_lote))
            en_ventana = [c for c in candidatas if c[0] <= limite]
            if not en_ventana:
                continue
            fecha, origen = min(en_ventana, key=lambda c: c[0])
            resultados.append(
                ItemCaducidad(
                    item_id=item.id,
                    nombre=item.nombre,
                    fecha_caducidad=fecha,
                    dias_restantes=(fecha - hoy).days,
                    origen=origen,
                )
            )
        resultados.sort(key=lambda r: r.fecha_caducidad)
        return resultados

    # --- CRUD de ítems de inventario --------------------------------------------

    _CAMPOS_ITEM_EDITABLES: frozenset[str] = frozenset(
        {
            "nombre",
            "categoria",
            "ubicacion",
            "stock_minimo",
            "unidad",
            "precio_unitario_estimado",
            "dias_promedio_consumo",
            "auto_lista_compra",
            "tags",
            "ean_barcode",
        }
    )

    def _ruta_item(self, item: Consumible) -> Path:
        """Devuelve la ruta canónica de un ítem según su ubicación."""
        return (
            self.vault_path
            / "inventario"
            / item.ubicacion
            / f"{item.id}.md"
        )

    def _validar_categoria(self, categoria: str) -> None:
        """Lanza ``ValueError`` si la categoría no existe en el manager."""
        if not self.categoria_manager.existe(categoria):
            raise ValueError(f"Categoría no válida: {categoria}")

    async def create_item(self, consumible: Consumible) -> Consumible:
        """Crea un nuevo ítem de inventario en ``inventario/<ubicacion>/<id>.md``.

        Raises:
            FileExistsError: si ya existe un archivo con el mismo id en la
                ubicación indicada.
        """
        self._validar_categoria(consumible.categoria)

        path = self._ruta_item(consumible)
        if path.exists():
            raise FileExistsError(
                f"Ya existe un ítem en {path.relative_to(self.vault_path)}"
            )

        cuerpo = f"# {consumible.nombre}\n\n"
        lock = await self._get_lock(path)
        async with lock:
            await self._write_doc(path, consumible, cuerpo)
        return consumible

    async def update_item(self, item_id: str, cambios: dict) -> Consumible:
        """Actualiza los campos editables de un ítem preservando el cuerpo.

        No permite modificar ``id`` ni ``stock_actual`` (este último se gestiona
        a través de ``consume_item``/``add_purchase``). Si ``cambios`` incluye
        una nueva ``ubicacion``, el archivo se mueve a la subcarpeta
        correspondiente.

        Raises:
            KeyError: si el ítem no existe.
            ValueError: si se intenta cambiar ``id`` o ``stock_actual``.
        """
        if "id" in cambios or "stock_actual" in cambios:
            raise ValueError(
                "No se permite cambiar 'id' ni 'stock_actual' directamente"
            )

        campos_invalidos = set(cambios.keys()) - self._CAMPOS_ITEM_EDITABLES
        if campos_invalidos:
            raise ValueError(
                f"Campos no editables en ítem: {sorted(campos_invalidos)}"
            )

        if "categoria" in cambios:
            self._validar_categoria(cambios["categoria"])

        path = await self._find_item_path(item_id)
        if path is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")

        lock = await self._get_lock(path)
        async with lock:
            item, cuerpo = await self._read_doc(path, Consumible)
            nueva_ubicacion = cambios.get("ubicacion", item.ubicacion)
            if nueva_ubicacion not in get_args(Ubicacion):
                raise ValueError(f"Ubicación no válida: {nueva_ubicacion}")

            for campo, valor in cambios.items():
                setattr(item, campo, valor)

            item.ultima_actualizacion = ahora_utc()
            destino = self._ruta_item(item)
            if destino != path:
                if destino.exists():
                    raise FileExistsError(
                        f"Ya existe un ítem en {destino.relative_to(self.vault_path)}"
                    )
                await self._write_doc(destino, item, cuerpo)
                await asyncio.to_thread(path.unlink)
            else:
                await self._write_doc(path, item, cuerpo)
        return item

    async def delete_item(self, item_id: str) -> bool:
        """Elimina el archivo ``.md`` de un ítem. Devuelve True si existía."""
        path = await self._find_item_path(item_id)
        if path is None:
            return False

        lock = await self._get_lock(path)
        async with lock:
            path = await self._find_item_path(item_id)
            if path is None:
                return False
            await asyncio.to_thread(path.unlink)
        return True

    async def move_item(
        self,
        item_id: str,
        nueva_categoria: str | None = None,
        nueva_ubicacion: Ubicacion | None = None,
    ) -> Consumible:
        """Mueve un ítem de ubicación (y opcionalmente de categoría).

        Si cambia la ubicación, el archivo se traslada a la nueva subcarpeta
        bajo ``inventario/``. La categoría se valida contra el catálogo
        dinámico antes de aplicarla.

        Raises:
            KeyError: si el ítem no existe.
            ValueError: si la nueva categoría no existe.
        """
        if nueva_categoria is not None:
            self._validar_categoria(nueva_categoria)

        path = await self._find_item_path(item_id)
        if path is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")

        lock = await self._get_lock(path)
        async with lock:
            item, cuerpo = await self._read_doc(path, Consumible)
            if nueva_categoria is not None:
                item.categoria = nueva_categoria
            if nueva_ubicacion is not None:
                item.ubicacion = nueva_ubicacion

            item.ultima_actualizacion = ahora_utc()
            destino = self._ruta_item(item)
            if destino != path:
                if destino.exists():
                    raise FileExistsError(
                        f"Ya existe un ítem en {destino.relative_to(self.vault_path)}"
                    )
                await self._write_doc(destino, item, cuerpo)
                await asyncio.to_thread(path.unlink)
            else:
                await self._write_doc(path, item, cuerpo)
        return item

    # --- Recetas (recetas/*.md) -------------------------------------------------

    def _archivos_recetas(self) -> list[Path]:
        """Lista todos los .md bajo recetas/ (recursivo)."""
        raiz = self.vault_path / "recetas"
        if not raiz.exists():
            return []
        return sorted(raiz.rglob("*.md"))

    async def list_recipes(self) -> list[Receta]:
        """Devuelve todas las recetas del vault."""
        recetas: list[Receta] = []
        for path in self._archivos_recetas():
            receta, _ = await self._read_doc(path, Receta)
            recetas.append(receta)
        return recetas

    async def _find_recipe_path(self, receta_id: str) -> Optional[Path]:
        """Localiza la ruta del archivo de una receta por su id."""
        for path in self._archivos_recetas():
            receta, _ = await self._read_doc(path, Receta)
            if receta.id == receta_id:
                return path
        return None

    async def get_receta(self, receta_id: str) -> Optional[Receta]:
        """Busca una receta por id."""
        path = await self._find_recipe_path(receta_id)
        if path is None:
            return None
        receta, _ = await self._read_doc(path, Receta)
        return receta

    _CAMPOS_RECETA_EDITABLES: frozenset[str] = frozenset(
        {
            "titulo",
            "categoria",
            "tiempo_minutos",
            "raciones",
            "calorias_racion",
            "ingredientes",
            "tags",
        }
    )

    async def create_receta(self, receta: Receta) -> Receta:
        """Crea una nueva receta en ``recetas/<id>.md``.

        Raises:
            FileExistsError: si ya existe una receta con el mismo id.
        """
        path = self.vault_path / "recetas" / f"{receta.id}.md"
        if path.exists():
            raise FileExistsError(
                f"Ya existe una receta en {path.relative_to(self.vault_path)}"
            )

        cuerpo = f"# {receta.titulo}\n\n## Ingredientes\n\n## Elaboración\n\n1.\n"
        lock = await self._get_lock(path)
        async with lock:
            await self._write_doc(path, receta, cuerpo)
        return receta

    async def update_receta(self, receta_id: str, cambios: dict) -> Receta:
        """Actualiza los campos editables de una receta preservando el cuerpo.

        No permite modificar ``id``.

        Raises:
            KeyError: si la receta no existe.
            ValueError: si se intenta cambiar ``id`` o hay campos desconocidos.
        """
        if "id" in cambios:
            raise ValueError("No se permite cambiar el 'id' de una receta")

        campos_invalidos = set(cambios.keys()) - self._CAMPOS_RECETA_EDITABLES
        if campos_invalidos:
            raise ValueError(
                f"Campos no editables en receta: {sorted(campos_invalidos)}"
            )

        path = await self._find_recipe_path(receta_id)
        if path is None:
            raise KeyError(f"Receta no encontrada: {receta_id}")

        lock = await self._get_lock(path)
        async with lock:
            receta, cuerpo = await self._read_doc(path, Receta)
            for campo, valor in cambios.items():
                if campo == "ingredientes":
                    receta.ingredientes = [
                        (
                            Ingrediente.model_validate(ing)
                            if isinstance(ing, dict)
                            else ing
                        )
                        for ing in valor
                    ]
                else:
                    setattr(receta, campo, valor)
            await self._write_doc(path, receta, cuerpo)
        return receta

    async def delete_receta(self, receta_id: str) -> bool:
        """Elimina el archivo ``.md`` de una receta. Devuelve True si existía."""
        path = await self._find_recipe_path(receta_id)
        if path is None:
            return False

        lock = await self._get_lock(path)
        async with lock:
            path = await self._find_recipe_path(receta_id)
            if path is None:
                return False
            await asyncio.to_thread(path.unlink)
        return True

    # --- Tareas domésticas (tareas/*.md) ----------------------------------------

    def _archivos_tareas(self) -> list[Path]:
        """Lista todos los .md bajo tareas/."""
        raiz = self.vault_path / "tareas"
        if not raiz.exists():
            return []
        return sorted(raiz.rglob("*.md"))

    async def _find_task_path(self, task_id: str) -> Optional[Path]:
        """Localiza la ruta del archivo de una tarea por su id."""
        for path in self._archivos_tareas():
            tarea, _ = await self._read_doc(path, Tarea)
            if tarea.id == task_id:
                return path
        return None

    async def get_task(self, task_id: str) -> Optional[Tarea]:
        """Busca una tarea por id."""
        path = await self._find_task_path(task_id)
        if path is None:
            return None
        tarea, _ = await self._read_doc(path, Tarea)
        return tarea

    async def get_task_by_google_id(
        self, google_task_id: str
    ) -> Optional[Tarea]:
        """Busca una tarea local por su id de Google Tasks."""
        for path in self._archivos_tareas():
            tarea, _ = await self._read_doc(path, Tarea)
            if tarea.google_task_id == google_task_id:
                return tarea
        return None

    async def list_tasks(
        self,
        estado: Optional[str] = None,
        asignado_a: Optional[str] = None,
    ) -> list[Tarea]:
        """Devuelve todas las tareas, con filtros opcionales."""
        tareas: list[Tarea] = []
        for path in self._archivos_tareas():
            tarea, _ = await self._read_doc(path, Tarea)
            if estado is not None and tarea.estado != estado:
                continue
            if asignado_a is not None and tarea.asignado_a != asignado_a:
                continue
            tareas.append(tarea)
        return tareas

    async def save_task(self, tarea: Tarea) -> None:
        """Persiste una tarea en su .md preservando el cuerpo (con lock)."""
        path = await self._find_task_path(tarea.id)
        if path is None:
            raise KeyError(f"Tarea no encontrada: {tarea.id}")
        lock = await self._get_lock(path)
        async with lock:
            _, cuerpo = await self._read_doc(path, Tarea)
            await self._write_doc(path, tarea, cuerpo)

    async def create_task(
        self, tarea: Tarea, slug: str, cuerpo: str = ""
    ) -> None:
        """Crea un nuevo archivo de tarea en ``tareas/<slug>.md``.

        Si no se proporciona cuerpo, se usa una plantilla mínima con checklist.
        """
        raiz = self.vault_path / "tareas"
        raiz.mkdir(parents=True, exist_ok=True)
        path = raiz / f"{slug}.md"
        if path.exists():
            raise FileExistsError(f"Ya existe una tarea en {path}")
        if not cuerpo:
            cuerpo = f"# {tarea.titulo}\n\n- [ ] Paso 1\n"
        lock = await self._get_lock(path)
        async with lock:
            await self._write_doc(path, tarea, cuerpo)

    async def delete_task(self, task_id: str) -> bool:
        """Elimina el archivo .md de una tarea. Devuelve True si existía."""
        path = await self._find_task_path(task_id)
        if path is None:
            return False
        lock = await self._get_lock(path)
        async with lock:
            # Releer la ruta por si cambió mientras se adquiría el lock
            path = await self._find_task_path(task_id)
            if path is None:
                return False
            await asyncio.to_thread(path.unlink)
        return True
