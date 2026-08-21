# Despliegue de HomeVault AI con Docker Compose

## Requisitos

- Docker Engine con plugin Compose v2 (`docker compose version`).
- Un archivo `.env` basado en la plantilla del repo.

## Pasos

```bash
cp .env.example .env
docker compose up -d --build
```

Servicios levantados:

- **backend** — API FastAPI en `http://localhost:8080`. Monta `./vault`
  en `/app/vault` y `./credentials` en `/app/credentials`; las rutas
  relativas de `.env` (`VAULT_PATH=./vault`, `GOOGLE_CREDENTIALS_DIR=./credentials`)
  se resuelven dentro del contenedor contra `/app`.
- **frontend** — Next.js standalone en `http://localhost:3000`.
- **mqtt** — broker Mosquitto accesible solo desde la red interna
  `homevault-net` (sin puerto publicado al host; `allow_anonymous true`
  es seguro en ese aislamiento). El backend lo alcanza como `mqtt:1883`.

## Exponer a Internet con Cloudflare Tunnel

Ejemplo real con un túnel dedicado (`homevault`) y un único dominio público:

```bash
# Crea el túnel (una sola vez)
cloudflared tunnel create homevault

# Apunta los hostnames al túnel
cloudflared tunnel route dns homevault homevault.quantum-homelab.win

# ~/.cloudflared/homevault.yml
tunnel: <ID_DEL_TUNNEL>
credentials-file: /home/quantum-nas/.cloudflared/<ID_DEL_TUNNEL>.json
ingress:
  - hostname: homevault.quantum-homelab.win
    service: http://localhost:3000
  - service: http_status:404
```

Levanta el túnel:

```bash
cloudflared tunnel --config ~/.cloudflared/homevault.yml run
```

Con `NEXT_PUBLIC_API_URL=` vacío en `.env`, el frontend Next.js proxea
`/api/*` al backend internamente, por lo que basta un solo dominio público.

URL de producción de ejemplo: `https://homevault.quantum-homelab.win`.

## Operación habitual

```bash
docker compose logs -f backend     # logs del backend
docker compose ps                  # estado de los servicios
docker compose down                # parar todo (los volúmenes persisten)
docker compose up -d --build       # rebuild tras cambios de código
```

Los datos del broker MQTT persisten en los volúmenes `mosquitto_data` y
`mosquitto_logs`. El vault Markdown vive en `./vault` del host (bind mount),
por lo que Obsidian puede seguir editándolo directamente.

## Notas

- `frontend/Dockerfile` lo aporta el agente de frontend (Next.js standalone);
  hasta que exista, `docker compose up -d --build backend mqtt` levanta el
  resto de la plataforma.
- Para que el backend use el broker interno, configura su host MQTT como
  `mqtt` (nombre del servicio) y puerto `1883`.
