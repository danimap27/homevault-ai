# Referencia de la API REST

Base URL local: `http://localhost:8000`
Documentación interactiva: `/docs` (Swagger UI) y `/redoc`.

---

## Inventario

### `GET /api/inventory`
Lista todos los consumibles.

**Query params:**
- `ubicacion` (opcional): filtra por ubicación.

### `GET /api/inventory/expiring`
Ítems próximos a caducar.

**Query params:**
- `days_ahead` (int, default 4)

### `GET /api/inventory/orphans`
Ítems cuyo `ultimo_consumo` supera el doble de `dias_promedio_consumo`.

### `POST /api/inventory/consume`
Descuenta stock mediante FIFO.

```json
{
  "item_id_o_nombre": "item_milk_01",
  "cantidad": 1.0
}
```

### `POST /api/inventory/purchase`
Añade un lote y tacha de la lista de la compra si estaba.

```json
{
  "item_id_o_nombre": "item_milk_01",
  "cantidad": 2,
  "precio_unitario": 1.15,
  "fecha_caducidad": "2026-09-02"
}
```

### `GET /api/recipes`
Lista de recetas.

---

## Códigos de barras

### `GET /api/barcode/{ean}`
Consulta Open Food Facts. Si el EAN ya existe en el vault, lo devuelve; si no, lo crea en `inventario/despensa/`.

### `POST /api/barcode/consume`
Consumo 1-click por código de barras.

```json
{
  "ean": "8410000001234",
  "cantidad": 1
}
```

---

## Lista de la compra

### `GET /api/shopping-list`
Devuelve las entradas pendientes parseadas.

### `POST /api/shopping-list/check`
Marca una entrada como comprada.

```json
{
  "item_id": "item_milk_01"
}
```

---

## Planificador

### `GET /api/planner/current`
Plan semanal de la semana ISO actual. 404 si aún no existe.

### `PUT /api/planner/current`
Guarda el plan semanal recibido.

```json
{
  "semana_iso": "2026-W34",
  "fecha_inicio": "2026-08-17",
  "fecha_fin": "2026-08-23",
  "dias": { ... },
  "batch_cooking_programado": []
}
```

### `GET /api/planner/rescue`
Modo Rescue Chef: sugiere recetas que consumen ítems a punto de caducar.

**Query params:**
- `dias` (int, default 4)

### `POST /api/planner/batch-cooking`
Cocina por lotes: descuenta ingredientes y genera tuppers en congelador.

```json
{
  "receta_ids": ["recipe_lentejas_01"],
  "destino": "congelador",
  "dias_max_congelador": 90
}
```

### `POST /api/planner/evento`
Calcula compra para un evento con invitados.

```json
{
  "receta_ids": ["recipe_pasta_01"],
  "invitados": 8
}
```

---

## Tareas

### `GET /api/tasks/pending`
Tareas pendientes.

**Query params:**
- `assigned_user` (opcional)

### `GET /api/tasks`
Lista de tareas.

**Query params:**
- `estado` (opcional): `pendiente` o `completada`
- `asignado_a` (opcional)

### `POST /api/tasks/{task_id}/complete`
Marca una tarea como completada, rota el turno y reprograma.

```json
{
  "completed_by": "Daniel"
}
```

### `POST /api/tasks/{task_id}/check-stock`
Verifica consumibles requeridos y marca `bloqueada_por_stock` si falta stock.

---

## Ingesta de tickets

### `POST /api/ingest/receipt`
Recibe imagen o texto de ticket.

**Multipart:** campo `imagen` (archivo).  
**JSON:** `{"texto": "...", "comercio": "...", "total": 34.50}`.

Devuelve el ticket parseado y el resultado del registro en el vault.

---

## Finanzas

### `GET /api/finance/summary?mes=YYYY-MM`
Resumen mensual de gastos.

Respuesta:

```json
{
  "mes": "2026-08",
  "total": 156.4,
  "por_categoria": [
    {"categoria": "lacteos", "total": 45.2},
    {"categoria": "despensa_seca", "total": 111.2}
  ]
}
```

---

## Impresión y NFC

### `POST /api/print/receipt-list`
Envía la lista de la compra a la impresora térmica ESC/POS.

### `POST /api/print/label-tupper`
Imprime etiqueta de tupper con QR.

```json
{
  "nombre": "Lentejas caseras",
  "fecha_congelacion": "2026-08-21",
  "qr_data": "homevault:item:tupper_lentejas_20260821"
}
```

### `GET /location/{slug}`
Devuelve los consumibles de una ubicación NFC/QR según `vault/config/ubicaciones.json`.

---

## Domótica

### `POST /api/domotica/webhook/boton`
Webhook para botones físicos Zigbee/Matter.

```json
{
  "boton_id": "boton_lavavajillas",
  "accion": "simple"
}
```

El mapa de botones se lee de `vault/config/botones.json`.

---

## WebSocket

### `GET /ws`
Canal de eventos del vault. Mensajes de salida:

```json
{
  "tipo": "INVENTORY_UPDATED",
  "ruta": "inventario/nevera/leche-entera.md",
  "accion": "modified"
}
```

Tipos posibles: `INVENTORY_UPDATED`, `TASK_CHANGED`, `MEAL_PLAN_SYNCED`, `SHOPPING_LIST_UPDATED`, `GENERIC_UPDATE`.

---

## MCP Server

Todas las herramientas están disponibles por stdio ejecutando:

```bash
python -m backend.mcp_server
```

Ver lista en `README.md`.
