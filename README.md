# HomeVault AI

Plataforma open-source de gestión inteligente del hogar. Su **única fuente de verdad** es un vault local de archivos Markdown con YAML frontmatter (100% compatible con Obsidian / Logseq), versionado con Git. **No utiliza bases de datos SQL ni NoSQL**: todo el estado vive en tu filesystem.

- Backend en **FastAPI** + **Python 3.11+** con modelos Pydantic v2.
- Servidor **MCP (Model Context Protocol)** para agentes externos (Hermes, Claude, etc.).
- Integración con **Google Tasks / Calendar**, **Open Food Facts**, **MQTT / Home Assistant**, impresoras ESC/POS y lectores NFC/QR.
- Frontend **Next.js 14 PWA** con App Router, TypeScript, Tailwind CSS y modo oscuro.
- Despliegue en un solo comando con **Docker Compose**.

---

## Características principales

| Módulo | Qué hace |
|--------|----------|
| **Inventario** | Consumibles/alimentos/recambios con lotes FIFO, stock mínimo, caducidades, sensores de peso MQTT y escáner de códigos de barras. |
| **Recetario + planificador** | Recetas con ingredientes, plan semanal interactivo, modo **Rescue Chef** (usa lo que caduca), **batch cooking** y calculadora de eventos/invitados. |
| **Tareas domésticas** | Reparto rotativo de convivientes, frecuencias personalizables, bloqueo por falta de recambio y sincronización bidireccional con Google Tasks. |
| **Lista de la compra** | Auto-generada al tocar stock mínimo, categorizada por pasillo, exportable e imprimible en térmica ESC/POS. |
| **Ingesta de tickets** | Foto de ticket o texto libre → IA estructurada → nuevos lotes FIFO + registro de gastos. |
| **Domótica** | Botones físicos Zigbee/Matter, sensores de peso ESPHome, publicación MQTT Discovery para Home Assistant y avisos TTS matutinos. |
| **MCP** | 7 herramientas estándar para que agentes externos consuman y modifiquen el hogar. |
| **Git auto-sync** | Commits automáticos con debounce y push opcional tras cada ráfaga de cambios. |

---

## Arquitectura rápida

```
┌─────────────┐      HTTP/WebSocket      ┌──────────────┐
│  Next.js    │ ◄──────────────────────► │   FastAPI    │
│  PWA        │                          │   backend    │
└─────────────┘                          └──────┬───────┘
                                                │
    ┌────────────┬─────────────┬───────────────┼────────────┐
    ▼            ▼             ▼               ▼            ▼
 Google      Open Food     MQTT/Home      Vault Markdown   MCP
 Workspace     Facts       Assistant      (única fuente)   server
```

El backend lee y escribe archivos `.md` de forma **atómica** (`asyncio.Lock` por archivo + `portalocker` + `.tmp`/`os.replace`). Los modelos Pydantic v2 validan el frontmatter YAML de cada entidad.

Más detalles en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) y [`docs/API.md`](docs/API.md).

---

## Requisitos

- Python 3.11+
- Node.js 20+ (solo si trabajas en el frontend)
- Docker + Docker Compose (opcional, recomendado para producción)
- Mosquitto (incluido en `docker-compose.yml`)

---

## Quickstart local

### 1. Clonar e instalar backend

```bash
git clone https://github.com/danimap27/homevault-ai.git
cd homevault-ai
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. Preparar entorno y vault

```bash
cp .env.example .env
# Crea tu vault privado (no se sube a git)
mkdir -p vault/{inventario/{nevera,congelador,despensa,limpieza,recambios_tecnicos,botiquin},recetas,planificador,tareas,listas,gastos,config}
touch vault/listas/compra.md
```

El repositorio incluye plantillas Obsidian en `vault_templates/`; puedes copiarlas a `vault/_templates/`.

### 3. Ejecutar backend + tests

```bash
.venv/bin/uvicorn backend.main:app --reload
# En otra terminal:
.venv/bin/pytest -q
```

API docs: `http://localhost:8000/docs`

### 4. Frontend (opcional)

```bash
cd frontend
npm install
cp .env.local.example .env.local   # ajusta NEXT_PUBLIC_API_URL
npm run build
npm start
```

---

## Despliegue con Docker Compose

```bash
cp .env.example .env
# Edita .env con tus claves (OpenAI/Google/etc.) si vas a usar esas integraciones
docker compose up -d --build
```

Servicios levantados:

- Backend: `http://localhost:8080`
- Frontend: `http://localhost:3000`
- MQTT broker: `mqtt:1883` (solo red interna de compose)

Más detalles en [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Integraciones disponibles

Todas son **opt-in**. Sin configurarlas, el core funciona 100% offline con el vault Markdown.

| Variable de entorno | Integración |
|---------------------|-------------|
| `AI_PROVIDER` + `AI_API_KEY` | Parseo de tickets con OpenAI / Anthropic / Gemini / Ollama |
| `GOOGLE_SYNC_ENABLED` + credenciales OAuth | Google Tasks + Calendar |
| `MQTT_ENABLED` + `MQTT_HOST` | Sensores de peso y Home Assistant |
| `OFF_*` | Open Food Facts |
| `PRINTER_HOST` | Impresora térmica ESC/POS |
| `GIT_REMOTE_ENABLED` | Push automático a remoto Git |

Ver `.env.example` para la lista completa.

---

## Servidor MCP

Levanta el servidor MCP por stdio:

```bash
python -m backend.mcp_server
```

Herramientas expuestas:

- `inventory_record_purchase`
- `inventory_consume`
- `inventory_query_expiring`
- `task_list_pending`
- `task_mark_completed`
- `meal_plan_suggest`
- `shopping_list_get_and_modify`

---

## Tests

```bash
.venv/bin/pytest -q          # backend
# frontend:
cd frontend && npm run build && cd ..
```

Estado actual: **182 tests en verde**.

---

## Estructura del repositorio

```
homevault-ai/
├── backend/                 # FastAPI + lógica de dominio
│   ├── main.py              # App + lifespan
│   ├── models.py            # Modelos Pydantic v2
│   ├── vault_manager.py     # E/S atómica de Markdown
│   ├── google_sync.py       # Google Tasks/Calendar
│   ├── ai_vision_parser.py  # Parseo de tickets con IA
│   ├── mqtt_connector.py    # MQTT / Home Assistant
│   ├── off_client.py        # Open Food Facts
│   ├── planner.py           # Rescue Chef + batch cooking
│   ├── printer.py           # ESC/POS
│   ├── watcher.py           # File watcher + WebSockets
│   ├── git_sync.py          # Auto-commits
│   ├── mcp_server.py        # Servidor MCP stdio
│   └── routers/             # APIRouters
├── frontend/                # Next.js 14 PWA
├── mosquitto/               # Configuración broker MQTT
├── vault_templates/         # Plantillas Obsidian
├── tests/                   # Tests pytest
├── docs/                    # Documentación
├── docker-compose.yml
├── backend/Dockerfile
└── frontend/Dockerfile
```

---

## Licencia

MIT — abierto a contribuciones.

---

Autor: [Dani](https://github.com/danimap27)
