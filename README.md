# AI Document Intelligence Platform

Aplicación web para cargar documentos PDF y hacerles preguntas en lenguaje natural mediante RAG
(Retrieval-Augmented Generation), con respuestas que citan el documento y la página de origen.

> **Estado:** Fase 3 (ingestión de PDF). Proyecto de portafolio / aprendizaje; **no** es un servicio
> listo para producción ni para exponerse a Internet (no tiene autenticación ni rate limiting).

La especificación completa está en
[`AI_Document_Intelligence_Platform_Spec.md`](AI_Document_Intelligence_Platform_Spec.md).

## Estructura

```text
.
├── backend/                # API FastAPI (Python 3.12)
│   ├── app/
│   │   ├── main.py         # crea la app FastAPI y registra las rutas
│   │   ├── api/            # routers HTTP: traducen peticiones a llamadas al repositorio
│   │   ├── core/config.py  # configuración desde variables de entorno / .env
│   │   ├── db/             # engine, sesiones y clase base del ORM
│   │   ├── models/         # modelos ORM (tablas)
│   │   ├── schemas/        # modelos Pydantic de entrada/salida de la API
│   │   ├── repositories/   # consultas a la base de datos
│   │   └── services/       # lógica: almacenamiento, extracción PDF, fragmentación, ingestión
│   ├── migrations/         # migraciones Alembic (historial versionado del esquema)
│   ├── tests/
│   │   ├── unit/           # rápidas, sin base de datos
│   │   └── integration/    # contra PostgreSQL real (base docintel_test)
│   ├── alembic.ini
│   ├── pyproject.toml      # dependencias y configuración de herramientas
│   └── uv.lock             # versiones exactas, para instalaciones reproducibles
├── docker/postgres/init/   # SQL que se ejecuta al crear el volumen de PostgreSQL
├── docker-compose.yml      # PostgreSQL 17 + pgvector para desarrollo
├── .env.example
└── README.md
```

Los embeddings (pgvector), las consultas RAG y el frontend (React + TypeScript) se añadirán en
fases posteriores.

## Requisitos

- [uv](https://docs.astral.sh/uv/) — gestiona Python 3.12, el entorno virtual y las dependencias.

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  No hace falta tener Python 3.12 instalado: `uv` lo descarga automáticamente.

- Docker con Docker Compose. En Windows + WSL: Docker Desktop con la integración WSL activada
  (Settings → Resources → WSL Integration).

## Ejecutar en local

Desde la raíz del repositorio:

```bash
cp .env.example .env
docker compose up -d db       # arranca PostgreSQL (espera a que esté "healthy")
cd backend
uv sync                       # crea .venv e instala dependencias desde uv.lock
uv run alembic upgrade head   # crea/actualiza las tablas
uv run uvicorn app.main:app --reload
```

- Health check: <http://localhost:8000/health>
- Documentación interactiva (Swagger UI): <http://localhost:8000/docs>
- Esquema OpenAPI: <http://localhost:8000/openapi.json>

Los datos de PostgreSQL se guardan en el volumen Docker `pgdata` y sobreviven a reinicios.
Para borrarlos por completo: `docker compose down -v`.

## Endpoints actuales

| Método | Ruta                            | Descripción                                             |
|--------|---------------------------------|---------------------------------------------------------|
| GET    | `/health`                       | Estado básico de la aplicación                          |
| POST   | `/api/v1/documents`             | Sube un PDF (`multipart/form-data`, campo `file`) y lo procesa |
| GET    | `/api/v1/documents`             | Lista paginada (`limit` 1–100, por defecto 20; `offset` ≥ 0), más recientes primero |
| GET    | `/api/v1/documents/{id}`        | Metadatos y estado de un documento (`404` si no existe, `422` si el id no es UUID) |

### Subir un PDF

```bash
curl -F "file=@/ruta/a/manual.pdf" http://localhost:8000/api/v1/documents
```

| Respuesta | Cuándo |
|-----------|--------|
| `201` con `status: "completed"` | El texto se extrajo y fragmentó correctamente |
| `201` con `status: "failed"` y `error_message` | El PDF es válido pero no se pudo procesar (p. ej. no tiene texto: PDF escaneado; OCR no soportado) |
| `400` | Archivo vacío |
| `413` | Supera `MAX_UPLOAD_SIZE_MB` (20 MB por defecto) |
| `415` | No es un PDF (se comprueba la extensión **y** la firma `%PDF-` del contenido; el `Content-Type` del cliente se ignora) |
| `422` | PDF dañado, protegido con contraseña, sin páginas o con más de `MAX_PDF_PAGES` |

Cuando la subida se rechaza (4xx) no se guarda nada. El procesamiento es síncrono en el MVP:
la respuesta llega cuando el documento ya está `completed` o `failed`.

### Cómo se procesa

1. Se valida el archivo y se guarda en `STORAGE_DIR` con un nombre aleatorio (el nombre original
   solo se guarda saneado como metadato y nunca se usa para rutas en disco).
2. Se extrae el texto de cada página con PyMuPDF.
3. El texto se divide en fragmentos de hasta `CHUNK_SIZE` caracteres (1000) con `CHUNK_OVERLAP`
   caracteres de solapamiento (200). Cada fragmento pertenece a una sola página, para poder
   citarla.
4. Los fragmentos y el estado `completed` se guardan en **una sola transacción**: si algo falla,
   el documento queda `failed` y sin fragmentos parciales.

Los archivos de documentos `failed` se conservan en disco para poder reprocesarlos más adelante.

## Migraciones

Desde `backend/`:

```bash
uv run alembic upgrade head                          # aplica todas las migraciones
uv run alembic downgrade -1                          # revierte la última
uv run alembic revision --autogenerate -m "mensaje"  # crea una a partir de cambios en models/
```

Revisa siempre el archivo generado por `--autogenerate` antes de aplicarlo.

## Pruebas, formato y lint

Desde `backend/`:

```bash
uv run pytest               # todas las pruebas
uv run pytest tests/unit    # solo unitarias (no necesitan PostgreSQL)
uv run ruff format .        # formatea el código
uv run ruff check .         # lint
```

Las pruebas de integración necesitan `docker compose up -d db`. Si PostgreSQL no está disponible
se marcan como **SKIPPED** con el motivo (usa `pytest -rs` para verlo); no cuentan como pasadas.

## Dependencias

| Paquete           | Tipo | Propósito                                                   |
|-------------------|------|-------------------------------------------------------------|
| fastapi           | app  | Framework web y generación automática de OpenAPI            |
| uvicorn           | app  | Servidor ASGI que ejecuta la aplicación                     |
| sqlalchemy        | app  | ORM y constructor de consultas SQL                          |
| alembic           | app  | Migraciones versionadas del esquema                         |
| psycopg[binary]   | app  | Driver de PostgreSQL (versión 3)                            |
| pydantic-settings | app  | Lee la configuración desde variables de entorno y `.env`    |
| python-multipart  | app  | Permite a FastAPI recibir archivos (`multipart/form-data`)  |
| pymupdf (1.x)     | app  | Valida PDF y extrae su texto por página. Fijado a `<2`: la 2.0 añade ~100 MB de dependencias de análisis de layout (onnxruntime, numpy) que no necesitamos |
| pytest            | dev  | Ejecutor de pruebas                                         |
| httpx             | dev  | Cliente HTTP que usa `TestClient` de FastAPI en las pruebas |
| ruff              | dev  | Formateador y linter                                        |
