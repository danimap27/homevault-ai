"""Configuración de HomeVault AI con pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings de la aplicación, cargados desde .env o entorno."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    vault_path: Path = Path("./vault")

    # Sincronización con Google Workspace (Fase 2)
    google_credentials_dir: Path = Path("./credentials")
    google_tasks_list_id: str = "@default"
    google_calendar_id: str = "primary"
    google_sync_enabled: bool = False
    google_poll_interval_s: int = 60

    # Auto-sincronización Git del vault (Fase 4)
    git_remote_enabled: bool = False  # GIT_REMOTE_ENABLED=true activa el push
    git_debounce_s: float = 5.0  # ventana de agrupación de ráfagas de cambios

    # Ingesta de tickets con IA (Fase 3)
    ai_provider: Optional[str] = None  # openai | anthropic | gemini | ollama
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None  # vacío = modelo por defecto del proveedor
    ollama_base_url: str = "http://localhost:11434"
    ai_chat_model: str = "qwen3.5:4b"  # modelo local del asistente del hogar

    # Domótica MQTT + Home Assistant (Fase 4a)
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""  # vacío = sin autenticación
    mqtt_password: str = ""
    mqtt_client_id: str = "homevault-ai"
    mqtt_enabled: bool = False

    # Observador del vault y WebSockets (Fase 4)
    watcher_enabled: bool = True

    # Impresora térmica ESC/POS (Fase 4c)
    printer_host: str = ""  # vacío = impresión deshabilitada (503)
    printer_port: int = 9100

    # CORS para el frontend Next.js (Fase 5); en .env va como JSON
    cors_origins: list[str] = ["http://localhost:3000"]


def get_settings() -> Settings:
    """Devuelve las settings actuales."""
    return Settings()
