# AI Document Intelligence Platform

Aplicación web para cargar documentos PDF y hacerles preguntas en lenguaje natural mediante RAG
(Retrieval-Augmented Generation), con respuestas que citan el documento y la página de origen.

> **Estado:** Fase 5 (respuestas RAG con LLM). Proyecto de portafolio / aprendizaje; **no** es un servicio
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
│   │   └── services/       # lógica: almacenamiento, PDF, fragmentación, embeddings, búsqueda
│   ├── migrations/         # migraciones Alembic (historial versionado del esquema)
│   ├── tests/
│   │   ├── unit/           # rápidas, sin base de datos
│   │   ├── integration/    # contra PostgreSQL real (base docintel_test)
│   │   └── external/       # contra APIs de pago; solo con `pytest -m openai`
│   ├── alembic.ini
│   ├── pyproject.toml      # dependencias y configuración de herramientas
│   └── uv.lock             # versiones exactas, para instalaciones reproducibles
├── docs/
│   ├── rag-best-practices.md   # buenas prácticas de RAG y su estado en el proyecto
│   └── decisions/              # registro de decisiones técnicas (ADR)
├── .github/dependabot.yml  # actualizaciones automáticas de dependencias
├── docker/postgres/init/   # SQL que se ejecuta al crear el volumen de PostgreSQL
├── docker-compose.yml      # PostgreSQL 17 + pgvector para desarrollo
├── .env.example
└── README.md
```

El frontend (React + TypeScript) se añadirá en la Fase 6. Las buenas prácticas aplicadas y pendientes están en
[`docs/rag-best-practices.md`](docs/rag-best-practices.md).

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
cp .env.example .env          # y escribe tu OPENAI_API_KEY (o usa EMBEDDINGS_PROVIDER=fake)
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
| DELETE | `/api/v1/documents/{id}`        | Borra el documento, sus fragmentos, embeddings y el archivo (`204`) |
| POST   | `/api/v1/documents/{id}/reprocess` | Vuelve a procesar (tras un fallo o un cambio de modelo de embeddings) |
| POST   | `/api/v1/search`                | Búsqueda híbrida de fragmentos (sin LLM)                |
| POST   | `/api/v1/query`                 | Pregunta → respuesta del LLM con fuentes verificables   |

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
| `503` | El proveedor de embeddings no está configurado (falta `OPENAI_API_KEY`) |

Cuando la subida se rechaza (4xx) no se guarda nada. El procesamiento es síncrono en el MVP:
la respuesta llega cuando el documento ya está `completed` o `failed`.

### Cómo se procesa

1. Se valida el archivo y se guarda en `STORAGE_DIR` con un nombre aleatorio (el nombre original
   solo se guarda saneado como metadato y nunca se usa para rutas en disco).
2. Se extrae el texto de cada página con PyMuPDF.
3. El texto se divide en fragmentos de hasta `CHUNK_SIZE` caracteres (1000) con `CHUNK_OVERLAP`
   caracteres de solapamiento (200). Cada fragmento pertenece a una sola página, para poder
   citarla.
4. Se generan los embeddings de los fragmentos por lotes (`EMBEDDING_BATCH_SIZE`), con timeout y
   reintentos con backoff. Si el proveedor falla, el documento queda `failed` con
   `error_code: "embedding_error"` y se puede reprocesar.
5. Los fragmentos, sus embeddings, el modelo que los generó (`embedding_model`) y el estado
   `completed` se guardan en **una sola transacción**: si algo falla, no quedan datos parciales.

Los archivos de documentos `failed` se conservan en disco para poder reprocesarlos más adelante.

### Buscar

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "¿cuántos días de vacaciones tengo?", "top_k": 5}'
```

La búsqueda es **híbrida**: combina la similitud de significado (embeddings + pgvector, búsqueda
exacta) con la búsqueda por palabras de PostgreSQL (`tsvector`), útil para nombres propios,
códigos y números exactos. Las dos listas se fusionan con Reciprocal Rank Fusion.

- Solo se consideran documentos `completed` y vectores del modelo de embeddings activo.
- Los resultados vectoriales deben superar `RETRIEVAL_MIN_SCORE`. Si nada es relevante, la
  respuesta es `{"results": [], "insufficient_evidence": true}`.
- `top_k` está limitado por `RETRIEVAL_MAX_TOP_K` y la consulta por `MAX_QUERY_CHARS` (`422`).
- La respuesta nunca incluye los vectores. Los logs registran conteos, similitudes y tiempos,
  nunca el texto de la pregunta ni de los documentos.

### Preguntar (RAG)

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿cuántos días de vacaciones tengo?"}'
```

```json
{
  "answer": "Cada empleado dispone de veintidós días hábiles de vacaciones al año.",
  "sources": [
    {"document_id": "…", "filename": "manual.pdf", "page_number": 1,
     "chunk_id": "…", "excerpt": "Política de vacaciones. Cada empleado…", "score": 0.016}
  ],
  "insufficient_evidence": false
}
```

Cómo se genera:

1. Búsqueda híbrida de los fragmentos relevantes. **Si no hay ninguno, se responde que no hay
   evidencia sin llamar al LLM** (sin costo).
2. Se construye un contexto limitado (`RETRIEVAL_TOP_K` fragmentos, `RAG_MAX_CONTEXT_CHARS`)
   con ids cortos `S1`, `S2`… El texto de los documentos va delimitado y escapado, y el prompt
   (`app/services/prompts.py`) declara que es información, no instrucciones.
3. El LLM (`gpt-6-luna`, sin herramientas, `store=False`) devuelve JSON con un esquema fijo:
   respuesta, ids citados y si hay evidencia suficiente.
4. **Las citas se verifican en el servidor**: se descartan ids que no estaban en el contexto, y
   las fuentes devueltas (documento, página, extracto) salen de la base de datos, no del texto
   del LLM. Una respuesta sin ninguna cita válida se trata como no respaldada.

`answer` es texto generado por un LLM: muéstralo siempre como texto, nunca como HTML.
Costo estimado: ~$0.0004 por pregunta (ver
[`docs/decisions/0002-proveedor-llm.md`](docs/decisions/0002-proveedor-llm.md)).

### Embeddings

Proveedor: OpenAI `text-embedding-3-small` (1536 dimensiones). Costo estimado: ~$0.11 por cada
100 PDF de 50 páginas. Motivos, alternativas y privacidad en
[`docs/decisions/0001-proveedor-embeddings.md`](docs/decisions/0001-proveedor-embeddings.md).

- **Configura un límite de gasto** en platform.openai.com antes de usar tu clave.
- Para probar sin clave ni costo: `EMBEDDINGS_PROVIDER=fake` y `LLM_PROVIDER=fake` en `.env`
  (embeddings y respuestas locales y deterministas; no entienden sinónimos, solo palabras
  compartidas, y la "respuesta" es el inicio del fragmento más relevante).
- Si cambias de modelo, reprocesa los documentos: los vectores de modelos distintos no son
  comparables y la búsqueda ignora los del modelo anterior.

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
uv run pytest               # todas las pruebas (nunca llaman a APIs de pago)
uv run pytest tests/unit    # solo unitarias (no necesitan PostgreSQL)
uv run pytest -m openai -s  # pruebas opcionales contra OpenAI real (fracciones de centavo)
uv run ruff format .        # formatea el código
uv run ruff check .         # lint
```

Auditoría de vulnerabilidades en las dependencias (además de Dependabot en GitHub):

```bash
uv export --no-emit-project --format requirements-txt -o /tmp/req.txt
uv run pip-audit -r /tmp/req.txt --disable-pip
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
| openai            | app  | SDK oficial de OpenAI: embeddings con timeout y reintentos  |
| pgvector          | app  | Tipo `Vector` de SQLAlchemy y operadores de distancia       |
| pytest            | dev  | Ejecutor de pruebas                                         |
| httpx             | dev  | Cliente HTTP de pruebas (Starlette usa ya `httpx2`, que trae `openai`) |
| ruff              | dev  | Formateador y linter                                        |
| pip-audit         | dev  | Busca vulnerabilidades conocidas en las dependencias        |
