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
| Umbral mínimo de similitud además del top-k | ✅ | Fase 4, `RETRIEVAL_MIN_SCORE`. Debe calibrarse con el conjunto de evaluación |
| Top-k acotado por el servidor; el cliente no puede pedir más | ✅ | Fase 4 |
| Búsqueda híbrida: vectorial + texto completo (`tsvector`), fusionadas con RRF | ✅ | Fase 4. Los embeddings fallan con nombres propios, códigos y números exactos |
| Búsqueda exacta primero; índice HNSW solo cuando el volumen lo justifique | ✅ | Fase 4: sin índice vectorial. Un índice aproximado puede perder resultados |
| Reranking con un segundo modelo | 🔜 | OpenAI no ofrece API de reranking; se evaluará en la Fase 7 con datos de evaluación |
| Filtrar permisos **dentro** de la consulta SQL, nunca después | 💼 | Ver «Aislamiento entre clientes» |

## 3. Generación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Prompt con reglas: solo usar el contexto, citar, abstenerse si no hay evidencia | 🔜 | Fase 5 |
| Documentos delimitados como datos (`<documento id=…>`), nunca como instrucciones | 🔜 | Fase 5 |
| Verificar que los IDs citados por el LLM estaban entre los recuperados; las fuentes mostradas salen de la BD | 🔜 | Fase 5. El LLM puede inventar citas |
| Respuesta estructurada (JSON: `answer`, `chunk_ids`, `insufficient_evidence`) | 🔜 | Fase 5 |
| Límite de fragmentos y de caracteres de contexto, no ampliable por el cliente | 🔜 | Fase 5 |
| Temperatura baja | 🔜 | Fase 5 |

## 4. Seguridad

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| **Prompt injection indirecta** (riesgo nº 1, OWASP LLM Top 10): el LLM no tiene herramientas, no ve secretos ni decide permisos | 🔜 | Fase 5. Las defensas son de diseño, no de redacción del prompt |
| La salida del LLM se renderiza como texto, no HTML (XSS, exfiltración por enlaces/imágenes markdown) | 🔜 | Fase 6 |
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
| Conocer la política del proveedor (entrenamiento, retención, región); DPA en un SaaS | 💼 | Ver `docs/decisions/0001-proveedor-embeddings.md` |
| Detección / anonimización de datos personales antes de enviarlos al proveedor | 💼 | Si los documentos contienen PII |
| Cifrado en tránsito (HTTPS) y en reposo (RDS, S3) | 🔜 | Fase 8 |

## 6. Calidad y evaluación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Pruebas sin llamadas de pago: proveedor falso determinista | ✅ | `FakeEmbeddingProvider` |
| Prueba opcional separada contra el proveedor real | ✅ | `pytest -m openai` |
| Conjunto de evaluación versionado (incluye preguntas sin respuesta) | 🔜 | Fase 7 |
| Medir recuperación (recall@k) y respuesta (fidelidad, abstención) por separado | 🔜 | Fase 7 |
| Repetir la evaluación al cambiar fragmentación, modelo, prompt o top-k | 🔜 | Fase 7 |

## 7. Operación

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Timeouts en toda llamada externa y errores claros cuando el proveedor falla | ✅ | Fase 4 (`503` en búsqueda, `failed` en ingestión) |
| Log por consulta: latencia por etapa, nº de resultados, mejores puntuaciones | ✅ | Fase 4; tokens y costo en la Fase 5 |
| Alertas de costo y errores | 🔜 | Fase 8 |

## 8. Desarrollo

| Práctica | Estado | Dónde / por qué |
|---|---|---|
| Proveedores detrás de una interfaz pequeña | ✅ | `EmbeddingProvider` (Protocol) |
| Parámetros del RAG configurables, no fijos en el código | ✅ | `app/core/config.py` |
| Migraciones para todo cambio de esquema, incluida la dimensión del vector | ✅ | `migrations/` |
| Prompts versionados en el código | 🔜 | Fase 5 |
