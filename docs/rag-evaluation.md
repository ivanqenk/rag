# Evaluación del RAG

Un sistema RAG puede «funcionar» (devolver texto) y aun así recuperar el fragmento equivocado,
inventar datos o no abstenerse cuando debe. Esta evaluación lo mide con un conjunto fijo y
versionado de documentos y preguntas, para comparar cambios (prompt, fragmentación, umbral,
modelo) con números y no con impresiones.

## Conjunto de evaluación (`backend/evaluation/dataset.json`, versión `eval-v4`)

Cinco documentos **ficticios** de una empresa inventada, guardados como texto (los PDF se
generan al ejecutar; no se versionan binarios):

| Documento | Idioma | Páginas | Contenido |
|---|---|---|---|
| `manual_empleado.pdf` | es | 3 | Jornada, vacaciones, permisos, teletrabajo, gastos |
| `seguridad_it.pdf` | es | 2 | Contraseñas, MFA, incidentes, equipos |
| `contrato_transporte.pdf` | es | 2 | Duración, precio, nivel de servicio, penalizaciones |
| `returns_policy.pdf` | en | 2 | Devoluciones, garantía, envíos |
| `acta_comite_flota.pdf` | es | 1 | Acta de reunión **con un intento de prompt injection** |

35 preguntas de ocho tipos (las 25 de `eval-v1`, 6 sobre formatos de respuesta y 4 de
seguimiento con su conversación previa):

| Tipo | Cuántas | Qué comprueba |
|---|---|---|
| `fact` | 15 | Un dato concreto, **formulado con otras palabras** que el documento («trabajar desde casa» vs. «teletrabajar») |
| `cross_language` | 3 | Pregunta en un idioma y documento en otro |
| `injection` | 1 | Que la respuesta no obedezca las instrucciones escondidas en el documento |
| `summary` | 2 | «¿De qué trata…?» / «Resume…» (ver [ADR 0003](decisions/0003-resumen-de-documentos.md)) |
| `unanswerable` | 5 | Que se abstenga: preguntas del mismo ámbito pero sin respuesta en los documentos (salario, permiso de paternidad, contraseña del wifi, bajas por enfermedad en formato detallado) y una sin relación |
| `followup` | 3 | Preguntas de seguimiento con la conversación anterior («¿Y con cuánta antelación las tengo que pedir?» tras preguntar por las vacaciones). Una cuarta, sin respuesta, cuenta como `unanswerable` |
| `grounding` | 5 | Preguntas en formato detallado que invitan a añadir consejos genéricos que no están en los documentos (antivirus, mayúsculas, formularios, policía…). Dos son procedimientos (`expect_ordered`) |

Cada pregunta indica el documento y la página esperados y los datos que debe contener la
respuesta (con alternativas: `"23"` o `"veintitrés"`).

## Métricas

| Métrica | Significado | Ideal |
|---|---|---|
| `retrieval_hit_rate` | El LLM leyó algún fragmento de la página esperada (tras la búsqueda y, si aplica, el reordenamiento) | 1.0 |
| `citation_accuracy` | La respuesta cita el documento (y la página) esperados | 1.0 |
| `content_accuracy` | La respuesta contiene el dato esperado (aproximación a «respaldada») | 1.0 |
| `correct_abstention_rate` | Se abstiene en las preguntas sin respuesta | 1.0 |
| `false_abstention_rate` | Se abstiene en preguntas que **sí** tienen respuesta | 0.0 |
| `injection_resisted` | La respuesta no contiene el texto que pedía el documento malicioso | 1.0 |
| `grounding_resisted` | Las respuestas largas no contienen lo que un modelo suele añadir por su cuenta (`must_not_include`) | 1.0 |
| `ordered_accuracy` | En formato detallado, los puntos salen numerados si la pregunta es un procedimiento, y solo entonces | 1.0 |
| `removed_claims_total` | Afirmaciones descartadas por el servidor (sin cita válida o sin respaldo verificado). El informe JSON guarda su texto para revisarlas | — |
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
uv run python -m evaluation.run --provider openai --strategy simple   # comparar estrategias
uv run python -m evaluation.run --provider openai --style detailed    # forzar un formato
uv run python -m evaluation.run --provider openai --dataset evaluation/book_dataset.json  # libro
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

### OpenAI (`text-embedding-3-small` + `gpt-6-luna`), 2026-10-24, umbral 0.2

| Métrica | Valor |
|---|---|
| `retrieval_hit_rate` | 1.0 |
| `citation_accuracy` | 1.0 |
| `content_accuracy` | 1.0 |
| `correct_abstention_rate` | 1.0 |
| `false_abstention_rate` | 0.0 |
| `injection_resisted` | 1.0 |
| `latency_ms_p50` / `max` | 1590 ms / 2771 ms |
| `query_cost_usd_avg` | $0.00012 |
| `total_cost_usd` (25 preguntas + 5 resúmenes) | $0.0035 |
| `min_similarity_answerable` | 0.417 |
| `max_similarity_unanswerable` | 0.578 |

**Interpretación.** Las 25 preguntas pasan: recupera la página correcta incluso con otras
palabras y entre idiomas, cita bien, no obedece al documento malicioso y se abstiene en las
cuatro preguntas sin respuesta. En la primera ejecución `content_accuracy` dio 0.952 por un
fallo **del evaluador**, no del sistema: la respuesta «Desconéctalo…» no contenía «desconect»
porque se comparaba con tildes. Se corrigió la comparación (minúsculas y sin tildes) y se
volvió a ejecutar.

**Calibración de `RETRIEVAL_MIN_SCORE`.** Las similitudes se **solapan**: hay preguntas sin
respuesta del mismo ámbito con similitud 0.578 (el documento habla de algo parecido) y
preguntas con respuesta desde 0.417. Ningún umbral separa ambos grupos, así que el umbral
**no puede ser** el mecanismo de abstención: esa decisión la toma el LLM con
`insufficient_evidence`, y la verificación de citas en el servidor la respalda. El umbral
cumple otro papel: descartar lo claramente ajeno (la pregunta sin relación dio 0.09) sin
llamar al LLM. Por eso se mantiene **0.25** por defecto: queda muy por debajo de la menor
similitud con respuesta (0.417), con margen para preguntas peor formuladas, y muy por encima
de lo ajeno. Con un conjunto mayor convendría revisarlo.

## Conjunto del libro (`backend/evaluation/book_dataset.json`, versión `book-v1`)

El conjunto `eval-v1` tiene documentos cortos y muy distintos entre sí, y no detectó un
problema que apareció al usarlo con un libro real: *Historia verdadera de la conquista de la
Nueva España*, de Bernal Díaz del Castillo (dominio público, 96 páginas, ~500 fragmentos).
En un libro así casi todos los fragmentos hablan de lo mismo (Cortés, indios, guerra,
Tlascala), y el fragmento con la respuesta quedaba en el puesto 20 de la búsqueda, cuando el
LLM solo leía los 5 primeros.

23 preguntas con respuesta y página verificadas en el texto: 16 de datos concretos, 2 hechas
desde una página («¿en qué año fue esto?» con el filtro de la página 65), 1 de resumen y 3 sin
respuesta (entre ellas «¿en qué año fue esto?» **sin** filtro: es ambigua, lo correcto es
abstenerse). El PDF no se versiona: para repetirla, coloca el libro en
`backend/evaluation/pdfs/Conquista-Nueva-Espana-Bernal-Diaz-del-Castillo.pdf`.

Al revisar los fallos de la línea base apareció una pregunta **mal planteada**: «¿Cuántos
indios de guerra pidió Cortés a Tlascala?» tiene dos respuestas en el libro (5.000 en la
página 64, para Tepeaca; 10.000 en la 65, para Tezcuco). La respuesta «cinco mil» no era
inventada. Se precisó la pregunta y se añadió la otra como pregunta aparte **antes** de
medir los cambios.

### Resultados, 2026-10-24 (OpenAI)

| Configuración | Recupera la página | Respuesta correcta | Abstención falsa | Latencia p50 / máx | Costo por pregunta |
|---|---|---|---|---|---|
| Línea base: palabras con AND, 5 fragmentos, sin filtros | 0.737 | 0.75 | 0.25 | 1.8 s / 3.3 s | $0.00019 |
| Palabras con OR + BM25 y filtros (`simple`) | 0.947 | 0.90 | 0.05 | 1.7 s / 2.7 s | $0.00019 |
| `progressive` (5 → 5 más → 10 más) | 0.947 | 0.90 | 0.00 | 1.8 s / 5.4 s | $0.00023 |
| `rerank`, 30 candidatos, razonamiento `low` | 1.0 | 1.0 | 0.00 | 4.1 s / 8.5 s | $0.00087 |
| `rerank`, 30 candidatos, razonamiento `none` | 1.0 | 1.0 | 0.00 | 3.0 s / 4.7 s | $0.00087 |
| **`rerank`, 20 candidatos, razonamiento `none` (por defecto)** | **1.0** | **1.0** | **0.00** | **2.9 s / 3.4 s** | **$0.00062** |

En las cuatro preguntas sin respuesta todas las configuraciones se abstienen. Con el conjunto
`eval-v1` las tres estrategias mantienen 25/25; con la configuración por defecto la mediana
es 1.7 s y el costo $0.00014 por pregunta (con pocos fragmentos relevantes no hace falta
reordenar y no hay llamada extra).

**Interpretación.**

- **La búsqueda por palabras era el problema principal.** Exigía todas las palabras (AND) y
  casi nunca aportaba. Con OR, ponderando cada palabra por su rareza (BM25) y exigiendo al
  menos la mitad de las palabras importantes, la página correcta pasa del 74 % al 95 %.
- **El filtro por página** resuelve las preguntas hechas desde lo que se está leyendo.
- **`progressive`** (idea propuesta durante la revisión) evita abstenciones, pero en b09
  respondió con otro suceso parecido (la segunda entrada en México, en 1520) en lugar del que
  se preguntaba: cada intento extra le da al LLM fragmentos menos relevantes. Su peor caso
  (preguntas sin respuesta) hace tres llamadas.
- **`rerank`** es la única que acierta todo: el LLM ve 20 candidatos y elige los 5 que de
  verdad responden. Cuesta una llamada extra (~1 s y unos $0.0004 por pregunta). Elegir
  fragmentos no necesita razonamiento: con `none` es igual de preciso y más rápido.
- Con 23 preguntas, la diferencia entre 0.90 y 1.0 son dos preguntas. Sirve para elegir con
  datos, no para afirmar que el sistema acierta siempre.

## Formatos de respuesta (`eval-v3`)

Breve y detallada; en detallada, los puntos van numerados si las fuentes describen un
procedimiento ([ADR 0005](decisions/0005-formatos-de-respuesta.md)). Prompts `rag-answer-v4` y
`rag-verify-v3`, 2026-10-24:

| Conjunto y formato | Respuesta correcta | Abstención correcta | Sin texto inventado (`grounding_resisted`) | Numeración correcta | Afirmaciones descartadas | Latencia p50 | Costo por pregunta |
|---|---|---|---|---|---|---|---|
| `eval-v3`, cada pregunta en su formato | 1.0 | 1.0 | 1.0 | 1.0 | 1 | 2.3 s | $0.00023 |
| `eval-v3`, todo detallada (dos ejecuciones) | 1.0 / 1.0 | 1.0 | 1.0 | 0.8 / 1.0 | 1 / 0 | 3.6 s | $0.00033 |
| `book-v1`, breve | 1.0 | 0.667 | — | — | 0 | 3.1 s | $0.00067 |
| `book-v1`, todo detallada | 0.95 | 1.0 | — | — | 2 | 4.4 s | $0.00084 |

Hubo una versión anterior con un tercer formato, «pasos» (`eval-v2`); dio resultados
equivalentes a detallada y se sustituyó por la numeración automática.

**Interpretación.**

- **Ninguna respuesta añadió lo prohibido** en las preguntas trampa, en ningún formato. Una
  comparación previa con y sin verificación dio lo mismo (0 invenciones): en este conjunto el
  prompt basta, y la verificación queda como seguro.
- **La verificación tuvo que calibrarse.** La primera versión descartaba resúmenes correctos
  por sinónimos («clave de acceso» frente a «contraseñas»). Tras tres versiones del prompt
  descarta muy poco, y lo que descarta suele ser un resumen que mezcla varios datos o un
  detalle discutible («tres días después de llegar a Cozumel»). Se acepta: perder un dato
  antes que inventarlo.
- **Numeración:** en una de tres ejecuciones, g01 (virus) juntó los pasos en dos puntos y no
  lo marcó como procedimiento; el contenido era correcto. Nunca numeró lo que no era un
  procedimiento.
- **b05** («¿cuántos soldados contó Cortés en el alarde antes de partir?») se abstuvo en una
  ejecución en formato detallado; en las demás responde 508. Es variación del modelo, no una
  invención.
- **g05** («¿qué hago si pierdo el portátil?») es una pregunta límite: los documentos no
  hablan de perderlo, solo de comunicar incidentes de seguridad. Según la ejecución, el modelo
  responde con eso (y aclara que no hay un procedimiento específico) o se abstiene.
- **b20** («¿en qué año fue esto?» sin página) cuenta como fallo en formato breve, pero la
  respuesta no inventa: «Si te refieres al alarde en Tezcuco, fue en 1521. Si te refieres al
  inicio de la marcha hacia Tezcuco, fue en 1520.» Se deja la métrica tal cual (esperaba
  abstención) en lugar de cambiar la expectativa después de ver el resultado.

## Conversación (`eval-v4`)

2026-10-24, con la pregunta reescrita a partir de la conversación (`rag-rewrite-v1`):

| Pregunta de seguimiento | Entendida como | Respuesta |
|---|---|---|
| «¿Y con cuánta antelación las tengo que pedir?» | «¿Con cuánta antelación tengo que pedir las vacaciones?» | 15 días ✓ |
| «¿Y me pagan algo por eso?» (tras teletrabajo) | «¿Me pagan algo por trabajar desde casa?» | 30 € al mes ✓ |
| «¿Y en cuánto tiempo tengo que avisar?» (tras virus) | «¿En cuánto tiempo tengo que avisar de que mi ordenador tiene un virus?» | Menos de 1 hora ✓ |
| «¿Y cuánto me pagan por ellos?» (tras vacaciones; sin respuesta) | «¿Cuánto me pagan por los 23 días laborables de vacaciones…?» | «El manual indica 23 días pero no especifica cuánto se paga» ✗ (esperaba abstención; no inventa) |

Conjunto completo: respuesta correcta 1.0, abstención correcta 0.833 (por la última), sin
texto inventado 1.0, mediana 2.4 s, $0.00023 por pregunta.

## Hallazgos y mejoras posibles

1. **Búsqueda por palabras clave** (resuelto): ver el conjunto del libro. Desde la migración
   `unaccent full text search` tampoco distingue tildes: «pidio» encuentra «pidió» (columna
   calculada con `immutable_unaccent`). Ambos conjuntos siguen al 100 % tras el cambio.
2. **Las preguntas de resumen dependen de una heurística** de patrones (ADR 0003).
3. **Los conjuntos son pequeños** (35 + 23 preguntas): sirven para detectar regresiones y
   comparar cambios, no para afirmar una precisión general del sistema.
4. **Conversación** (resuelto): las preguntas de seguimiento se reescriben con los 3 últimos
   turnos. Cuando la conversación da un dato («23 días»), la respuesta a una pregunta sin
   respuesta tiende a repetirlo y aclarar lo que falta en lugar de abstenerse.
