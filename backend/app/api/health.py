"""Endpoint de salud: permite comprobar que la aplicación está viva."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Intencionalmente mínimo: no expone versión, host, configuración ni secretos.
    return HealthResponse(status="ok")
