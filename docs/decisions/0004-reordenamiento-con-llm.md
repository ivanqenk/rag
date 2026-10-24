# ADR 0004: reordenar los candidatos con el LLM antes de responder

- **Estado:** aceptada (2026-10-24)
- **Relacionado:** [evaluación](../rag-evaluation.md#conjunto-del-libro-backendevaluationbook_datasetjson-versión-book-v1), `RAG_STRATEGY` en `backend/app/core/config.py`

## Contexto

Con un libro largo y homogéneo (96 páginas, ~500 fragmentos que hablan casi todos de lo
mismo) el RAG fallaba en preguntas sencillas: el fragmento con la respuesta quedaba en el
puesto 20 de la búsqueda y el LLM solo leía los 5 primeros. La búsqueda por palabras
tampoco ayudaba, porque exigía que el fragmento contuviera todas las palabras de la pregunta.

## Opciones evaluadas (mismas 23 preguntas, con OpenAI)

| Opción | Respuesta correcta | Latencia p50 | Costo por pregunta |
|---|---|---|---|
| `simple`: los 5 primeros de la búsqueda (con la búsqueda por palabras corregida) | 90 % | 1.7 s | $0.00019 |
| `progressive`: 5; si no hay evidencia, los 5 siguientes; luego 10 más | 90 % | 1.8 s (máx. 5.4 s) | $0.00023 |
| `rerank`: la búsqueda trae 20 candidatos y el LLM elige los 5 más útiles | **100 %** | 2.9 s | $0.00062 |
| Pasar el libro entero al LLM (*long context*) | no medido | mucho mayor | ~$0.012 (100 veces más) y no escala a muchos documentos |
| Modelo de reordenamiento dedicado (cross-encoder, Cohere Rerank…) | no medido | — | otro proveedor o un modelo local pesado para esta máquina |

## Decisión

`RAG_STRATEGY=rerank` por defecto, con 20 candidatos (`RAG_RERANK_CANDIDATES`) y sin
razonamiento para esa llamada (`RAG_RERANK_REASONING_EFFORT=none`: elegir fragmentos es más
sencillo que redactar; con `low` acertaba igual y tardaba 1 s más). Las otras estrategias se
mantienen configurables para poder volver a compararlas.

Además, la búsqueda por palabras pasa a OR con puntuación BM25 (cuenta más una palabra rara
que una frecuente) y exige al menos la mitad de las palabras importantes de la pregunta, para
que una palabra suelta no convierta en «evidencia» un fragmento sin relación.

## Consecuencias

- Una llamada extra al LLM por pregunta cuando hay más candidatos que los que se leen: ~1 s y
  ~$0.0004 más. Con pocos documentos no hay llamada extra.
- El reordenamiento usa el mismo proveedor y las mismas defensas: candidatos delimitados y
  escapados como datos, salida estructurada (solo ids) y ids validados en el servidor. Si la
  llamada falla o no elige nada, se usa el orden de la búsqueda: mejora la precisión, pero no
  es imprescindible para responder.
- La medición se basa en 23 preguntas: la diferencia entre 90 % y 100 % son dos preguntas.
  Hay que repetirla al cambiar de modelo, prompt o tamaño de fragmento.
