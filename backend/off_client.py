"""Cliente de Open Food Facts para escaneo de códigos de barras (Fase 4b).

El OFFClient consulta la API pública v2 de Open Food Facts con un cliente
httpx ASYNC INYECTABLE, lo que permite testear todo el flujo con
httpx.MockTransport o con fakes sin red. Las respuestas (también los "no
encontrado") se cachean en memoria con un TTL configurable para no martillear
la API pública cuando se re-escanea el mismo producto.

La función de módulo `map_off_to_consumible` traduce la respuesta cruda de
OFF a un ProductoOFF (nombre, marcas, alérgenos, kcal/proteínas por 100 g e
imagen), que es lo que el router de barcode usa para crear el .md del
inventario con el esquema exacto de Consumible.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

OFF_BASE_URL = "https://world.openfoodfacts.org"
OFF_TIMEOUT_S = 10.0
OFF_CACHE_TTL_S = 3600.0
OFF_USER_AGENT = "HomeVaultAI/0.4 (quantum-homelab; escaneo de despensa)"


class ProductoOFF(BaseModel):
    """Datos normalizados de un producto de Open Food Facts."""

    ean: str
    nombre: str
    marcas: list[str] = Field(default_factory=list)
    alergenos: list[str] = Field(default_factory=list)
    kcal_100g: Optional[float] = None
    proteinas_100g: Optional[float] = None
    imagen_url: Optional[str] = None


class OFFClient:
    """Cliente async de Open Food Facts con cache en memoria TTL.

    El cliente httpx es inyectable: en producción se crea uno real y en tests
    se pasa un AsyncClient con MockTransport (o un fake con el mismo método
    `get`), sin conexiones reales.
    """

    def __init__(
        self,
        cliente_http: Optional[httpx.AsyncClient] = None,
        base_url: str = OFF_BASE_URL,
        timeout_s: float = OFF_TIMEOUT_S,
        cache_ttl_s: float = OFF_CACHE_TTL_S,
        user_agent: str = OFF_USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self.user_agent = user_agent
        self._cliente = cliente_http
        # Cache: ean -> (instante monotónico, producto o None si no existe)
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._cache_lock = asyncio.Lock()

    async def _get_cliente(self) -> httpx.AsyncClient:
        """Devuelve el cliente httpx, creándolo perezosamente si falta."""
        if self._cliente is None:
            self._cliente = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_s,
                headers={"User-Agent": self.user_agent},
            )
        return self._cliente

    async def aclose(self) -> None:
        """Cierra el cliente httpx si lo creó el propio OFFClient."""
        if self._cliente is not None:
            await self._cliente.aclose()
            self._cliente = None

    def _cache_valido(self, ean: str) -> tuple[bool, Optional[dict]]:
        """Devuelve (hit, producto) si el EAN tiene una entrada de cache viva."""
        entrada = self._cache.get(ean)
        if entrada is None:
            return False, None
        instante, producto = entrada
        if time.monotonic() - instante > self.cache_ttl_s:
            return False, None
        return True, producto

    async def get_product(self, ean: str) -> Optional[dict]:
        """Devuelve el dict "product" de OFF para un EAN, o None si no existe.

        Cachea tanto aciertos como "no encontrado" durante cache_ttl_s.
        Lanza httpx.HTTPError ante errores de red o HTTP inesperados.
        """
        hit, producto = self._cache_valido(ean)
        if hit:
            return producto

        cliente = await self._get_cliente()
        url = f"{self.base_url}/api/v2/product/{ean}.json"
        respuesta = await cliente.get(url)
        if respuesta.status_code == 404:
            producto = None
        else:
            respuesta.raise_for_status()
            datos = respuesta.json()
            # La API v2 devuelve status 0 cuando el producto no existe
            producto = datos.get("product") if datos.get("status") == 1 else None

        async with self._cache_lock:
            self._cache[ean] = (time.monotonic(), producto)
        return producto


def build_off_client() -> OFFClient:
    """Factoría del cliente real según variables de entorno OFF_*."""
    return OFFClient(
        base_url=os.environ.get("OFF_BASE_URL", OFF_BASE_URL),
        timeout_s=float(os.environ.get("OFF_TIMEOUT_S", OFF_TIMEOUT_S)),
        cache_ttl_s=float(os.environ.get("OFF_CACHE_TTL_S", OFF_CACHE_TTL_S)),
        user_agent=os.environ.get("OFF_USER_AGENT", OFF_USER_AGENT),
    )


# --- Mapeo de la respuesta OFF a datos normalizados ------------------------------


def _limpiar_alergeno(etiqueta: str) -> str:
    """Normaliza una etiqueta de alérgeno OFF ("en:milk" -> "milk")."""
    texto = etiqueta.strip()
    if ":" in texto:
        texto = texto.split(":", 1)[1]
    return texto.replace("-", " ").strip()


def _extraer_float(nutriments: dict, claves: tuple[str, ...]) -> Optional[float]:
    """Primera clave numérica disponible del dict de nutrimientos de OFF."""
    for clave in claves:
        valor = nutriments.get(clave)
        if isinstance(valor, (int, float)):
            return round(float(valor), 2)
    return None


def map_off_to_consumible(data: dict, ean: str) -> ProductoOFF:
    """Traduce la respuesta de OFF a los datos normalizados del producto.

    `data` puede ser la respuesta completa de la API v2 (con clave "product")
    o directamente el dict del producto. Tolera campos ausentes: el nombre
    cae a "Producto <ean>" y los opcionales quedan vacíos o None.
    """
    producto = data.get("product", data)
    if not isinstance(producto, dict):
        producto = {}

    nombre = (
        producto.get("product_name")
        or producto.get("generic_name")
        or f"Producto {ean}"
    ).strip() or f"Producto {ean}"

    marcas = [
        marca.strip()
        for marca in str(producto.get("brands") or "").split(",")
        if marca.strip()
    ]

    alergenos_raw = producto.get("allergens_tags") or []
    if not alergenos_raw:
        alergenos_raw = [
            a for a in str(producto.get("allergens") or "").split(",") if a
        ]
    alergenos = sorted(
        {_limpiar_alergeno(a) for a in alergenos_raw if _limpiar_alergeno(a)}
    )

    nutriments = producto.get("nutriments") or {}
    kcal = _extraer_float(nutriments, ("energy-kcal_100g", "energy-kcal"))
    proteinas = _extraer_float(nutriments, ("proteins_100g",))

    imagen = (
        producto.get("image_front_url")
        or producto.get("image_url")
        or producto.get("image_small_url")
    )

    return ProductoOFF(
        ean=ean,
        nombre=nombre,
        marcas=marcas,
        alergenos=alergenos,
        kcal_100g=kcal,
        proteinas_100g=proteinas,
        imagen_url=imagen,
    )
