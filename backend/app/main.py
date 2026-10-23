"""Punto de entrada de la aplicación FastAPI."""

from fastapi import FastAPI

from app.api import documents, health

app = FastAPI(
    title="AI Document Intelligence Platform",
    version="0.1.0",
    description="API para cargar documentos PDF y consultarlos mediante RAG.",
)

# /health va sin prefijo; las rutas de negocio usarán /api/v1.
app.include_router(health.router)
app.include_router(documents.router)
