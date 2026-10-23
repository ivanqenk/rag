# AI Document Intelligence Platform
## Especificación funcional y técnica para Claude Code / Codex

**Estado:** Plan inicial del MVP  
**Objetivo:** construir un proyecto de portafolio que demuestre backend Python, APIs, PostgreSQL con búsqueda vectorial, RAG, frontend TypeScript/React, pruebas y despliegue reproducible.  
**Principio de ejecución:** implementar de forma incremental, mantener la aplicación ejecutable al final de cada fase y evitar complejidad que no sea necesaria para el MVP.

---

## 1. Instrucciones para el agente de código

Actúa como un ingeniero de software senior y mentor técnico. Ayuda a implementar esta especificación por fases, sin intentar generar todo el sistema de una sola vez.

### Reglas de trabajo
1. Antes de modificar archivos, inspecciona el repositorio y resume su estado.
2. Si el repositorio está vacío, crea la estructura mínima necesaria para la fase actual.
3. Implementa **una fase o tarea pequeña a la vez**. Explica brevemente las decisiones importantes.
4. No afirmes que algo funciona sin ejecutar las pruebas o comandos pertinentes cuando el entorno lo permita.
5. Mantén el código sencillo, tipado, modular y legible para alguien que está aprendiendo Python y FastAPI.
6. Evita abstracciones prematuras, microservicios, Kubernetes y patrones complejos que no estén justificados.
7. No agregues dependencias sin explicar su propósito.
8. No guardes secretos, tokens, claves API, credenciales ni documentos privados en el repositorio.
9. Usa variables de entorno y proporciona un `.env.example` sin valores secretos.
10. Mantén las pruebas actualizadas. No deshabilites ni elimines pruebas para hacer pasar la suite.
11. Al terminar cada tarea, informa: archivos modificados, decisiones tomadas, comandos ejecutados, resultados de pruebas y siguiente tarea.
12. Si una decisión esencial está sin definir, presenta una recomendación concreta y pide confirmación solo cuando elegir mal pueda causar retrabajo significativo.
13. No cambies de tecnología o alcance sin explicar la razón y solicitar aprobación.
14. No implementes funcionalidades futuras antes de completar los criterios de aceptación de la fase actual.
15. Prioriza seguridad, mantenibilidad y evidencia verificable sobre velocidad aparente.

### Flujo recomendado para cada tarea
- Inspeccionar el estado actual.
- Identificar requisitos y criterios de aceptación.
- Proponer un plan corto.
- Implementar el cambio mínimo completo.
- Ejecutar formato, lint y pruebas disponibles.
- Revisar errores, seguridad básica y regresiones.
- Actualizar documentación.
- Resumir el resultado y sugerir la siguiente tarea.

---

## 2. Visión del producto

AI Document Intelligence Platform es una aplicación web que permite cargar documentos PDF, extraer y fragmentar su texto, generar embeddings, almacenarlos en PostgreSQL con pgvector y hacer preguntas en lenguaje natural. Las respuestas deben apoyarse en fragmentos recuperados y mostrar las fuentes utilizadas.

### Usuario objetivo del MVP
Un único usuario de demostración que administra una colección de documentos. La autenticación multiusuario y los permisos complejos quedan fuera del primer MVP.

### Problema que resuelve
Permite consultar información contenida en documentos sin tener que leerlos manualmente, con referencias que permitan comprobar de dónde salió la respuesta.

### Objetivos de aprendizaje y portafolio
- Python y FastAPI.
- Diseño y documentación de APIs REST.
- PostgreSQL, SQLAlchemy, Alembic y pgvector.
- Procesamiento de PDF y pipelines de ingestión.
- Embeddings, búsqueda por similitud y RAG.
- React y TypeScript.
- Pruebas automatizadas.
- Docker Compose y, en una fase posterior, AWS y Terraform.
- Seguridad básica, manejo de errores y observabilidad.

---

## 3. Alcance funcional del MVP

### Incluido
1. Cargar archivos PDF con límites de tamaño.
2. Validar extensión, tipo de archivo, tamaño y contenido extraído.
3. Guardar archivos localmente fuera del directorio público durante el desarrollo.
4. Registrar metadatos y estado de procesamiento.
5. Extraer texto por página.
6. Dividir el texto en fragmentos configurables con solapamiento.
7. Generar embeddings a través de una interfaz de proveedor.
8. Guardar fragmentos y embeddings en PostgreSQL + pgvector.
9. Buscar fragmentos relevantes por similitud semántica.
10. Enviar los fragmentos recuperados a un LLM para generar una respuesta.
11. Mostrar la respuesta con referencias al documento y página cuando estén disponibles.
12. Mostrar lista de documentos y estado de procesamiento.
13. Mostrar errores comprensibles cuando el PDF no tenga texto, el proveedor falle o no haya evidencia suficiente.
14. Incluir pruebas automatizadas y documentación para ejecutar el proyecto.

### Fuera de alcance inicial
- OCR para PDFs escaneados.
- Autenticación multiusuario y multitenancy.
- Roles y permisos granulares.
- Agentes autónomos o servidor MCP.
- Kafka, microservicios y Kubernetes.
- Entrenamiento o fine-tuning de modelos.
- Editor de documentos.
- Integración con CMS.
- Despliegue productivo de alta disponibilidad.
- Procesamiento de Office, HTML o imágenes como fuentes independientes; se podrán evaluar después.

---

## 4. Arquitectura

### Estilo arquitectónico
Monolito modular con frontend separado. Un único backend FastAPI contiene la API, lógica de negocio y pipeline de ingestión/RAG. PostgreSQL es la base de datos principal y pgvector agrega almacenamiento y búsqueda vectorial.

### Componentes

**Frontend**
- React
- TypeScript
- Vite
- Cliente HTTP tipado
- Pantallas para biblioteca, carga, estado de procesamiento y preguntas/respuestas

**Backend**
- Python 3.12
- FastAPI
- Pydantic para validación y configuración de esquemas
- SQLAlchemy 2.x para acceso a datos
- Alembic para migraciones
- PyMuPDF para extracción de texto PDF
- pytest y HTTPX para pruebas

**Persistencia**
- PostgreSQL
- Extensión pgvector
- Archivos almacenados en volumen local durante el desarrollo
- S3 como mejora futura

**IA**
- Proveedor de embeddings intercambiable mediante una interfaz pequeña
- Proveedor de generación de texto intercambiable mediante una interfaz pequeña
- Recuperación semántica en PostgreSQL/pgvector
- RAG con contexto limitado, instrucciones contra respuestas no respaldadas y referencias a las fuentes

**Ejecución**
- Docker Compose para PostgreSQL y servicios locales cuando sea conveniente
- Backend y frontend ejecutables localmente durante las primeras fases
- AWS y Terraform después de que el flujo local esté probado

### Flujo de ingestión
1. El cliente envía un PDF al endpoint de carga.
2. El backend valida el archivo y aplica límites configurables.
3. Se crea un registro de documento con estado `pending`.
4. El MVP inicial puede procesar sincrónicamente o mediante una tarea local controlada. La interfaz debe permitir introducir una cola real después sin rediseñar la lógica de negocio.
5. El servicio de ingestión extrae texto por página.
6. El texto se fragmenta con parámetros configurables.
7. Se generan embeddings en lotes cuando el proveedor lo permita.
8. Se guardan fragmentos, metadatos y vectores.
9. El documento pasa a `completed`; ante un fallo, pasa a `failed` con un mensaje seguro y útil.
10. La API expone el estado al frontend.

**Nota:** no introducir SQS en el MVP local. Se incorporará en una fase posterior, conservando separada la lógica de procesamiento.

### Flujo de consulta RAG
1. El cliente envía una pregunta.
2. El backend valida la entrada.
3. Se genera un embedding para la pregunta.
4. pgvector recupera los mejores fragmentos por similitud.
5. Se aplican límites de cantidad de fragmentos y tamaño total de contexto.
6. El backend solicita al LLM una respuesta basada en el contexto recuperado.
7. El sistema devuelve respuesta, referencias y metadatos básicos.
8. Si no hay evidencia suficiente, responde de manera explícita que no puede responder con los documentos disponibles.

### Principios de diseño
- No mezclar controladores HTTP con lógica de negocio.
- No acoplar la aplicación a un proveedor de IA específico.
- Mantener las consultas SQL y operaciones de persistencia claras y testeables.
- Usar migraciones versionadas.
- Mantener el texto extraído y sus referencias al documento/página.
- No confiar en nombres, extensiones ni MIME types enviados por el cliente.
- No registrar texto completo de documentos ni secretos en logs por defecto.
- No usar respuestas generadas por LLM como sustituto de validación o autorización.
- Usar búsqueda vectorial exacta para la primera validación; evaluar HNSW cuando haya datos y métricas que lo justifiquen.

---

## 5. Modelo de datos inicial

El esquema puede evolucionar con migraciones; no crear un sistema genérico excesivo.

### `documents`
Campos sugeridos:
- `id`: UUID, clave primaria.
- `original_filename`: nombre original saneado.
- `storage_key`: identificador o ruta interna del archivo.
- `content_type`: tipo detectado/validado.
- `size_bytes`: tamaño del archivo.
- `checksum_sha256`: hash para identificar duplicados potenciales.
- `status`: `pending`, `processing`, `completed` o `failed`.
- `error_code`: código interno opcional.
- `error_message`: mensaje seguro y no sensible opcional.
- `created_at`, `updated_at`, `processed_at`: timestamps.

### `document_chunks`
Campos sugeridos:
- `id`: UUID, clave primaria.
- `document_id`: clave foránea a `documents`, con política explícita al borrar.
- `chunk_index`: orden del fragmento en el documento.
- `page_number`: número de página, si se conoce.
- `text`: contenido del fragmento.
- `token_count` o estimación equivalente, si resulta útil.
- `embedding`: columna pgvector con dimensión definida según el modelo elegido.
- `created_at`: timestamp.

Restricciones e índices:
- Restricción única para `(document_id, chunk_index)`.
- Índice por `document_id`.
- Índice vectorial HNSW solo cuando el tamaño/mediciones lo justifique.
- La dimensión de `embedding` debe coincidir con el modelo seleccionado; documentar esta decisión.

### `queries` (opcional para el primer MVP)
- `id`: UUID.
- `question`: pregunta del usuario.
- `answer`: respuesta producida.
- `created_at`: timestamp.
- Se pueden guardar referencias como JSON estructurado si se necesita historial.
- No guardar conversaciones o contenido sensible sin una razón explícita.

### Reglas de integridad
- La ingestión fallida no debe dejar fragmentos parciales utilizables como si el documento estuviera completo.
- Reprocesar un documento debe sustituir sus fragmentos de manera transaccional o mediante una estrategia segura de versionado.
- Eliminar un documento debe limpiar sus fragmentos y el archivo asociado siguiendo una política documentada.
- Nunca asumir que una dimensión de embedding puede cambiar sin migración/reindexado.

---

## 6. API inicial

Usar prefijo `/api/v1`.

### Salud
- `GET /health`
  - Devuelve estado básico de la aplicación.
  - No debe exponer secretos ni información de infraestructura.

### Documentos
- `POST /api/v1/documents`
  - Multipart upload de PDF.
  - Devuelve `201 Created` con metadatos y estado.
  - Errores esperados: `400`, `413`, `415`, `422`.
- `GET /api/v1/documents`
  - Devuelve lista paginada, ordenada por fecha descendente.
- `GET /api/v1/documents/{document_id}`
  - Devuelve metadatos y estado.
- `DELETE /api/v1/documents/{document_id}`
  - Elimina documento y fragmentos de acuerdo con la política definida.
- `POST /api/v1/documents/{document_id}/reprocess`
  - Puede posponerse si no cabe en el MVP inicial.

### Consulta RAG
- `POST /api/v1/query`
  - Request: pregunta y parámetros limitados opcionales.
  - Response: respuesta, referencias, identificadores de fragmento y puntuaciones cuando sean útiles.
  - No permitir que el cliente imponga límites arbitrarios de contexto o costo.

### Formato orientativo de respuesta RAG
```json
{
  "answer": "Respuesta basada en los documentos disponibles.",
  "sources": [
    {
      "document_id": "uuid",
      "filename": "manual.pdf",
      "page_number": 3,
      "chunk_id": "uuid",
      "excerpt": "Fragmento breve que respalda la respuesta."
    }
  ],
  "insufficient_evidence": false
}
```

La API debe documentar validaciones, códigos de error y límites. No devolver rutas físicas del servidor.

---

## 7. Frontend

### Vistas mínimas
1. **Biblioteca de documentos**
   - Lista de archivos.
   - Fecha, tamaño y estado.
   - Indicadores de procesamiento y error.
2. **Carga de documentos**
   - Selector o zona de arrastrar/soltar.
   - Validación de tamaño y tipo en cliente como comodidad, además de la validación del servidor.
   - Mensajes de progreso/resultado.
3. **Consulta**
   - Campo de pregunta.
   - Respuesta del sistema.
   - Fuentes citadas y enlace a los metadatos del documento.
   - Mensaje claro cuando no hay evidencia suficiente.

### Requisitos de interfaz
- Manejar estados de carga, vacío, error y éxito.
- No mostrar errores internos ni stack traces.
- Mantener accesibilidad básica: etiquetas, navegación por teclado y contraste adecuado.
- No implementar un sistema de diseño complejo en el MVP.
- Mantener tipos de las respuestas de API en TypeScript.

---

## 8. Seguridad y fiabilidad

1. Establecer un límite de tamaño configurable para las cargas.
2. Validar PDF con más de una señal; no confiar solo en extensión o `Content-Type`.
3. Generar nombres internos aleatorios para archivos y evitar path traversal.
4. Guardar los archivos fuera del directorio servido públicamente.
5. No ejecutar macros ni contenido activo de documentos.
6. No incluir secretos en Git. Agregar `.env` al `.gitignore`.
7. Proporcionar `.env.example` con valores ficticios/no secretos.
8. Configurar timeouts y manejo de errores para proveedores externos.
9. Limitar tamaño de pregunta, número de fragmentos recuperados y tamaño de contexto.
10. Tratar el texto de los documentos como datos no confiables: un documento puede contener prompt injection. Las instrucciones del documento no deben autorizar herramientas, revelar secretos ni cambiar políticas.
11. No permitir que el LLM decida permisos de acceso.
12. Registrar eventos operativos sin registrar contenido sensible por defecto.
13. En el MVP de un solo usuario, dejar claro que no es un servicio público listo para producción.
14. Añadir rate limiting y autenticación antes de exponer la aplicación a Internet.

---

## 9. Estrategia de pruebas

### Pruebas unitarias
- Fragmentación de texto y solapamiento.
- Extracción de texto de PDF.
- Manejo de PDF vacío o sin texto.
- Validación de entradas.
- Construcción de contexto para RAG.
- Tratamiento de ausencia de fuentes relevantes.

### Pruebas de integración
- Conexión con PostgreSQL y pgvector.
- Crear/listar/eliminar documentos.
- Guardar y consultar embeddings.
- Flujo de ingestión completo con proveedores simulados.
- Manejo de fallos durante ingestión y consulta.

### Pruebas de evaluación RAG
Crear un pequeño conjunto versionado de documentos de prueba y preguntas con respuestas esperadas. Evaluar:
- Si el fragmento relevante aparece entre los resultados recuperados.
- Si la respuesta está respaldada por las fuentes.
- Si se abstiene cuando no existe evidencia.
- Latencia y costo aproximado por consulta.

Las pruebas automatizadas no deben depender de llamadas pagadas a un LLM real. Simular los proveedores en la suite general y mantener una prueba de integración opcional separada.

---

## 10. Estructura sugerida del repositorio

```text
ai-document-intelligence/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── documents.py
│   │   │   └── query.py
│   │   ├── core/
│   │   │   └── config.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── base.py
│   │   ├── models/
│   │   │   ├── document.py
│   │   │   └── document_chunk.py
│   │   ├── schemas/
│   │   │   ├── document.py
│   │   │   └── query.py
│   │   ├── repositories/
│   │   └── services/
│   │       ├── storage.py
│   │       ├── pdf_extraction.py
│   │       ├── chunking.py
│   │       ├── embeddings.py
│   │       ├── retrieval.py
│   │       └── rag.py
│   ├── migrations/
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── types/
│   │   └── main.tsx
│   ├── package.json
│   └── Dockerfile
├── infra/
│   └── terraform/
├── docs/
│   ├── architecture.md
│   ├── decisions/
│   └── rag-evaluation.md
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

Esta estructura es el objetivo de evolución, no una exigencia de crear todos los directorios en el primer commit.

---

## 11. Fases de desarrollo y criterios de aceptación

### Fase 0 — Preparación
- Inspeccionar herramientas instaladas y estado del repositorio.
- Crear README inicial, `.gitignore` y `.env.example`.
- Crear estructura mínima de backend y frontend.
- Documentar cómo ejecutar los componentes.

**Aceptación:** repositorio limpio, sin secretos, con instrucciones iniciales reproducibles.

### Fase 1 — API básica
- Configurar Python 3.12 y FastAPI.
- Implementar `GET /health`.
- Implementar una primera ruta de documentos usando datos temporales solo para validar el flujo.
- Añadir pytest y HTTPX.
- Activar documentación OpenAPI.

**Aceptación:** servidor arranca, endpoints responden y las pruebas pasan.

### Fase 2 — PostgreSQL
- Añadir PostgreSQL a Docker Compose.
- Conectar SQLAlchemy.
- Configurar Alembic.
- Crear tabla `documents`.
- Implementar creación, listado y detalle persistentes.

**Aceptación:** los datos sobreviven al reinicio del backend y las migraciones pueden aplicarse desde cero.

### Fase 3 — Ingestión PDF
- Implementar carga y almacenamiento local seguro.
- Extraer texto por página.
- Fragmentar texto con configuración explícita.
- Gestionar estados y fallos.
- Añadir pruebas para PDFs válidos, vacíos e inválidos.

**Aceptación:** un PDF válido produce fragmentos rastreables y los errores no dejan documentos falsamente completados.

### Fase 4 — Embeddings y pgvector
- Habilitar la extensión pgvector.
- Seleccionar un modelo de embeddings y documentar dimensiones, costo y proveedor.
- Implementar interfaz de proveedor.
- Generar y persistir embeddings.
- Implementar búsqueda semántica y pruebas.

**Aceptación:** una consulta devuelve fragmentos pertinentes en un conjunto pequeño de documentos de prueba.

### Fase 5 — RAG
- Seleccionar un proveedor LLM.
- Construir contexto limitado con los fragmentos recuperados.
- Crear endpoint de consulta.
- Devolver fuentes con página y fragmento.
- Añadir comportamiento de abstención ante evidencia insuficiente.
- Probar con proveedores simulados.

**Aceptación:** la respuesta incluye fuentes, maneja preguntas no respondibles y la suite no necesita llamadas pagadas.

### Fase 6 — Frontend
- Crear biblioteca de documentos.
- Crear formulario de carga.
- Crear pantalla de consulta y referencias.
- Manejar carga, errores y estados vacíos.
- Verificar integración con API.

**Aceptación:** el usuario puede completar el flujo principal desde la interfaz.

### Fase 7 — Calidad y portafolio
- Completar pruebas unitarias y de integración.
- Crear conjunto de evaluación RAG.
- Añadir Dockerfiles y Docker Compose para el entorno completo.
- Documentar arquitectura y decisiones.
- Añadir capturas o demostración, instrucciones de ejecución y limitaciones.

**Aceptación:** una persona distinta puede ejecutar el proyecto siguiendo el README y verificar el flujo principal.

### Fase 8 — Extensión cloud (posterior al MVP)
- Almacenar archivos en S3.
- Incorporar SQS y worker para procesamiento asíncrono.
- Crear recursos AWS mediante Terraform.
- Configurar IAM de mínimo privilegio, logs, métricas y gestión de secretos.
- Documentar costos y destrucción segura de recursos.

**Aceptación:** despliegue reproducible en un entorno AWS de prueba y procesamiento recuperable ante fallos.

---

## 12. Plan estimado para una persona principiante

Con unas 2 horas diarias, reservar aproximadamente 6 semanas para el MVP local, con margen para aprender y depurar:

- Semana 1: Python aplicado y FastAPI.
- Semana 2: PostgreSQL, SQLAlchemy y migraciones.
- Semana 3: carga de PDF, extracción y fragmentación.
- Semana 4: embeddings, pgvector y recuperación.
- Semana 5: RAG y frontend inicial.
- Semana 6: integración, pruebas, documentación y demo.

El alcance puede necesitar más tiempo. Si una fase se retrasa, reducir funcionalidades opcionales antes que saltarse pruebas o seguridad.

---

## 13. Decisiones técnicas pendientes

No inventes estas decisiones silenciosamente. Propón una opción por defecto y explica brevemente las ventajas y desventajas antes de implementarla:

1. **Proveedor de embeddings:** costo, dimensiones, calidad y facilidad de configuración.
2. **Proveedor de LLM:** costo, límites, privacidad y calidad.
3. **Dimensión de pgvector:** debe coincidir con el modelo seleccionado.
4. **Fragmentación:** tamaño y solapamiento inicial, validado con ejemplos.
5. **Procesamiento:** síncrono/simple para el primer flujo local; arquitectura desacoplada para añadir worker y SQS después.
6. **Gestión de archivos:** almacenamiento local en desarrollo y S3 más adelante.
7. **Autenticación:** fuera del MVP de demostración, pero obligatoria antes de exponerlo públicamente.

No se debe asumir que un proveedor específico está configurado ni que hay claves disponibles. Mantener los proveedores detrás de interfaces pequeñas para poder cambiarlos.

---

## 14. Primer prompt para iniciar el trabajo con Claude Code o Codex

Copia el siguiente prompt en el agente una vez que estés en el directorio del proyecto:

> Lee el documento de especificación completo y síguelo como fuente principal de requisitos.
>
> Comienza únicamente con la Fase 0 y la primera parte de la Fase 1. Inspecciona el repositorio y las herramientas disponibles antes de realizar cambios. Si el repositorio está vacío, crea la estructura mínima, configura Python 3.12, FastAPI, un endpoint `GET /health`, las dependencias de pruebas y las instrucciones de ejecución. No implementes PostgreSQL, pgvector, embeddings, RAG ni frontend todavía.
>
> Explica cada paso con claridad porque estoy aprendiendo Python/FastAPI. Ejecuta las pruebas disponibles, informa los resultados reales y no afirmes que algo pasó si no lo verificaste. No agregues dependencias ni archivos que no sean necesarios para esta tarea. Al terminar, resume los archivos creados, comandos ejecutados, resultados y siguiente tarea.

---

## 15. Definición de terminado del MVP

El MVP se considerará terminado cuando un evaluador pueda:

1. Clonar el repositorio.
2. Configurar variables de entorno siguiendo el README.
3. Levantar el backend, frontend y PostgreSQL.
4. Cargar un PDF.
5. Ver su estado de procesamiento.
6. Hacer una pregunta relacionada con el documento.
7. Obtener una respuesta con fuentes verificables.
8. Ejecutar las pruebas y comprender la arquitectura a partir de la documentación.

**Principio rector:** construir una funcionalidad completa, probada y explicable antes de pasar a la siguiente. El objetivo no es producir mucho código generado por IA; es poder defender las decisiones y demostrar que el sistema funciona.
