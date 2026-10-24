# Buenas prácticas de RAG aplicadas en este proyecto

Guía de referencia de desarrollo, seguridad, privacidad y calidad para un sistema RAG, con el
estado de cada práctica en este repositorio.

**Leyenda:** ✅ implementado · 🔜 se implementa en la fase indicada · 👤 acción manual de la
persona que despliega · 💼 solo necesario si el proyecto pasa a ser un SaaS multi-cliente
(fuera del alcance del MVP).

---

## 1. Ingestión

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Validar tamaño, tipo real (extensión + firma `%PDF-` + apertura) y nº de páginas; ignorar el `Content-Type` del cliente | ✅ | `services/ingestion.py`, `services/pdf_extraction.py` |
| Nombres de archivo aleatorios, fuera de lo servido por HTTP, sin path traversal | ✅ | `services/storage.py` |
| Procedencia de cada fragmento (documento, página, posición) para poder citar | ✅ | tabla `document_chunks` |
| Reprocesado idempotente y transaccional (sin duplicados ni fragmentos parciales) | ✅ | `process_document` |
| Registrar qué modelo generó cada embedding (`embedding_model`) | ✅ | Fase 4. Cambiar de modelo exige reindexar; así se sabe qué vectores son obsoletos |
| Embeddings por lotes, con timeout y reintentos con backoff | ✅ | Fase 4, `services/embeddings.py` |
| Detección de duplicados por `checksum_sha256` | 💼 | El hash ya se guarda; falta la política (rechazar / reutilizar) |

## 2. Recuperación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Mismo modelo para documentos y preguntas; solo se comparan vectores del modelo activo | ✅ | Fase 4, `services/retrieval.py` |
| Umbral mínimo de similitud además del top-k | ✅ | Fase 4, `RETRIEVAL_MIN_SCORE`. La evaluación informa los valores para calibrarlo; pendiente de ejecutarla con OpenAI (👤 saldo) |
| Top-k acotado por el servidor; el cliente no puede pedir más | ✅ | Fase 4 |
| Búsqueda híbrida: vectorial + texto completo (`tsvector`), fusionadas con RRF | ✅ | Fase 4. Los embeddings fallan con nombres propios, códigos y números exactos |
| Búsqueda exacta primero; índice HNSW solo cuando el volumen lo justifique | ✅ | Fase 4: sin índice vectorial. Un índice aproximado puede perder resultados |
| Reranking con un segundo modelo | 💼 | OpenAI no ofrece API de reranking. Mejora futura; medir su efecto con `evaluation/run.py` antes de adoptarlo |
| Filtrar permisos **dentro** de la consulta SQL, nunca después | 💼 | Ver «Aislamiento entre clientes» |

## 3. Generación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Prompt con reglas: solo usar el contexto, citar, abstenerse si no hay evidencia | ✅ | `services/prompts.py` |
| Documentos delimitados como datos (`<fuente id=…>`, texto escapado), nunca como instrucciones | ✅ | `build_user_message`: un documento no puede cerrar su etiqueta ni fingir otra fuente |
| Verificar que los IDs citados por el LLM estaban entre los recuperados; las fuentes mostradas salen de la BD | ✅ | `services/rag.py`. Sin ninguna cita válida, la respuesta se trata como no respaldada |
| Respuesta estructurada (JSON: `answer`, `cited_sources`, `insufficient_evidence`) | ✅ | Structured Outputs de OpenAI con el esquema `LLMAnswer` |
| Límite de fragmentos y de caracteres de contexto, no ampliable por el cliente | ✅ | `RETRIEVAL_TOP_K`, `RAG_MAX_CONTEXT_CHARS`; `/query` solo acepta la pregunta |
| Fidelidad sobre creatividad | ✅ | `gpt-6-luna` no documenta `temperature`; se usa esfuerzo de razonamiento bajo + esquema fijo (ADR 0002) |
| Sin evidencia no se llama al LLM | ✅ | Ahorra costo y elimina respuestas inventadas |

## 4. Seguridad

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| **Prompt injection indirecta** (riesgo nº 1, OWASP LLM Top 10): el LLM no tiene herramientas, no ve secretos ni decide permisos | ✅ | Fase 5. Las defensas son de diseño, no de redacción del prompt. Prueba real opcional en `tests/external/test_openai_llm.py` |
| La salida del LLM se renderiza como texto, no HTML (XSS, exfiltración por enlaces/imágenes markdown) | ✅ | `frontend/src/pages/AskPage.tsx`, sin `dangerouslySetInnerHTML` ni Markdown; prueba con HTML malicioso en `AskPage.test.tsx` |
| Errores comprensibles en la interfaz, sin trazas ni detalles internos | ✅ | `frontend/src/api/client.ts` |
| Límite de longitud de las preguntas | ✅ | Fase 4, `MAX_QUERY_CHARS` |
| Secretos solo en `.env` (ignorado por Git) o gestor de secretos; nunca en logs ni frontend | ✅ | `.gitignore`, `.env.example` |
| Límite de gasto mensual en el panel del proveedor | 👤 | Configuración manual en platform.openai.com |
| Rate limiting y cuotas por usuario | 💼 | Obligatorio antes de exponer a Internet |
| Lockfile de dependencias | ✅ | `uv.lock` |
| Auditoría de vulnerabilidades en dependencias | ✅ | `pip-audit` + Dependabot (`.github/dependabot.yml`) |
| Aislamiento entre clientes: `tenant_id` en todas las consultas + Row-Level Security en PostgreSQL | 💼 | El error más grave posible en un RAG multi-cliente es recuperar documentos de otro cliente |

## 5. Privacidad

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Logs sin texto de documentos ni preguntas: solo IDs, conteos, tiempos y puntuaciones | ✅ | Ingestión y búsqueda |
| Tratar los embeddings como datos sensibles (se puede reconstruir parcialmente el texto) | ✅ | Nunca se devuelven por la API |
| Borrado real: archivo + fragmentos + embeddings (derecho al olvido) | ✅ | `DELETE /api/v1/documents/{id}` |
| No guardar conversaciones en el proveedor | ✅ | `store=False` en cada llamada al LLM |
| No guardar preguntas ni respuestas en nuestra base de datos sin una razón explícita | ✅ | No existe tabla `queries` (opcional en la especificación) |
| Conocer la política del proveedor (entrenamiento, retención, región); DPA en un SaaS | 💼 | Ver ADR 0001 y 0002 en `docs/decisions/` |
| Detección / anonimización de datos personales antes de enviarlos al proveedor | 💼 | Si los documentos contienen PII |
| Cifrado en tránsito (HTTPS) y en reposo (RDS, S3) | 🔜 | Fase 8 |

## 6. Calidad y evaluación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Pruebas sin llamadas de pago: proveedor falso determinista | ✅ | `FakeEmbeddingProvider` |
| Prueba opcional separada contra el proveedor real | ✅ | `pytest -m openai`: embeddings, respuesta citada, abstención y prompt injection |
| Conjunto de evaluación versionado (incluye preguntas sin respuesta) | ✅ | Fase 7, `backend/evaluation/dataset.json` (25 preguntas, incluye prompt injection) |
| Medir recuperación (recall@k) y respuesta (fidelidad, abstención) por separado | ✅ | Fase 7, [`rag-evaluation.md`](rag-evaluation.md). La fidelidad se aproxima comprobando el dato esperado |
| Repetir la evaluación al cambiar fragmentación, modelo, prompt o top-k | ✅ | `uv run python -m evaluation.run`; el informe registra modelos, versiones de prompt y umbral |

## 7. Operación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Timeouts en toda llamada externa y errores claros cuando el proveedor falla | ✅ | Fase 4 (`503` en búsqueda, `failed` en ingestión) |
| Log por consulta: latencia por etapa, resultados, citas, tokens, costo estimado, modelo y versión del prompt | ✅ | `services/rag.py`, sin texto de la pregunta ni de la respuesta |
| Alertas de costo y errores | 🔜 | Fase 8 |

## 8. Desarrollo

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Proveedores detrás de una interfaz pequeña | ✅ | `EmbeddingProvider` (Protocol) |
| Parámetros del RAG configurables, no fijos en el código | ✅ | `app/core/config.py` |
| Migraciones para todo cambio de esquema, incluida la dimensión del vector | ✅ | `migrations/` |
| Prompts versionados en el código | ✅ | `services/prompts.py` (`PROMPT_VERSION`) |
