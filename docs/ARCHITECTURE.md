# Arquitectura de HomeVault AI

## Filosofía: Markdown como base de datos

HomeVault AI almacena **todo el estado** en archivos Markdown planos con YAML frontmatter. Cada entidad es un archivo `.md` con:

- Un bloque `---` con metadatos validados por Pydantic v2.
- Un cuerpo Markdown libre (ficha técnica, instrucciones, checklists, notas).

Ventajas:

- **Portable**: Obsidian, Logseq, cualquier editor de texto.
- **Versionable**: Git diff de cada cambio.
- **Auditável**: sabes quién tocó qué y cuándo.
- **Sin vendor lock-in**: no dependes de ninguna base de datos.

## Entidades principales

| Entidad | Ruta | Esquema |
|---------|------|---------|
| Consumible / alimento / recambio | `inventario/<ubicacion>/<slug>.md` | `Consumible` |
| Receta | `recetas/<slug>.md` | `Receta` |
| Plan semanal | `planificador/YYYY-Www.md` | `PlanSemanal` |
| Tarea doméstica | `tareas/<slug>.md` | `Tarea` |
| Lista de la compra | `listas/compra.md` | Markdown libre parseado |
| Gastos mensuales | `gastos/YYYY-MM.md` | Frontmatter `mes/total_mes/tickets` + tabla |
| Configuración | `config/*.json` | JSON libre |

## Concurrencia y atomicidad

`VaultManager` garantiza consistencia:

- `asyncio.Lock` por ruta de archivo (diccionario global protegido).
- `portalocker` sobre un sidecar `.lock` durante la escritura real.
- Escritura atómica: se escribe a `<archivo>.tmp` y se mueve con `os.replace`.
- Los eventos `.tmp` son ignorados por el file watcher.

## Flujo de datos típico

### Compra de leche (ticket físico)

1. El usuario saca foto al ticket o pega texto libre.
2. `POST /api/ingest/receipt` → `ReceiptParser` con LLM → `TicketParseado`.
3. `register_purchase()` crea un nuevo lote en `inventario/nevera/leche-entera.md`.
4. Si la leche estaba en `listas/compra.md`, se marca `[x]`.
5. Se acumula el gasto en `gastos/2026-08.md`.
6. El file watcher detecta cambios en `inventario/` y `listas/` y emite `INVENTORY_UPDATED` + `SHOPPING_LIST_UPDATED` por WebSocket.
7. `GitSync` programa un commit `Auto-sync: update inventory [skip ci]` tras 5 segundos de silencio.

### Consumo por sensor de peso

1. ESPHome publica `home/sensors/kitchen/fridge/milk_weight` con gramos restantes.
2. `MQTTConnector` recibe el mensaje, busca el consumible con `mqtt_sensor_topic` igual.
3. Actualiza `stock_actual` y dispara la lista de la compra si toca mínimo.
4. El cambio se propaga igual que en el flujo anterior.

### Tarea recurrente

1. El backend crea una tarea en Google Tasks y guarda `google_task_id`.
2. Cada 60 segundos `poll_google_tasks()` consulta estado remoto.
3. Cuando se completa (remoto o local), se añade al historial, rota el siguiente conviviente y se reprograma según la frecuencia.
4. Si la tarea requiere consumibles y no hay stock, se marca `bloqueada_por_stock` y se añade a la compra.

## Diagrama de componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (Next.js PWA)                 │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP / WebSocket
┌───────────────────────▼─────────────────────────────────────────┐
│                         FastAPI backend                         │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌─────────┐ │
│  │   routers    │ │ VaultManager│ │ GoogleSync   │ │ Planner │ │
│  └──────┬───────┘ └──────┬──────┘ └──────┬───────┘ └────┬────┘ │
│         └─────────────────┴───────────────┘              │       │
│                           │                              │       │
│                    vault/ (Markdown)                     │       │
│                           │                              │       │
│         ┌─────────────────┼─────────────────┐            │       │
│         ▼                 ▼                 ▼            ▼       │
│   MQTT Connector    OFF Client    ReceiptParser    MCP server   │
└─────────────────────────────────────────────────────────────────┘
```

## Decisiones de diseño

- **Sin ORM**: Pydantic v2 es el único schema. Lectura/escritura directa de archivos.
- **Clientes inyectables**: MQTT, Google, LLM, impresora, Open Food Facts — todos usan un protocolo mínimo que permite tests con fakes sin credenciales reales.
- **Lotes FIFO**: los consumos descuentan primero del lote con caducidad más próxima; el resto va a `stock_actual`.
- **Eventos externos ≠ estado interno**: Google Tasks es un espejo; el estado canónico sigue siendo el archivo `.md`.
- **Git auto-sync con debounce**: evita un commit por cada tecla; agrupa ráfagas y solo empuja si `GIT_REMOTE_ENABLED=true`.

## Escalabilidad

HomeVault AI está pensado para un único hogar / servidor doméstico. El cuello de botella es el número de archivos en el vault; para un uso doméstico real (miles de ítems) la E/S atómica por archivo es suficiente. Si algún día se necesita escalar, el límite sería el filesystem, no una base de datos.
