"""Punto de entrada de la aplicación FastAPI."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, folders, health, query, search, trash
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.processing import resume_unfinished
from app.services.trash import purge_periodically

# Uvicorn solo configura sus propios loggers; sin esto, los logs INFO de la aplicación
# (métricas de ingestión y búsqueda) se descartarían. Nunca se registra el texto de
# documentos ni preguntas, solo identificadores, conteos y tiempos.
logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Al arrancar: retoma los documentos que quedaron a medias y lanza la purga periódica de
    la papelera. Al parar, cancela la purga."""
    settings = get_settings()
    resume = None
    if settings.processing_mode == "background":
        # En un hilo: procesar puede tardar y no debe retrasar el arranque. Se guarda la
        # referencia para que el recolector de basura no descarte la tarea.
        resume = asyncio.create_task(asyncio.to_thread(resume_unfinished, SessionLocal, settings))
    task = asyncio.create_task(purge_periodically(SessionLocal, settings))
    yield
    del resume
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    lifespan=lifespan,
    title="AI Document Intelligence Platform",
    version="0.1.0",
    description="API para cargar documentos PDF y consultarlos mediante RAG.",
)

# /health va sin prefijo; las rutas de negocio usarán /api/v1.
app.include_router(health.router)
app.include_router(documents.router)
app.include_router(folders.router)
app.include_router(trash.router)
app.include_router(search.router)
app.include_router(query.router)
