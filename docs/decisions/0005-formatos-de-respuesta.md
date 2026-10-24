# ADR 0005: formatos de respuesta sin inventar

- **Estado:** aceptada (2026-10-24)
- **Relacionado:** [evaluación](../rag-evaluation.md#formatos-de-respuesta-eval-v2), `app/services/rag.py`, `app/services/prompts.py`

## Contexto

Todas las respuestas eran un párrafo corto. Para preguntas como «¿qué hago si mi ordenador
tiene un virus?» hace falta una lista de pasos, y para otras, más detalle. Pero cuanto más
larga es una respuesta, más fácil es que el LLM añada algo que no está en los documentos
(consejos genéricos, pasos «razonables», cifras aproximadas). Requisito del usuario: los
formatos largos no pueden inventar ni añadir nada.

## Decisión

Tres formatos (`answer_style` en `/api/v1/query`): **breve** (una o dos frases, por defecto),
**detallada** (resumen y puntos) y **pasos** (lista ordenada).

La respuesta es **datos estructurados, no Markdown**: `answer` + `points[]`, y cada punto con
sus propias fuentes. El frontend lo dibuja como texto, así que un documento malicioso no puede
colar HTML ni enlaces (mismo criterio que antes), y cada afirmación se puede comprobar por
separado.

Cuatro capas contra lo inventado:

1. **Prompt** (`rag-answer-v3`): solo lo que aparece en las fuentes; prohibido añadir
   consejos, pasos o cifras «razonables»; mejor menos puntos que uno sin respaldo; ante una
   pregunta ambigua no elegir una interpretación.
2. **Citas por punto verificadas en el servidor**: un punto sin ninguna cita válida se
   descarta; las fuentes devueltas son solo las de lo que queda.
3. **Verificación independiente** (`rag-verify-v3`, `RAG_VERIFY_ANSWERS`, en detallada y
   pasos): una segunda llamada, sin razonamiento, compara cada afirmación con el texto de SUS
   fuentes y se descarta lo no respaldado. Recibe la pregunta para entender sus términos.
4. **Evaluación** con preguntas trampa que invitan a añadir consejos genéricos (antivirus,
   mayúsculas en las contraseñas, formularios, policía…).

## Calibración de la verificación

La primera versión del verificador era demasiado literal: rechazaba «una clave de acceso debe
tener al menos 14 caracteres» porque el documento dice «contraseñas», y frases introductorias
como «los pasos son:». En la práctica descartaba resúmenes correctos (falsos positivos). Con
una batería de 9 afirmaciones (4 respaldadas con paráfrasis, 5 inventadas), las versiones
sucesivas del prompt:

| Versión | Cambio | Resultado |
|---|---|---|
| v1 | «ante la duda, false» | Rechaza sinónimos y frases introductorias |
| v2 | Paráfrasis y sinónimos cuentan; las introducciones no afirman hechos | A veces acepta «al menos 12» cuando el texto dice 14 |
| v3 | Las cifras deben coincidir exactamente; recibe la pregunta | 12/12 ejecuciones correctas |

Esa batería es ahora una prueba contra el proveedor real
(`tests/external/test_openai_llm.py`).

## Consecuencias

- Detallada y pasos tardan ~1–1.5 s más que breve (una llamada más) y cuestan ~$0.0003 por
  pregunta frente a ~$0.0002.
- En la evaluación, el prompt por sí solo ya no inventó nada (con y sin verificación:
  0 respuestas con texto prohibido). La verificación es un **seguro**: su coste medido es
  descartar de vez en cuando un resumen correcto que combina varios datos (los puntos quedan).
  Se prefiere perder un dato a mostrar uno inventado.
- Con 31 preguntas no se puede afirmar que nunca invente: se puede medir y detectar si
  empeora al cambiar de modelo o de prompt.
