# AI Document Intelligence Platform

Aplicación web para cargar documentos PDF y hacerles preguntas en lenguaje natural mediante RAG
(Retrieval-Augmented Generation), con respuestas que citan el documento y la página de origen.

> **Estado:** MVP completo (Fase 7). Proyecto de portafolio / aprendizaje; **no** es un servicio
> listo para producción ni para exponerse a Internet (no tiene autenticación ni rate limiting).

**Qué hace:** subes PDFs; el sistema extrae su texto, lo divide en fragmentos, genera
embeddings y un resumen de cada documento, y responde preguntas citando documento, página y
extracto. Si los documentos no contienen la respuesta, lo dice en lugar de inventarla.

**Documentación:** [arquitectura](docs/architecture.md) · [evaluación del RAG](docs/rag-evaluation.md)
· [buenas prácticas](docs/rag-best-practices.md) · [decisiones (ADR)](docs/decisions/)

| Biblioteca | Pregunta con fuentes |
|---|---|
| ![Biblioteca con tres documentos procesados](docs/images/biblioteca.png) | ![Respuesta con la fuente: documento, página y extracto](docs/images/pregunta.png) |
| **Detalle con resumen** | **Sin evidencia (modo oscuro)** |
| ![Detalle de un documento con su resumen](docs/images/documento.png) | ![Aviso de que los documentos no contienen la respuesta](docs/images/sin-evidencia.png) |

<sub>Capturas con documentos ficticios del conjunto de evaluación y proveedores **falsos**
(sin IA): por eso la «respuesta» y el «resumen» son el inicio del texto encontrado. Con OpenAI
son texto redactado por el LLM.</sub>

## Inicio rápido (Docker)

Solo necesitas Docker con Docker Compose.

```bash
git clone https://github.com/ivanqenk/rag.git && cd rag
cp .env.example .env
```

Edita `.env` y elige una opción:

- **Con OpenAI** (respuestas reales, ~$0.0004 por pregunta): escribe tu `OPENAI_API_KEY` y
  configura un límite de gasto en platform.openai.com.
- **Sin clave ni costo** (para comprobar el flujo): `EMBEDDINGS_PROVIDER=fake`,
  `LLM_PROVIDER=fake` y `RETRIEVAL_MIN_SCORE=0.2`. La búsqueda solo encuentra palabras exactas
  (pregunta con palabras que aparezcan tal cual en el PDF), la «respuesta» es el inicio del
  fragmento encontrado y, por coincidencias del hash que usa, alguna pregunta sin relación
  puede devolver un fragmento en vez de abstenerse. Con OpenAI esto no ocurre.

```bash
docker compose up --build     # la primera vez tarda unos minutos
```

Abre **<http://localhost:8080>** y comprueba el flujo principal:

1. **Biblioteca** → sube un PDF con texto (no escaneado). Debe quedar en estado «Listo».
2. Pulsa su nombre: verás sus datos y su **resumen**.
3. **Preguntar** → haz una pregunta sobre su contenido. La respuesta muestra las fuentes con
   página y extracto. Prueba también «¿de qué trata?» y una pregunta que el documento no
   responda: debe decir que no hay evidencia suficiente.

Para pararlo: `Ctrl+C` (o `docker compose down`). `docker compose down -v` borra también los
documentos y la base de datos.

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
│   ├── evaluation/         # conjunto de evaluación RAG (dataset.json) y script (run.py)
│   ├── tests/
│   │   ├── unit/           # rápidas, sin base de datos
│   │   ├── integration/    # contra PostgreSQL real (base docintel_test)
│   │   └── external/       # contra APIs de pago; solo con `pytest -m openai`
│   ├── Dockerfile          # imagen del backend (aplica migraciones al arrancar)
│   ├── alembic.ini
│   ├── pyproject.toml      # dependencias y configuración de herramientas
│   └── uv.lock             # versiones exactas, para instalaciones reproducibles
├── frontend/               # React + TypeScript + Vite
│   ├── src/
│   │   ├── api/client.ts   # cliente HTTP tipado (único lugar que conoce la API)
│   │   ├── types/api.ts    # tipos de las respuestas (reflejan los esquemas del backend)
│   │   ├── pages/          # Biblioteca, Preguntar, Detalle de documento
│   │   ├── components/     # subida de archivos, etiqueta de estado
│   │   └── router.ts       # navegación mínima por hash (#/biblioteca, #/preguntar…)
│   ├── docker/nginx.conf   # sirve la app y hace de proxy de /api (con cabeceras de seguridad)
│   ├── Dockerfile          # compila con Node y sirve con nginx sin root
│   └── vite.config.ts      # proxy /api -> backend en desarrollo; configuración de Vitest
├── docs/
│   ├── architecture.md         # componentes, flujos, modelo de datos y decisiones
│   ├── rag-evaluation.md       # metodología y resultados de la evaluación
│   ├── rag-best-practices.md   # buenas prácticas de RAG y su estado en el proyecto
│   └── decisions/              # registro de decisiones técnicas (ADR)
├── .github/dependabot.yml  # actualizaciones automáticas de dependencias
├── docker/postgres/init/   # SQL que se ejecuta al crear el volumen de PostgreSQL
├── docker-compose.yml      # PostgreSQL + pgvector; con --build, también backend y frontend
├── .env.example
└── README.md
```

Las buenas prácticas aplicadas y pendientes están en
[`docs/rag-best-practices.md`](docs/rag-best-practices.md).

## Requisitos para desarrollo

- [uv](https://docs.astral.sh/uv/) — gestiona Python 3.12, el entorno virtual y las dependencias.

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  No hace falta tener Python 3.12 instalado: `uv` lo descarga automáticamente.

- [Node.js](https://nodejs.org/) 20 o superior (con npm), para el frontend.
- Docker con Docker Compose. En Windows + WSL: Docker Desktop con la integración WSL activada
  (Settings → Resources → WSL Integration).

## Desarrollo en local (sin Docker para backend y frontend)

Recomendado para modificar el código: recarga automática al guardar.

Desde la raíz del repositorio:

```bash
cp .env.example .env          # y escribe tu OPENAI_API_KEY (o usa EMBEDDINGS_PROVIDER=fake)
docker compose up -d db       # arranca PostgreSQL (espera a que esté "healthy")
cd backend
uv sync                       # crea .venv e instala dependencias desde uv.lock
uv run alembic upgrade head   # crea/actualiza las tablas
uv run uvicorn app.main:app --reload
```

En otra terminal, el frontend:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Abre **<http://localhost:5173>**: sube un PDF en «Biblioteca» y pregunta en «Preguntar». En
desarrollo, Vite reenvía las peticiones `/api` al backend (puerto 8000), así que no hace falta
configurar CORS.

Backend directamente:

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
5. Se genera un **resumen** del documento con el LLM (si el documento es largo, a partir de
   fragmentos repartidos por todo él). Es opcional: si no hay LLM configurado o falla, el
   documento se completa igualmente sin resumen.
6. Los fragmentos, sus embeddings, el modelo que los generó (`embedding_model`), el resumen y
   el estado `completed` se guardan en **una sola transacción**: si algo falla, no quedan datos
   parciales.

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
    {"document_id": "…", "filename": "manual.pdf", "page_number": 1, "source_type": "chunk",
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

**Preguntas de resumen** («¿de qué trata?», «resume…», «ideas principales», «summarize»):
la búsqueda por similitud no sirve para ellas, así que se responden con los resúmenes de los
documentos. Esas fuentes llegan con `source_type: "summary"`, sin página, fragmento ni score
([ADR 0003](docs/decisions/0003-resumen-de-documentos.md)).

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

### Backend

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

### Frontend

Desde `frontend/`:

```bash
npm test                    # pruebas de componentes (Vitest + Testing Library, sin backend)
npm run typecheck           # TypeScript estricto
npm run lint                # oxlint
npm run build               # compilación de producción en dist/
```

Las pruebas simulan `fetch`, así que no necesitan el backend. Incluyen una prueba de seguridad:
una respuesta del LLM con HTML malicioso (`<img onerror>`, `<script>`, imágenes Markdown) debe
mostrarse como texto inerte.

## Evaluación del RAG

Un conjunto versionado de 5 documentos ficticios y 25 preguntas (datos concretos con otras
palabras, entre idiomas, resúmenes, prompt injection y preguntas sin respuesta) mide
recuperación, citas, contenido, abstención, latencia y costo. Desde `backend/`:

```bash
uv run python -m evaluation.run                     # gratis, con proveedores falsos
uv run python -m evaluation.run --provider openai   # real, ~$0.01
```

**Resultado con OpenAI (2026-10-24):** 25/25 preguntas correctas (recuperación, citas, datos,
abstención e inyección), mediana de 1.6 s por pregunta y $0.0035 en total. Con un conjunto
tan pequeño esto detecta regresiones; no demuestra una precisión general.

Metodología, resultados e interpretación en [`docs/rag-evaluation.md`](docs/rag-evaluation.md).

## Frontend

- **Biblioteca:** subida por clic o arrastrando (con validación previa de tipo y tamaño), lista
  con tamaño, fecha y estado, error de los documentos fallidos, reintentar y eliminar.
- **Detalle de documento:** metadatos, estado y resumen generado (con botón para generarlo si
  falta).
- **Preguntar:** respuesta con fuentes (documento, página y extracto) enlazadas al detalle del
  documento, y aviso explícito cuando no hay evidencia suficiente.
- **Estados** de carga, vacío, error y éxito en todas las pantallas; errores comprensibles, sin
  trazas ni detalles internos.
- **Accesibilidad básica:** etiquetas en los controles, navegación por teclado, foco visible,
  anuncios `aria-live` de los cambios de estado, estado comunicado con texto (no solo color) y
  contraste en modo claro y oscuro.
- **Seguridad:** la respuesta del LLM se muestra como texto plano. Nunca se usa
  `dangerouslySetInnerHTML` ni se interpreta Markdown, porque un documento malicioso podría
  inducir al LLM a devolver HTML o enlaces que ejecuten código o filtren datos.

## Dependencias

### Backend

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

### Frontend

| Paquete | Tipo | Propósito |
|---|---|---|
| react, react-dom | app | Interfaz de usuario |
| vite, @vitejs/plugin-react | dev | Servidor de desarrollo, proxy a la API y compilación |
| typescript | dev | Tipado estático (modo estricto) |
| oxlint | dev | Linter (incluido en la plantilla oficial de Vite) |
| vitest, jsdom | dev | Ejecutor de pruebas y DOM simulado |
| @testing-library/react, user-event, jest-dom | dev | Probar componentes como los usaría una persona |

## Limitaciones conocidas

- **Sin autenticación, autorización ni rate limiting**: todos los documentos son visibles para
  cualquiera que acceda. No exponer a Internet.
- **Procesamiento síncrono**: la subida espera a que termine el procesamiento; un PDF grande
  con OpenAI puede tardar decenas de segundos. La Fase 8 lo mueve a una cola con un worker.
- **PDF escaneados no soportados** (sin OCR): quedan `failed` con un mensaje explicativo.
  Tablas, columnas y figuras se extraen como texto plano, sin estructura.
- **Preguntas de resumen detectadas con una heurística** de patrones; con varios documentos,
  «¿de qué trata?» no indica cuál.
- **La abstención depende del LLM**, no del umbral: preguntas sin respuesta del mismo ámbito
  tienen tanta similitud como las que sí la tienen (ver
  [calibración](docs/rag-evaluation.md#openai-text-embedding-3-small--gpt-6-luna-2026-10-24-umbral-02)).
- **La búsqueda por palabras clave aporta poco** con preguntas naturales (exige todas las
  palabras); ver [hallazgos de la evaluación](docs/rag-evaluation.md#hallazgos-y-mejoras-posibles).
- **Sin historial de conversación**: cada pregunta es independiente.
- **Almacenamiento local**: los archivos viven en un volumen del servidor (S3 en la Fase 8).
- **Las capturas usan los proveedores falsos**: falta añadir capturas con respuestas reales
  del LLM (requiere saldo en OpenAI).
