# 0003 — Resumen automático de documentos

**Estado:** aceptada · **Fecha:** 2026-10-23 · **Fase:** 7 (ampliación aprobada del alcance)

## Contexto

La búsqueda RAG recupera los fragmentos **más parecidos a la pregunta**. Las preguntas de
resumen («¿de qué trata?», «resúmelo») no se parecen a ningún fragmento concreto: o no
superan el umbral de similitud (el sistema se abstiene) o recuperan unos pocos trozos
sueltos que no representan el documento. Es una limitación conocida del RAG básico.

## Opciones

| Opción | Ventajas | Desventajas |
|---|---|---|
| **A. Resumen al procesar** | Una llamada por documento, una sola vez; el resumen se muestra también en la página del documento | Más tiempo y costo de ingestión; el resumen de un documento muy largo se basa en una muestra |
| B. Detectar la pregunta y pasar el principio del documento | Sin costo de ingestión | Solo ve el principio; con documentos largos falla |
| C. Botón «Resumir» bajo demanda | Sin adivinar la intención | Una llamada al LLM cada vez; no ayuda en el chat |

## Decisión

**Opción A**:

- Al procesar un documento, tras los embeddings, se pide al LLM un resumen de 3-5 frases
  (prompt versionado `doc-summary-v1`, salida estructurada, `store=False`, sin herramientas).
- Si el documento supera `SUMMARY_MAX_INPUT_CHARS` (12 000 caracteres), se envían fragmentos
  **repartidos a lo largo de todo el documento** (principio, medio y final), no solo el
  principio.
- El resumen es **opcional**: si no hay LLM configurado o el proveedor falla, el documento
  queda `completed` sin resumen y es consultable con normalidad. Al reprocesar, si el nuevo
  resumen falla, se conserva el anterior (describe el mismo archivo).
- Las preguntas de resumen se detectan con una **heurística de patrones** (español e inglés,
  sin tildes): «de qué trata», «resum…», «ideas principales», «summarize», «what is this
  document about»… Para ellas, el contexto del LLM son los resúmenes de los documentos
  procesados (los más recientes primero, dentro del límite de contexto), con la misma
  verificación de citas que el RAG normal. La fuente se marca `source_type: "summary"`.
  Si no hay resúmenes, se usa la búsqueda normal.

## Costo

Con `gpt-6-luna` ($0.10 / $0.50 por millón de tokens): 12 000 caracteres ≈ 3 000 tokens de
entrada + ~200 de respuesta y razonamiento ≈ **$0.0004 por documento**, una sola vez.

## Consecuencias y limitaciones

- La heurística puede fallar en ambos sentidos: una pregunta de resumen con otras palabras
  («explícame este PDF») sigue el camino normal, y una pregunta concreta que contenga
  «resumen» usa los resúmenes. Alternativa futura: clasificar la intención con el LLM
  (una llamada extra por pregunta).
- Con muchos documentos, «¿de qué trata?» no indica cuál: el LLM recibe hasta 20 resúmenes
  y responde con los relevantes. No hay selección de documento en la interfaz (futuro).
- El resumen de un documento muy largo se basa en una muestra y puede omitir partes.
- El resumen es texto generado por un LLM: el frontend lo muestra como texto plano y avisa
  de que puede contener errores.
