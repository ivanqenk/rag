# Imagen del backend (FastAPI). Dos etapas: una instala las dependencias con uv y la final
# solo copia el entorno ya instalado, sin uv ni cachés: más pequeña y con menos superficie.

FROM python:3.12.15-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Primero solo los archivos de dependencias: Docker reutiliza esta capa mientras no cambien.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

FROM python:3.12.15-slim-trixie
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 STORAGE_DIR=/data/storage
# Usuario sin privilegios: si alguien comprometiera la aplicación, no sería root.
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /data/storage && chown app /data/storage
WORKDIR /app
COPY --from=builder --chown=root:root /app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# Aplica las migraciones pendientes y arranca el servidor.
# --proxy-headers: la IP del cliente sale de X-Forwarded-For (para los límites por IP). Es seguro
# confiar en cualquier origen porque el backend solo es accesible a través de nginx, que
# sobrescribe esa cabecera con la IP real.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
