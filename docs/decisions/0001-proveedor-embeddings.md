# 0001 — Proveedor de embeddings: OpenAI `text-embedding-3-small`

**Estado:** aceptada · **Fecha:** 2026-10-23 · **Fase:** 4

## Contexto

El RAG necesita convertir fragmentos y preguntas en vectores. La dimensión del vector queda
fija en la columna `document_chunks.embedding`, así que cambiar de modelo exige una migración
y reprocesar todos los documentos. El proyecto imita un SaaS: los modelos deben consumirse
por API, sin cargar el equipo de desarrollo (portátil sin GPU, 6.7 GB de RAM en WSL).

## Opciones evaluadas (precios de las páginas oficiales, octubre 2026)

| Opción | Precio | Dimensión | Pros | Contras |
|---|---|---|---|---|
| **OpenAI `text-embedding-3-small`** | $0.02 / 1M tokens | 1536 | Una sola cuenta y clave para embeddings y LLM | De pago desde el primer token (céntimos) |
| Voyage `voyage-4` | $0.06 / 1M, 200M tokens gratis | 1024 | Gratis a esta escala, alta calidad | Otra cuenta; límites bajos sin tarjeta |
| Ollama `bge-m3` (local) | Gratis | 1024 | Privado, sin clave | Lento en CPU; quien evalúe debe instalarlo |

## Decisión

OpenAI `text-embedding-3-small`, 1536 dimensiones, por API.

## Consecuencias

- **Costo estimado:** ~900 tokens por página (+25% por el solapamiento). 100 PDF de 50
  páginas ≈ 5.6M tokens ≈ **$0.11**. Las preguntas son despreciables (~30 tokens cada una).
- **Privacidad:** el texto de los fragmentos y las preguntas se envía a OpenAI. Según su
  política para la API, por defecto no se usa para entrenar y se retiene hasta 30 días para
  vigilancia de abusos; verificar la política vigente antes de cargar documentos reales o
  sensibles. En un SaaS: DPA con el proveedor, retención cero y elección de región.
- **Cambio de proveedor:** la interfaz `EmbeddingProvider` lo aísla. Cada fragmento guarda
  `embedding_model`; la búsqueda solo compara vectores del modelo activo, y
  `POST /api/v1/documents/{id}/reprocess` regenera los de un documento.
- **Pruebas:** `FakeEmbeddingProvider` (determinista, sin red) en toda la suite. La prueba
  contra la API real es opcional: `uv run pytest -m openai`.
- **Umbral de similitud:** `RETRIEVAL_MIN_SCORE=0.25` es un valor inicial; calibrarlo con el
  conjunto de evaluación de la Fase 7.
- **Protección de costos:** configurar un límite de gasto mensual en platform.openai.com.
