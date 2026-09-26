"""Ingesta multimodal de tickets de compra (Fase 3).

El ReceiptParser delega la comprensión del ticket (texto libre/OCR o imagen)
en un cliente LLM INYECTABLE con la interfaz mínima `completar`, lo que
permite testear todo el flujo con fakes sin llamadas reales. Los adaptadores
reales (OpenAI, Anthropic, Gemini y Ollama) importan sus SDKs de forma
perezosa para no obligar a tenerlos todos instalados ni configurados.

El efecto en cascada al registrar una compra vive en la función de módulo
`register_purchase`: por cada ítem actualiza el inventario (nuevo lote FIFO
o creación del .md si el ítem no existía) y acumula el gasto mensual en
gastos/YYYY-MM.md con la E/S atómica del VaultManager.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import unicodedata
import uuid
from datetime import date
from typing import Optional, Protocol, get_args

from pydantic import BaseModel, Field, ValidationError

from backend.categorias import CategoriaManager
from backend.config import Settings
from backend.models import (
    Consumible,
    Ubicacion,
    Unidad,
)
from backend.vault_manager import VaultManager, ahora_utc

logger = logging.getLogger(__name__)

# Catálogos válidos derivados de los Literals de los modelos de Fase 1
UBICACIONES_VALIDAS: frozenset[str] = frozenset(get_args(Ubicacion))
UNIDADES_VALIDAS: frozenset[str] = frozenset(get_args(Unidad))

# Modelos por defecto de cada proveedor cuando AI_MODEL está vacío
_MODELOS_POR_DEFECTO: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2-vision",
}


class ErrorParseoTicket(Exception):
    """La respuesta del LLM no contiene un JSON de ticket válido."""


# --- Modelos de la salida estructurada -----------------------------------------


class ItemTicket(BaseModel):
    """Ítem detectado en un ticket.

    Los campos "sugeridos" y la unidad se admiten como texto libre para ser
    tolerantes con la salida del LLM; se validan contra los catálogos de la
    Fase 1 en el momento de registrar la compra.
    """

    nombre_detectado: str
    item_id_sugerido: Optional[str] = None
    cantidad: float = Field(default=1.0, gt=0)
    unidad: str = "unidades"
    precio_unitario: float = Field(default=0.0, ge=0)
    categoria_sugerida: str = "despensa_seca"
    ubicacion_sugerida: str = "despensa"
    fecha_caducidad_estimada: Optional[date] = None


class TicketParseado(BaseModel):
    """Ticket completo devuelto por el LLM, validado con Pydantic v2."""

    comercio: str = "Desconocido"
    fecha: date = Field(default_factory=date.today)
    total_ticket: float = Field(default=0.0, ge=0.0)
    items: list[ItemTicket] = Field(default_factory=list)


class TicketGasto(BaseModel):
    """Resumen de un ticket dentro del archivo de gastos del mes."""

    comercio: str
    fecha: date
    total: float = Field(ge=0.0)
    items_registrados: list[str] = Field(default_factory=list)
    supermercado: str = "Desconocido"


class GastoMes(BaseModel):
    """Frontmatter de gastos/YYYY-MM.md."""

    mes: str  # formato "YYYY-MM"
    total_mes: float = Field(default=0.0, ge=0.0)
    tickets: list[TicketGasto] = Field(default_factory=list)


class ResultadoItemRegistrado(BaseModel):
    """Resultado del registro de un ítem del ticket."""

    nombre_detectado: str
    item_id: str
    accion: str  # "lote_anadido" o "item_creado"
    cantidad: float
    stock_actual: float
    tachado_de_lista_compra: bool


class ResultadoRegistroCompra(BaseModel):
    """Resultado agregado de register_purchase()."""

    ticket: TicketParseado
    items: list[ResultadoItemRegistrado] = Field(default_factory=list)
    archivo_gasto: str  # ruta relativa, p. ej. "gastos/2026-08.md"
    total_mes: float


# --- Cliente LLM inyectable y adaptadores reales --------------------------------


class ClienteLLM(Protocol):
    """Interfaz mínima de un cliente LLM multimodal (fácil de falsear)."""

    async def completar(
        self,
        prompt: str,
        imagen: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        """Genera texto para el prompt dado, con imagen opcional adjunta."""
        ...


class OpenAIAdapter:
    """Adaptador real a la API de OpenAI (gpt-4o y compatibles)."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        from openai import AsyncOpenAI

        self._cliente = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def completar(
        self,
        prompt: str,
        imagen: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        contenido: list[dict] = [{"type": "text", "text": prompt}]
        if imagen is not None:
            datos = base64.b64encode(imagen).decode("ascii")
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type or 'image/jpeg'};base64,{datos}"
                    },
                }
            )
        respuesta = await self._cliente.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": contenido}],
            temperature=0,
        )
        return respuesta.choices[0].message.content or ""


class AnthropicAdapter:
    """Adaptador real a la API de Anthropic (claude-3.5-sonnet y sup.)."""

    def __init__(
        self, api_key: str, model: str = "claude-3-5-sonnet-latest"
    ) -> None:
        from anthropic import AsyncAnthropic

        self._cliente = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def completar(
        self,
        prompt: str,
        imagen: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        contenido: list[dict] = []
        if imagen is not None:
            contenido.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type or "image/jpeg",
                        "data": base64.b64encode(imagen).decode("ascii"),
                    },
                }
            )
        contenido.append({"type": "text", "text": prompt})
        respuesta = await self._cliente.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": contenido}],
        )
        return "".join(
            bloque.text
            for bloque in respuesta.content
            if bloque.type == "text"
        )


class GeminiAdapter:
    """Adaptador real a la API de Gemini (google-genai)."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        from google import genai

        self._cliente = genai.Client(api_key=api_key)
        self.model = model

    async def completar(
        self,
        prompt: str,
        imagen: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        from google.genai import types

        partes: list = [types.Part.from_text(text=prompt)]
        if imagen is not None:
            partes.append(
                types.Part.from_bytes(
                    data=imagen, mime_type=mime_type or "image/jpeg"
                )
            )
        respuesta = await self._cliente.aio.models.generate_content(
            model=self.model, contents=partes
        )
        return respuesta.text or ""


class OllamaAdapter:
    """Adaptador real a Ollama local (API HTTP /api/generate, sin SDK)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2-vision",
        think: Optional[bool] = None,
        timeout: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        # None = no enviar el parámetro (comportamiento por defecto del modelo);
        # False = desactivar el modo razonamiento (clave en CPU con modelos híbridos).
        self.think = think
        self.timeout = timeout

    async def completar(
        self,
        prompt: str,
        imagen: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> str:
        import httpx

        cuerpo: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if self.think is not None:
            cuerpo["think"] = self.think
        if imagen is not None:
            cuerpo["images"] = [base64.b64encode(imagen).decode("ascii")]
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as cliente:
            respuesta = await cliente.post("/api/generate", json=cuerpo)
            respuesta.raise_for_status()
            return respuesta.json().get("response", "")


def build_llm_client(settings: Settings) -> ClienteLLM:
    """Factoría del cliente LLM según settings.ai_provider.

    Lanza ValueError si el proveedor es desconocido o falta su API key.
    """
    proveedor = (settings.ai_provider or "").strip().lower()
    if proveedor not in _MODELOS_POR_DEFECTO:
        raise ValueError(
            f"AI_PROVIDER no soportado: {settings.ai_provider!r} "
            f"(openai|anthropic|gemini|ollama)"
        )
    modelo = settings.ai_model or _MODELOS_POR_DEFECTO[proveedor]
    if proveedor == "ollama":
        return OllamaAdapter(base_url=settings.ollama_base_url, model=modelo)
    if not settings.ai_api_key:
        raise ValueError(f"AI_API_KEY es obligatoria para {proveedor}")
    if proveedor == "openai":
        return OpenAIAdapter(api_key=settings.ai_api_key, model=modelo)
    if proveedor == "anthropic":
        return AnthropicAdapter(api_key=settings.ai_api_key, model=modelo)
    return GeminiAdapter(api_key=settings.ai_api_key, model=modelo)


# --- Prompt y parseo tolerante ---------------------------------------------------

_PROMPT_TICKET = """Eres el motor de ingesta de tickets de HomeVault AI, un \
sistema de gestión del hogar cuyo inventario vive en archivos Markdown.

Analiza el ticket de compra indicado al final y devuelve EXCLUSIVAMENTE un \
objeto JSON con este esquema exacto (sin texto adicional, sin Markdown):

{{
  "comercio": "nombre del comercio",
  "fecha": "YYYY-MM-DD",
  "total_ticket": 0.0,
  "items": [
    {{
      "nombre_detectado": "nombre del producto",
      "item_id_sugerido": null,
      "cantidad": 1.0,
      "unidad": "unidades",
      "precio_unitario": 0.0,
      "categoria_sugerida": "despensa_seca",
      "ubicacion_sugerida": "despensa",
      "fecha_caducidad_estimada": null
    }}
  ]
}}

Reglas:
- "item_id_sugerido": si el producto coincide claramente con un ítem del \
inventario actual (lista abajo), usa su id exacto; en caso contrario, null.
- "unidad" debe ser una de: {unidades}.
- "categoria_sugerida" debe ser una de: {categorias}.
- "ubicacion_sugerida" debe ser una de: {ubicaciones}.
- "fecha_caducidad_estimada": YYYY-MM-DD estimada según el tipo de producto, \
o null si no aplica (limpieza, recambios, botiquín).
- Responde SOLO con el JSON. Nada de prólogos ni explicaciones.

Inventario actual (id: nombre (categoría, ubicación)):
{inventario}

Ticket a analizar:
{fuente}
"""


def _slugificar(texto: str) -> str:
    """Slug ASCII snake_case a partir del nombre detectado."""
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_str = normalizado.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_str.lower()).strip("_")
    return slug or "item"


class ReceiptParser:
    """Parser de tickets con LLM inyectable y registro en cascada."""

    def __init__(self, vault: VaultManager, llm: ClienteLLM) -> None:
        self.vault = vault
        self.llm = llm

    # --- Construcción del prompt -------------------------------------------------

    async def _construir_prompt(self, fuente: str) -> str:
        """Prompt con el inventario actual para sugerir item_id."""
        items = await self.vault.list_items()
        if items:
            inventario = "\n".join(
                f"- {i.id}: {i.nombre} ({i.categoria}, {i.ubicacion})"
                for i in items
            )
        else:
            inventario = "(inventario vacío)"
        categorias = [
            c.id for c in self.vault.categoria_manager.listar()
        ] or ["despensa_seca"]
        return _PROMPT_TICKET.format(
            unidades=", ".join(sorted(UNIDADES_VALIDAS)),
            categorias=", ".join(sorted(categorias)),
            ubicaciones=", ".join(sorted(UBICACIONES_VALIDAS)),
            inventario=inventario,
            fuente=fuente,
        )

    # --- Parseo -------------------------------------------------------------------

    async def parse_ticket_from_text(
        self,
        texto: str,
        comercio: Optional[str] = None,
        total: Optional[float] = None,
    ) -> TicketParseado:
        """Parsea un ticket descrito en lenguaje natural (o ya transcrito)."""
        lineas = [f"Texto del ticket:\n{texto}"]
        if comercio:
            lineas.append(f"Comercio (ya conocido): {comercio}")
        if total is not None:
            lineas.append(f"Total del ticket (ya conocido): {total}")
        respuesta = await self.llm.completar(
            await self._construir_prompt("\n".join(lineas))
        )
        ticket = self._validar_ticket(respuesta)
        # Los datos ya conocidos del llamador tienen prioridad si el LLM
        # no los extrajo
        if comercio and ticket.comercio == "Desconocido":
            ticket.comercio = comercio
        if total is not None and ticket.total_ticket == 0.0:
            ticket.total_ticket = total
        return ticket

    async def parse_ticket_from_image(
        self, imagen: bytes, mime_type: str = "image/jpeg"
    ) -> TicketParseado:
        """Parsea un ticket a partir de su imagen (multimodal)."""
        respuesta = await self.llm.completar(
            await self._construir_prompt(
                "Analiza la imagen del ticket de compra adjunta."
            ),
            imagen=imagen,
            mime_type=mime_type,
        )
        return self._validar_ticket(respuesta)

    @classmethod
    def _validar_ticket(cls, respuesta: str) -> TicketParseado:
        """Extrae el JSON de la respuesta y lo valida como TicketParseado."""
        datos = cls._extraer_json(respuesta)
        try:
            return TicketParseado.model_validate(datos)
        except ValidationError as exc:
            raise ErrorParseoTicket(
                f"El JSON del ticket no cumple el esquema: {exc}"
            ) from exc

    @staticmethod
    def _extraer_json(respuesta: str) -> dict:
        """Extrae el objeto JSON de la respuesta con tolerancia.

        Soporta JSON directo, bloques con fences Markdown (```json ... ```)
        y JSON envuelto en texto libre. Lanza ErrorParseoTicket si no hay
        un objeto JSON válido.
        """
        texto = respuesta.strip()
        try:
            datos = json.loads(texto)
            if isinstance(datos, dict):
                return datos
        except json.JSONDecodeError:
            pass
        match = re.search(
            r"```(?:json)?\s*\n?(?P<bloque>.*?)```", texto, re.DOTALL
        )
        if match:
            try:
                datos = json.loads(match.group("bloque").strip())
                if isinstance(datos, dict):
                    return datos
            except json.JSONDecodeError:
                pass
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio != -1 and fin > inicio:
            try:
                datos = json.loads(texto[inicio : fin + 1])
                if isinstance(datos, dict):
                    return datos
            except json.JSONDecodeError:
                pass
        raise ErrorParseoTicket(
            "La respuesta del LLM no contiene un objeto JSON válido"
        )

    # --- Registro en cascada --------------------------------------------------------

    async def register_purchase(
        self, ticket: TicketParseado
    ) -> ResultadoRegistroCompra:
        """Registra el ticket completo (delega en la función de módulo)."""
        return await register_purchase(self.vault, ticket)


def build_receipt_parser(vault: VaultManager, settings: Settings) -> ReceiptParser:
    """Factoría: ReceiptParser con el cliente LLM real según settings."""
    return ReceiptParser(vault, build_llm_client(settings))


# --- Extracción de precio desde imagen --------------------------------------------


_PROMPT_PRECIO_IMAGEN = (
    "Devuelve SOLO el precio total visible en esta imagen como número decimal. "
    "Si no hay precio, devuelve null."
)


async def extraer_precio_desde_imagen(
    parser: ReceiptParser,
    imagen_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Optional[float]:
    """Envía una imagen al LLM y devuelve el precio total detectado.

    El prompt fuerza una respuesta numérica o null. Se aplican heurísticas
    básicas para limpiar símbolos de moneda y normalizar separadores decimales.

    Args:
        parser: ReceiptParser con un cliente LLM inyectable.
        imagen_bytes: Contenido binario de la imagen.
        mime_type: Tipo MIME de la imagen.

    Returns:
        Precio como float si se detecta y es mayor que 0, None en cualquier
        otro caso.
    """
    respuesta = await parser.llm.completar(
        _PROMPT_PRECIO_IMAGEN,
        imagen=imagen_bytes,
        mime_type=mime_type,
    )
    texto = respuesta.strip()
    if not texto or texto.lower() in ("null", "none"):
        return None

    # Elimina símbolos de moneda comunes y espacios, conservando dígitos y
    # separadores decimales.
    limpio = re.sub(r"[^\d.,]", "", texto)
    if not limpio:
        return None

    # Normaliza separadores decimales: el último separador es el decimal.
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        # Puede ser decimal o separador de miles sin decimales. Asumimos que
        # una sola coma con dos dígitos a la derecha es decimal; en otro caso,
        # si hay más de dos decimales, se trata como separador de miles.
        partes = limpio.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")

    try:
        valor = float(limpio)
    except ValueError:
        return None
    return valor if valor > 0 else None


# --- Efecto en cascada del registro -----------------------------------------------


def _cuerpo_gasto(gasto: GastoMes) -> str:
    """Cuerpo Markdown de gastos/YYYY-MM.md: tabla con todos los tickets."""
    lineas = [
        f"# Gastos de {gasto.mes}",
        "",
        f"Total del mes: {gasto.total_mes:.2f} EUR",
        "",
        "| Fecha | Comercio | Total (EUR) | Ítems |",
        "| --- | --- | --- | --- |",
    ]
    for ticket in gasto.tickets:
        items = ", ".join(ticket.items_registrados) or "-"
        lineas.append(
            f"| {ticket.fecha.isoformat()} | {ticket.comercio} "
            f"| {ticket.total:.2f} | {items} |"
        )
    return "\n".join(lineas) + "\n"


async def _registrar_gasto(
    vault: VaultManager,
    ticket: TicketParseado,
    items_registrados: list[str],
    supermercado: Optional[str] = None,
) -> GastoMes:
    """Acumula el ticket en gastos/YYYY-MM.md (crea el archivo si falta)."""
    mes = ticket.fecha.strftime("%Y-%m")
    ruta = vault.vault_path / "gastos" / f"{mes}.md"
    lock = await vault._get_lock(ruta)
    async with lock:
        if ruta.exists():
            gasto, _ = await vault._read_doc(ruta, GastoMes)
        else:
            gasto = GastoMes(mes=mes)
        gasto.tickets.append(
            TicketGasto(
                comercio=ticket.comercio,
                fecha=ticket.fecha,
                total=ticket.total_ticket,
                items_registrados=items_registrados,
                supermercado=supermercado or ticket.comercio or "Desconocido",
            )
        )
        gasto.total_mes = round(sum(t.total for t in gasto.tickets), 2)
        await vault._write_doc(ruta, gasto, _cuerpo_gasto(gasto))
    return gasto


def _normalizar_categoria(
    categoria: str, manager: CategoriaManager
) -> str:
    """Devuelve la categoría si existe en el manager; si no, ``despensa_seca``."""
    if manager.existe(categoria):
        return categoria
    return "despensa_seca"


async def _crear_item_desde_ticket(
    vault: VaultManager, item_ticket: ItemTicket
) -> Consumible:
    """Crea el .md de un consumible nuevo con el esquema exacto de Fase 1.

    El ítem nace con stock 0 (la compra se añade después como lote FIFO con
    add_purchase), stock_minimo 1 y auto_lista_compra activado. Los campos
    sugeridos por el LLM que no encajen en los catálogos de Fase 1 caen a
    valores seguros por defecto.
    """
    slug = _slugificar(item_ticket.nombre_detectado)
    item_id = f"item_{slug}"
    if await vault.get_item(item_id) is not None:
        item_id = f"item_{slug}_{uuid.uuid4().hex[:6]}"
    ubicacion = (
        item_ticket.ubicacion_sugerida
        if item_ticket.ubicacion_sugerida in UBICACIONES_VALIDAS
        else "despensa"
    )
    categoria = _normalizar_categoria(
        item_ticket.categoria_sugerida, vault.categoria_manager
    )
    unidad = (
        item_ticket.unidad
        if item_ticket.unidad in UNIDADES_VALIDAS
        else "unidades"
    )
    nuevo = Consumible(
        id=item_id,
        nombre=item_ticket.nombre_detectado,
        categoria=categoria,
        ubicacion=ubicacion,
        stock_actual=0.0,
        stock_minimo=1.0,
        unidad=unidad,
        precio_unitario_estimado=item_ticket.precio_unitario or None,
        lotes=[],
        auto_lista_compra=True,
        ultima_actualizacion=ahora_utc(),
    )
    ruta = vault.vault_path / "inventario" / ubicacion / f"{item_id}.md"
    cuerpo = (
        f"# {item_ticket.nombre_detectado}\n\n"
        "Creado automáticamente desde un ticket de compra.\n"
    )
    await vault._write_doc(ruta, nuevo, cuerpo)
    logger.info("Ítem creado desde ticket: %s (%s)", item_id, ruta)
    return nuevo


async def register_purchase(
    vault: VaultManager,
    ticket: TicketParseado,
    supermercado: Optional[str] = None,
) -> ResultadoRegistroCompra:
    """Registra un ticket parseado con efecto en cascada sobre el vault.

    Por cada ítem: si item_id_sugerido existe en el vault se registra la
    compra como nuevo lote FIFO (tachándolo de listas/compra.md si estaba
    pendiente); si no existe, se crea su .md en inventario/<ubicacion>/ y
    después se añade el lote. Al final, el gasto se acumula en
    gastos/YYYY-MM.md.

    Args:
        vault: Gestor del vault Markdown.
        ticket: Ticket parseado por el LLM.
        supermercado: Nombre del supermercado donde se realizó la compra.
            Si no se indica, se usa ``ticket.comercio``.
    """
    supermercado_final = supermercado or ticket.comercio or "Desconocido"
    resultados: list[ResultadoItemRegistrado] = []
    for item_ticket in ticket.items:
        existente: Optional[Consumible] = None
        if item_ticket.item_id_sugerido:
            existente = await vault.get_item(item_ticket.item_id_sugerido)
        if existente is not None:
            item_id = existente.id
            accion = "lote_anadido"
        else:
            nuevo = await _crear_item_desde_ticket(vault, item_ticket)
            item_id = nuevo.id
            accion = "item_creado"
        compra = await vault.add_purchase(
            item_id,
            item_ticket.cantidad,
            item_ticket.precio_unitario,
            item_ticket.fecha_caducidad_estimada,
            supermercado=supermercado_final,
        )
        resultados.append(
            ResultadoItemRegistrado(
                nombre_detectado=item_ticket.nombre_detectado,
                item_id=item_id,
                accion=accion,
                cantidad=item_ticket.cantidad,
                stock_actual=compra.stock_actual,
                tachado_de_lista_compra=compra.tachado_de_lista_compra,
            )
        )
    gasto = await _registrar_gasto(
        vault, ticket, [r.item_id for r in resultados], supermercado_final
    )
    return ResultadoRegistroCompra(
        ticket=ticket,
        items=resultados,
        archivo_gasto=f"gastos/{gasto.mes}.md",
        total_mes=gasto.total_mes,
    )
