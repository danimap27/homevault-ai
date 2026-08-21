# Imagen del backend HomeVault AI (FastAPI + uvicorn).
# El contexto de build es la raíz del repo (ahí está pyproject.toml).
FROM python:3.11-slim

WORKDIR /app

# Git es necesario para GitPython (auto-sync del vault).
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Instala el paquete declarado en pyproject.toml (capa cacheable).
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir .

# El vault y las credenciales se montan como volúmenes en /app/vault y
# /app/credentials; las rutas relativas de .env (./vault, ./credentials)
# se resuelven contra WORKDIR=/app.
EXPOSE 8080

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
