#!/usr/bin/env python3
"""Puente TCP hacia Ollama para los contenedores Docker del homelab.

Contexto: Ollama corre como servicio system y escucha SOLO en 127.0.0.1:11434,
así que los contenedores de HomeVault no pueden hablar con él. Este puente
escucha en las IPs de las interfaces bridge de Docker (docker0 / br-*) en el
puerto 11435 y reenvía a 127.0.0.1:11434, sin exponer nada a la LAN.

Re-escanea las interfaces cada 30 s para sobrevivir a reinicios o recreaciones
del stack Docker (las IPs de bridge pueden cambiar). Sin dependencias externas.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess

PUERTO_ESCUCHA = 11435
DESTINO = ("127.0.0.1", 11434)
INTERVALO_RESCANEO_S = 30

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("ollama-bridge")

# Línea de `ip -o -4 addr show`, p. ej.:
# "3: br-0f2e319c9dab: <BROADCAST,...> inet 172.25.0.1/16 brd ..."
_REGEX_DIRECCION = re.compile(
    r"^\d+:\s+(?P<iface>[^@\s:]+)(?:@\S+)?\s+.*\binet\s+"
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)"
)


def ips_bridge_docker() -> set[str]:
    """IPs IPv4 de las interfaces bridge de Docker (docker0 y br-*)."""
    try:
        salida = subprocess.run(
            ["ip", "-o", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    ips: set[str] = set()
    for linea in salida.splitlines():
        coincidencia = _REGEX_DIRECCION.match(linea)
        if not coincidencia:
            continue
        iface = coincidencia.group("iface")
        if iface == "docker0" or iface.startswith("br-"):
            ips.add(coincidencia.group("ip"))
    return ips


async def manejar_conexion(
    lector_cliente: asyncio.StreamReader,
    escritor_cliente: asyncio.StreamWriter,
) -> None:
    """Reenvía bidireccionalmente una conexión hacia Ollama."""
    try:
        lector_remoto, escritor_remoto = await asyncio.open_connection(*DESTINO)
    except OSError as exc:
        log.warning("No se pudo conectar con Ollama: %s", exc)
        escritor_cliente.close()
        return

    async def copiar(
        lector: asyncio.StreamReader, escritor: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                datos = await lector.read(65536)
                if not datos:
                    break
                escritor.write(datos)
                await escritor.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                escritor.close()
            except Exception:  # noqa: BLE001 - cierre best-effort
                pass

    await asyncio.gather(
        copiar(lector_cliente, escritor_remoto),
        copiar(lector_remoto, escritor_cliente),
    )


async def main() -> None:
    servidores: dict[str, asyncio.Server] = {}
    log.info(
        "Puente Ollama arrancado: escucha en puertos %s de las bridges Docker → %s:%s",
        PUERTO_ESCUCHA,
        *DESTINO,
    )
    while True:
        actuales = ips_bridge_docker()
        for ip in actuales:
            if ip not in servidores:
                try:
                    servidores[ip] = await asyncio.start_server(
                        manejar_conexion, host=ip, port=PUERTO_ESCUCHA
                    )
                    log.info("Escuchando en %s:%s", ip, PUERTO_ESCUCHA)
                except OSError as exc:
                    log.error("No se pudo abrir %s:%s: %s", ip, PUERTO_ESCUCHA, exc)
        for ip in list(servidores):
            if ip not in actuales:
                servidores.pop(ip).close()
                log.info("Interfaz %s desaparecida: servidor cerrado", ip)
        if not actuales:
            log.warning("Sin interfaces bridge de Docker todavía; reintentando…")
        await asyncio.sleep(INTERVALO_RESCANEO_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
