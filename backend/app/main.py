"""Punto de entrada de la aplicación FastAPI."""

import logging

from fastapi import FastAPI

from app.api import documents, health, query, search
from app.core.config import get_settings

# Uvicorn solo configura sus propios loggers; sin esto, los logs INFO de la aplicación
# (métricas de ingestión y búsqueda) se descartarían. Nunca se registra el texto de
# documentos ni preguntas, solo identificadores, conteos y tiempos.
logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="AI Document Intelligence Platform",
    version="0.1.0",
    description="API para cargar documentos PDF y consultarlos mediante RAG.",
)

# /health va sin prefijo; las rutas de negocio usarán /api/v1.
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(query.router)
