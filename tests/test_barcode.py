"""Tests del OFFClient, map_off_to_consumible y el router de barcode (Fase 4b)."""

from __future__ import annotations

import time
from datetime import date

import frontmatter
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ai_vision_parser import (
    ReceiptParser,
    extraer_precio_desde_imagen,
)
from backend.local_barcodes import LocalBarcodeManager
from backend.models import Consumible
from backend.off_client import (
    OFFClient,
    ProductoOFF,
    map_off_to_consumible,
)
from backend.routers.barcode import router as barcode_router
from backend.vault_manager import VaultManager

EAN_NUEVO = "8412345678905"
EAN_EXISTENTE = "8411111111111"  # yogur del fixture vault_poblado
EAN_DESCONOCIDO = "9999999999999"

# Respuesta típica de la API v2 de Open Food Facts para un producto existente
RESPUESTA_OFF_ENCONTRADA = {
    "code": EAN_NUEVO,
    "status": 1,
    "product": {
        "product_name": "Atún claro en aceite de oliva",
        "brands": "Campos, MarcaBlanca",
        "allergens": "en:fish, en:molluscs",
        "allergens_tags": ["en:fish"],
        "nutriments": {
            "energy-kcal_100g": 189,
            "proteins_100g": 24.5,
        },
        "image_front_url": "https://images.off.example/atun.jpg",
    },
}

RESPUESTA_OFF_NO_ENCONTRADA = {"code": EAN_DESCONOCIDO, "status": 0}


class FakeOFFClient:
    """Fake del OFFClient: dict ean -> producto (o None), registra llamadas."""

    def __init__(self, productos: dict | None = None) -> None:
        self.productos = dict(productos or {})
        self.llamadas: list[str] = []

    async def get_product(self, ean: str) -> dict | None:
        self.llamadas.append(ean)
        return self.productos.get(ean)


def _app_test(
    vault: VaultManager,
    off_client,
    parser: ReceiptParser | None = None,
) -> FastAPI:
    """App FastAPI mínima con el router de barcode y estado inyectado."""
    app = FastAPI()
    app.state.vault = vault
    app.state.off_client = off_client
    app.state.receipt_parser = parser
    app.include_router(barcode_router)
    return app


# --- OFFClient con MockTransport (sin red real) -----------------------------------


def _cliente_mock(handler) -> OFFClient:
    """OFFClient con un AsyncClient de httpx interceptado por MockTransport."""
    return OFFClient(cliente_http=httpx.AsyncClient(transport=handler))


async def test_off_client_producto_encontrado() -> None:
    """GET a la API v2 devuelve el dict del producto cuando status es 1."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert f"/api/v2/product/{EAN_NUEVO}.json" in str(request.url)
        return httpx.Response(200, json=RESPUESTA_OFF_ENCONTRADA)

    cliente = _cliente_mock(httpx.MockTransport(handler))
    producto = await cliente.get_product(EAN_NUEVO)
    assert producto == RESPUESTA_OFF_ENCONTRADA["product"]


async def test_off_client_producto_no_encontrado() -> None:
    """status 0 de OFF se traduce a None (también un 404 HTTP)."""

    def handler_status0(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RESPUESTA_OFF_NO_ENCONTRADA)

    cliente = _cliente_mock(httpx.MockTransport(handler_status0))
    assert await cliente.get_product(EAN_DESCONOCIDO) is None

    def handler_404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    cliente_404 = _cliente_mock(httpx.MockTransport(handler_404))
    assert await cliente_404.get_product(EAN_DESCONOCIDO) is None


async def test_off_client_cache_ttl() -> None:
    """La segunda consulta del mismo EAN no repite la petición HTTP."""
    peticiones = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, json=RESPUESTA_OFF_ENCONTRADA)

    cliente = _cliente_mock(httpx.MockTransport(handler))
    primero = await cliente.get_product(EAN_NUEVO)
    segundo = await cliente.get_product(EAN_NUEVO)
    assert primero == segundo
    assert peticiones == 1

    # Con TTL agotado vuelve a llamar a la API
    cliente_ttl = OFFClient(
        cliente_http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cache_ttl_s=0.05,
    )
    await cliente_ttl.get_product(EAN_NUEVO)
    time.sleep(0.06)
    await cliente_ttl.get_product(EAN_NUEVO)
    assert peticiones == 3


async def test_off_client_cachea_no_encontrado() -> None:
    """Los "no encontrado" también se cachean dentro del TTL."""
    peticiones = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, json=RESPUESTA_OFF_NO_ENCONTRADA)

    cliente = _cliente_mock(httpx.MockTransport(handler))
    assert await cliente.get_product(EAN_DESCONOCIDO) is None
    assert await cliente.get_product(EAN_DESCONOCIDO) is None
    assert peticiones == 1


async def test_off_client_propaga_error_http() -> None:
    """Un 500 de OFF se propaga como httpx.HTTPStatusError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    cliente = _cliente_mock(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await cliente.get_product(EAN_NUEVO)


# --- map_off_to_consumible -----------------------------------------------------------


def test_map_off_completo() -> None:
    """Extrae nombre, marcas, alérgenos, nutrimientos e imagen."""
    producto = map_off_to_consumible(RESPUESTA_OFF_ENCONTRADA, EAN_NUEVO)
    assert producto.ean == EAN_NUEVO
    assert producto.nombre == "Atún claro en aceite de oliva"
    assert producto.marcas == ["Campos", "MarcaBlanca"]
    # allergens_tags tiene prioridad y se limpia el prefijo "en:"
    assert producto.alergenos == ["fish"]
    assert producto.kcal_100g == 189.0
    assert producto.proteinas_100g == 24.5
    assert producto.imagen_url == "https://images.off.example/atun.jpg"


def test_map_off_minimo_y_tolerante() -> None:
    """Sin campos opcionales: nombre de respaldo y alérgenos del string crudo."""
    producto = map_off_to_consumible({"product": {}}, EAN_NUEVO)
    assert producto == ProductoOFF(
        ean=EAN_NUEVO, nombre=f"Producto {EAN_NUEVO}"
    )
    # Sin allergens_tags usa el string "allergens" y limpia prefijos/guiones
    solo_alergenos = map_off_to_consumible(
        {"product": {"allergens": "en:milk,en:tree-nuts"}}, EAN_NUEVO
    )
    assert solo_alergenos.alergenos == ["milk", "tree nuts"]


# --- Router GET /api/barcode/{ean} -----------------------------------------------------


def test_get_barcode_item_ya_existente(
    vault_poblado: VaultManager,
) -> None:
    """Si el EAN ya está en el vault se devuelve el ítem sin llamar a OFF."""
    fake_off = FakeOFFClient()
    cliente = TestClient(_app_test(vault_poblado, fake_off))

    respuesta = cliente.get(f"/api/barcode/{EAN_EXISTENTE}")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["creado"] is False
    assert datos["origen"] == "vault"
    assert datos["item"]["id"] == "item_test_01"
    assert datos["item"]["ean_barcode"] == EAN_EXISTENTE
    assert fake_off.llamadas == []


def test_get_barcode_crea_item_desde_off(vault: VaultManager) -> None:
    """EAN nuevo: consulta OFF y crea el .md en inventario/despensa."""
    fake_off = FakeOFFClient({EAN_NUEVO: RESPUESTA_OFF_ENCONTRADA["product"]})
    cliente = TestClient(_app_test(vault, fake_off))

    respuesta = cliente.get(f"/api/barcode/{EAN_NUEVO}")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["creado"] is True
    assert datos["origen"] == "off"
    item = datos["item"]
    assert item["id"] == "item_atun_claro_en_aceite_de_oliva"
    assert item["ean_barcode"] == EAN_NUEVO
    assert item["stock_actual"] == 0.0
    assert item["stock_minimo"] == 1.0
    assert item["auto_lista_compra"] is True
    assert datos["producto_off"]["marcas"] == ["Campos", "MarcaBlanca"]
    assert fake_off.llamadas == [EAN_NUEVO]

    # El archivo existe con el esquema de Consumible y la ficha en el cuerpo
    ruta = (
        vault.vault_path
        / "inventario"
        / "despensa"
        / f"{item['id']}.md"
    )
    assert ruta.exists()
    post = frontmatter.loads(ruta.read_text(encoding="utf-8"))
    modelo = Consumible.model_validate(post.metadata)
    assert modelo.id == item["id"]
    assert "**Marca:** Campos, MarcaBlanca" in post.content
    assert "- fish" in post.content
    assert "| Energía | 189 kcal |" in post.content
    assert "| Proteínas | 24.5 g |" in post.content
    assert "https://images.off.example/atun.jpg" in post.content

    # Un segundo escaneo resuelve ya desde el vault
    segunda = cliente.get(f"/api/barcode/{EAN_NUEVO}")
    assert segunda.json()["creado"] is False
    assert fake_off.llamadas == [EAN_NUEVO]


def test_get_barcode_crea_item_desde_local(
    vault: VaultManager,
) -> None:
    """EAN en base local: crea el ítem sin llamar a OFF."""
    manager = LocalBarcodeManager(vault.vault_path)
    barcode = manager.listar()[0]
    cliente = TestClient(_app_test(vault, FakeOFFClient()))

    respuesta = cliente.get(f"/api/barcode/{barcode.ean}")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["origen"] == "local"
    assert datos["creado"] is True
    assert datos["item"]["ean_barcode"] == barcode.ean
    assert datos["item"]["nombre"] == barcode.nombre
    assert datos["item"]["ubicacion"] == barcode.ubicacion


def test_get_barcode_no_encontrado_devuelve_sugerencias(
    vault_poblado: VaultManager,
) -> None:
    """EAN desconocido devuelve 404 estructurado con sugerencias de fusión."""
    fake_off = FakeOFFClient({EAN_DESCONOCIDO: None})
    cliente = TestClient(_app_test(vault_poblado, fake_off))

    respuesta = cliente.get(f"/api/barcode/{EAN_DESCONOCIDO}")

    assert respuesta.status_code == 404
    datos = respuesta.json()
    assert datos["detail"] == "Producto no encontrado"
    assert datos["ean"] == EAN_DESCONOCIDO
    sugerencias = datos["sugerencias"]
    assert len(sugerencias) == 2
    # Ordenados por nombre
    assert sugerencias[0]["nombre"] == "Arroz integral"
    assert sugerencias[0]["id"] == "item_conc_01"
    assert sugerencias[1]["nombre"] == "Yogur natural"
    assert sugerencias[1]["id"] == "item_test_01"


def test_get_barcode_sin_cliente_off_503(vault: VaultManager) -> None:
    """Sin OFFClient configurado, un EAN desconocido responde 503."""
    app = FastAPI()
    app.state.vault = vault
    app.include_router(barcode_router)
    respuesta = TestClient(app).get(f"/api/barcode/{EAN_NUEVO}")
    assert respuesta.status_code == 503


def test_get_barcode_error_off_502(vault: VaultManager) -> None:
    """Un error de red/HTTP de OFF se traduce en 502."""

    class OffRoto:
        async def get_product(self, ean: str) -> dict | None:
            raise httpx.ConnectError("sin red")

    cliente = TestClient(_app_test(vault, OffRoto()))
    respuesta = cliente.get(f"/api/barcode/{EAN_NUEVO}")
    assert respuesta.status_code == 502


# --- Router POST /api/barcode/consume ---------------------------------------------------


def test_consume_por_ean_ok(vault_poblado: VaultManager) -> None:
    """Consume por EAN descuenta stock vía el motor FIFO del VaultManager."""
    cliente = TestClient(_app_test(vault_poblado, FakeOFFClient()))

    respuesta = cliente.post(
        "/api/barcode/consume", json={"ean": EAN_EXISTENTE, "cantidad": 3}
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert "resultado" in datos
    resultado = datos["resultado"]
    assert resultado["item_id"] == "item_test_01"
    # FIFO: 2 del lote próximo a caducar + 1 del siguiente; el stock_actual
    # no se toca mientras los lotes cubren el consumo (semántica de Fase 1)
    assert resultado["cantidad_consumida_lotes"] == 3.0
    assert resultado["stock_actual"] == 6.0
    assert "quitado_de_lista" in datos


def test_consume_por_ean_cantidad_por_defecto(
    vault_poblado: VaultManager,
) -> None:
    """Sin cantidad en el cuerpo se consume exactamente 1 unidad."""
    cliente = TestClient(_app_test(vault_poblado, FakeOFFClient()))
    respuesta = cliente.post("/api/barcode/consume", json={"ean": EAN_EXISTENTE})
    assert respuesta.status_code == 200
    resultado = respuesta.json()["resultado"]
    assert resultado["cantidad_solicitada"] == 1.0
    assert resultado["cantidad_consumida_lotes"] == 1.0
    assert resultado["stock_actual"] == 6.0


def test_consume_por_ean_desconocido_404(vault_poblado: VaultManager) -> None:
    """Un EAN que no está en el vault responde 404."""
    cliente = TestClient(_app_test(vault_poblado, FakeOFFClient()))
    respuesta = cliente.post(
        "/api/barcode/consume", json={"ean": EAN_DESCONOCIDO}
    )
    assert respuesta.status_code == 404


def test_consume_quita_de_lista_compra(
    vault_poblado: VaultManager,
) -> None:
    """Al consumir, el ítem se tacha de la lista de la compra."""
    vault = vault_poblado
    # Se escribe la lista directamente para evitar awaits en test síncrono.
    ruta_lista = vault.vault_path / "listas" / "compra.md"
    ruta_lista.write_text(
        "# Lista de la compra\n\n"
        "- [ ] Yogur natural <!-- item_id:item_test_01; "
        "cantidad:4.0; unidad:unidades; categoria:lacteos -->\n",
        encoding="utf-8",
    )
    cliente = TestClient(_app_test(vault, FakeOFFClient()))

    respuesta = cliente.post(
        "/api/barcode/consume", json={"ean": EAN_EXISTENTE, "cantidad": 1}
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["quitado_de_lista"] == 1
    assert ruta_lista.read_text(encoding="utf-8").startswith(
        "# Lista de la compra\n\n- [x] Yogur natural"
    )


# --- Router POST /api/barcode/register --------------------------------------------------


def _bytes_imagen_dummy() -> bytes:
    """Bytes mínimos que pasan como imagen JPEG para los tests multipart."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


def test_registro_manual_crea_item_con_foto(vault: VaultManager) -> None:
    """El registro manual crea un Consumible con foto y un primer lote."""
    cliente = TestClient(_app_test(vault, FakeOFFClient()))
    ean = "8410000000001"
    datos = {
        "ean": ean,
        "nombre": "Leche entera",
        "categoria": "lacteos",
        "ubicacion": "nevera",
        "unidad": "litros",
        "precio": "1.20",
        "cantidad": "2",
    }
    archivos = {
        "foto_producto": ("leche.jpg", _bytes_imagen_dummy(), "image/jpeg"),
    }

    respuesta = cliente.post("/api/barcode/register", data=datos, files=archivos)

    assert respuesta.status_code == 200
    item = respuesta.json()
    assert item["ean_barcode"] == ean
    assert item["nombre"] == "Leche entera"
    assert item["categoria"] == "lacteos"
    assert item["ubicacion"] == "nevera"
    assert item["unidad"] == "litros"
    assert item["stock_actual"] == 2.0
    assert item["stock_minimo"] == 1.0
    assert item["auto_lista_compra"] is True

    ruta_item = vault.vault_path / "inventario" / "nevera" / f"{item['id']}.md"
    assert ruta_item.exists()
    post = frontmatter.loads(ruta_item.read_text(encoding="utf-8"))
    assert Consumible.model_validate(post.metadata)
    assert "![Foto del producto]" in post.content
    assert f"assets/productos/{item['id']}.jpg" in post.content

    ruta_foto = vault.vault_path / "assets" / "productos" / f"{item['id']}.jpg"
    assert ruta_foto.exists()


def test_registro_manual_guarda_supermercado(vault: VaultManager) -> None:
    """El registro manual puede almacenar el supermercado en el lote."""
    cliente = TestClient(_app_test(vault, FakeOFFClient()))
    ean = "8410000000007"
    datos = {
        "ean": ean,
        "nombre": "Leche entera",
        "categoria": "lacteos",
        "ubicacion": "nevera",
        "unidad": "litros",
        "precio": "1.20",
        "cantidad": "2",
        "supermercado": "Carrefour",
    }

    respuesta = cliente.post("/api/barcode/register", data=datos)

    assert respuesta.status_code == 200
    item = respuesta.json()
    assert item["stock_actual"] == 2.0
    ruta = vault.vault_path / "inventario" / "nevera" / f"{item['id']}.md"
    post = frontmatter.loads(ruta.read_text(encoding="utf-8"))
    assert post.metadata["lotes"][0]["supermercado"] == "Carrefour"


def test_registro_manual_categoria_invalida_400(vault: VaultManager) -> None:
    """Una categoría fuera del catálogo devuelve 400."""
    cliente = TestClient(_app_test(vault, FakeOFFClient()))
    datos = {
        "ean": "8410000000002",
        "nombre": "Producto raro",
        "categoria": "inexistente",
    }
    respuesta = cliente.post("/api/barcode/register", data=datos)
    assert respuesta.status_code == 400
    assert "Categoría no válida" in respuesta.json()["detail"]


def test_fusion_actualiza_ean_y_stock(
    vault_poblado: VaultManager,
    fake_llm,
) -> None:
    """Fusionar un EAN con un ítem existente actualiza su código y stock."""
    vault = vault_poblado
    parser = ReceiptParser(vault, fake_llm)
    ean_nuevo = "8410000000003"
    cliente = TestClient(_app_test(vault_poblado, FakeOFFClient(), parser))

    respuesta = cliente.post(
        "/api/barcode/register",
        data={
            "ean": ean_nuevo,
            "nombre": "Yogur natural",
            "merge_target_id": "item_test_01",
            "cantidad": "3",
            "precio": "0.45",
        },
    )

    assert respuesta.status_code == 200
    item = respuesta.json()
    assert item["id"] == "item_test_01"
    assert item["ean_barcode"] == ean_nuevo
    assert item["stock_actual"] == 9.0  # 6 originales + 3 del nuevo lote

    ruta = vault.vault_path / "inventario" / "nevera" / "yogur.md"
    post = frontmatter.loads(ruta.read_text(encoding="utf-8"))
    assert post.metadata["ean_barcode"] == ean_nuevo
    # El lote añadado aparece en el historial de lotes
    assert len(post.metadata["lotes"]) == 3


def test_fusion_con_foto_precio_extraido_por_ia(
    vault_poblado: VaultManager,
    fake_llm,
) -> None:
    """La foto del precio puede sobrescribir el precio mediante el LLM."""
    fake_llm.respuestas.append("2,50")
    vault = vault_poblado
    parser = ReceiptParser(vault, fake_llm)
    cliente = TestClient(_app_test(vault, FakeOFFClient(), parser))

    respuesta = cliente.post(
        "/api/barcode/register",
        data={
            "ean": "8410000000004",
            "nombre": "Yogur natural",
            "merge_target_id": "item_test_01",
            "cantidad": "1",
            "precio": "0.45",
        },
        files={
            "foto_precio": ("precio.jpg", _bytes_imagen_dummy(), "image/jpeg"),
        },
    )

    assert respuesta.status_code == 200
    item = respuesta.json()
    assert item["precio_unitario_estimado"] == 2.5
    assert fake_llm.llamadas[-1]["imagen"] is not None


def test_fusion_target_inexistente_404(vault: VaultManager) -> None:
    """Fusionar con un ítem que no existe devuelve 404."""
    cliente = TestClient(_app_test(vault, FakeOFFClient()))
    respuesta = cliente.post(
        "/api/barcode/register",
        data={
            "ean": "8410000000005",
            "nombre": "Desconocido",
            "merge_target_id": "item_inexistente",
        },
    )
    assert respuesta.status_code == 404


# --- Extracción de precio desde imagen --------------------------------------------------


async def test_extraer_precio_desde_imagen_con_llm_fake(
    vault: VaultManager,
    fake_llm,
) -> None:
    """La función auxiliar parsea el precio devuelto por un LLM fake."""
    fake_llm.respuestas.extend(["3.99", "2,50", "null"])
    parser = ReceiptParser(vault, fake_llm)

    assert await extraer_precio_desde_imagen(parser, b"", "image/jpeg") == 3.99
    assert await extraer_precio_desde_imagen(parser, b"", "image/jpeg") == 2.5
    assert await extraer_precio_desde_imagen(parser, b"", "image/jpeg") is None
