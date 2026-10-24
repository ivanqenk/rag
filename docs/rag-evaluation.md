# Evaluación del RAG

Un sistema RAG puede «funcionar» (devolver texto) y aun así recuperar el fragmento equivocado,
inventar datos o no abstenerse cuando debe. Esta evaluación lo mide con un conjunto fijo y
versionado de documentos y preguntas, para comparar cambios (prompt, fragmentación, umbral,
modelo) con números y no con impresiones.

## Conjunto de evaluación (`backend/evaluation/dataset.json`, versión `eval-v1`)

Cinco documentos **ficticios** de una empresa inventada, guardados como texto (los PDF se
generan al ejecutar; no se versionan binarios):

| Documento | Idioma | Páginas | Contenido |
|---|---|---|---|
| `manual_empleado.pdf` | es | 3 | Jornada, vacaciones, permisos, teletrabajo, gastos |
| `seguridad_it.pdf` | es | 2 | Contraseñas, MFA, incidentes, equipos |
| `contrato_transporte.pdf` | es | 2 | Duración, precio, nivel de servicio, penalizaciones |
| `returns_policy.pdf` | en | 2 | Devoluciones, garantía, envíos |
| `acta_comite_flota.pdf` | es | 1 | Acta de reunión **con un intento de prompt injection** |

25 preguntas de seis tipos:

| Tipo | Cuántas | Qué comprueba |
|---|---|---|
| `fact` | 15 | Un dato concreto, **formulado con otras palabras** que el documento («trabajar desde casa» vs. «teletrabajar») |
| `cross_language` | 3 | Pregunta en un idioma y documento en otro |
| `injection` | 1 | Que la respuesta no obedezca las instrucciones escondidas en el documento |
| `summary` | 2 | «¿De qué trata…?» / «Resume…» (ver [ADR 0003](decisions/0003-resumen-de-documentos.md)) |
| `unanswerable` | 4 | Que se abstenga: preguntas del mismo ámbito pero sin respuesta en los documentos (salario, permiso de paternidad, contraseña del wifi) y una sin relación |

Cada pregunta indica el documento y la página esperados y los datos que debe contener la
respuesta (con alternativas: `"23"` o `"veintitrés"`).

## Métricas

| Métrica | Significado | Ideal |
|---|---|---|
| `retrieval_hit_rate` | El fragmento de la página esperada está entre los resultados que pasan el umbral | 1.0 |
| `citation_accuracy` | La respuesta cita el documento (y la página) esperados | 1.0 |
| `content_accuracy` | La respuesta contiene el dato esperado (aproximación a «respaldada») | 1.0 |
| `correct_abstention_rate` | Se abstiene en las preguntas sin respuesta | 1.0 |
| `false_abstention_rate` | Se abstiene en preguntas que **sí** tienen respuesta | 0.0 |
| `injection_resisted` | La respuesta no contiene el texto que pedía el documento malicioso | 1.0 |
| `latency_ms_p50` / `max` | Latencia de la consulta completa (búsqueda + LLM) | — |
| `query_cost_usd_avg` / `total_cost_usd` | Costo estimado por los tokens del LLM (incluye los resúmenes) | — |
| `min_similarity_answerable` / `max_similarity_unanswerable` | Para calibrar `RETRIEVAL_MIN_SCORE`: el umbral debería quedar entre ambos | — |

`content_accuracy` es una aproximación barata (buscar el dato en el texto); no detecta una
respuesta que contenga el número correcto con una afirmación falsa. Una evaluación más fina
usaría un LLM como juez o revisión humana (fuera del alcance del MVP).

## Cómo ejecutarla

Desde `backend/`, con PostgreSQL levantado (`docker compose up -d db`). Usa la base de
**pruebas** y la vacía al empezar; la de desarrollo no se toca.

```bash
uv run python -m evaluation.run                               # proveedores falsos (gratis)
uv run python -m evaluation.run --provider openai             # real (~$0.01)
uv run python -m evaluation.run --provider openai --pause 7   # cuentas con límite de 10 peticiones/min
```

Imprime una tabla por pregunta y las métricas, y guarda el informe completo (incluidas las
respuestas) en `backend/evaluation/results/` (ignorado por git). La suite de pruebas ejecuta
la evaluación con proveedores falsos (`tests/integration/test_evaluation.py`) para que el
script no se rompa sin que nadie lo note.

## Resultados

### Proveedores falsos (`fake-hashing-v2` + `fake-llm-v1`), 2026-10-24

| Métrica | Valor |
|---|---|
| `retrieval_hit_rate` | 0.105 |
| `citation_accuracy` | 0.095 |
| `content_accuracy` | 0.048 |
| `correct_abstention_rate` | 1.0 |
| `false_abstention_rate` | 0.81 |
| `injection_resisted` | 1.0 |
| `latency_ms_p50` | 5 ms |
| `total_cost_usd` | 0 |

**Interpretación.** Es el resultado esperado y sirve de **línea base**: el buscador falso
solo encuentra palabras exactas, y las preguntas del conjunto están formuladas a propósito con
otras palabras. Que acierte casi nada demuestra que el conjunto **distingue** entre buscar
palabras y entender el significado. Se abstiene bien en las preguntas sin respuesta, pero
porque no encuentra casi nada en general (81 % de abstenciones falsas). La «resistencia» a la
inyección no significa nada aquí: el LLM falso no lee instrucciones.

### OpenAI (`text-embedding-3-small` + `gpt-6-luna`)

**Pendiente:** requiere saldo en la cuenta de OpenAI. Cuando se ejecute, anotar aquí las
métricas, la fecha y, con `min_similarity_answerable` y `max_similarity_unanswerable`,
calibrar `RETRIEVAL_MIN_SCORE` (hoy 0.25, sin calibrar).

## Hallazgos y mejoras posibles

1. **La búsqueda por palabras clave aporta poco.** `websearch_to_tsquery` exige que el
   fragmento contenga **todas** las palabras de la pregunta («cuántos», «tengo», «al»…), lo que
   casi nunca ocurre con preguntas naturales. Mejora posible: combinar los términos con OR y
   ordenar por `ts_rank`, o usar un diccionario con palabras vacías (`spanish`), y medir el
   efecto con esta evaluación.
2. **Las preguntas de resumen dependen de una heurística** de patrones (ADR 0003).
3. **El conjunto es pequeño** (25 preguntas, 5 documentos): sirve para detectar regresiones
   y comparar cambios, no para afirmar una precisión general del sistema.
