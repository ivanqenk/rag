# 0002 — Proveedor de LLM: OpenAI `gpt-6-luna`

**Estado:** aceptada · **Fecha:** 2026-10-23 · **Fase:** 5

## Contexto

El LLM redacta la respuesta a partir de los fragmentos recuperados. Se eligió OpenAI para
embeddings (ADR 0001), así que una sola cuenta y clave cubren ambos. Es el componente de
costo variable más importante: se paga en **cada** pregunta.

## Opciones (página oficial de precios, octubre 2026, USD por millón de tokens)

| Modelo | Entrada | Salida | Uso recomendado por OpenAI |
|---|---|---|---|
| **`gpt-6-luna`** | $0.10 | $0.50 | Tareas acotadas y de alto volumen |
| `gpt-6.1-sol` | $2.00 | $10.00 | Trabajo complejo a costo moderado |
| `gpt-6-astra` | $10.00 | $50.00 | Máxima capacidad |

## Decisión

`gpt-6-luna` mediante la API Responses, con:

- **Structured Outputs** (`text_format=LLMAnswer`): la respuesta siempre es JSON válido con
  `answer`, `cited_sources` e `insufficient_evidence`; no hay que interpretar texto libre.
- **`reasoning.effort = "low"`**: es un modelo de razonamiento; responder a partir de
  fragmentos dados no necesita razonamiento largo, y menos esfuerzo = menos tokens y latencia.
  La documentación del modelo no menciona `temperature`, así que no se usa; el esquema fijo y
  el prompt restrictivo cumplen el objetivo de "fidelidad sobre creatividad".
- **`store = False`**: OpenAI no guarda la conversación (no la reutilizamos).
- **Sin herramientas** (`tools`): el LLM no puede ejecutar acciones.

## Consecuencias

- **Costo estimado:** ~2,500 tokens de entrada (5 fragmentos + instrucciones) y ~300 de
  salida por pregunta ≈ **$0.0004**. Con $1, unas 2,500 preguntas. Cada consulta registra en
  el log los tokens reales y el costo estimado (`LLM_INPUT/OUTPUT_PRICE_PER_MTOK`).
- **Sin evidencia no se llama al LLM**: si la búsqueda no encuentra nada relevante, la API
  responde que no hay evidencia sin gastar tokens.
- Si la calidad no alcanza (se medirá en la Fase 7), el siguiente paso es `gpt-6.1-sol`
  cambiando solo `LLM_MODEL`.
- **Pruebas:** `FakeLLMProvider` en toda la suite; pruebas reales opcionales con
  `uv run pytest -m openai -s` (respuesta citada, abstención y resistencia a prompt injection).
