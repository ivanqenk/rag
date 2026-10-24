"""Límites de uso: frecuencia por cliente, presupuesto diario de OpenAI y cuotas de almacenamiento.

Protegen el gasto y el servidor mientras no hay usuarios (después serán por usuario u
organización):

- Frecuencia (429 + Retry-After): ventana deslizante en memoria por dirección IP. Es por
  proceso: con varias réplicas haría falta un almacén compartido (Redis) o el límite del
  balanceador o del API Gateway (Fase 8).
- Presupuesto diario (429): suma el costo estimado de cada consulta y documento en
  `usage_daily`, que sobrevive a reinicios. Se comprueba ANTES de gastar; una consulta en
  curso puede pasarse un poco del límite (fracciones de centavo).
- Cuotas (403): número de documentos y espacio ocupado, incluida la papelera.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.repositories.usage import UsageRepository


class SlidingWindowLimiter:
    """Cuenta eventos por clave en una ventana de tiempo que se desliza (no por minutos de
    reloj: así no se pueden hacer 2× peticiones juntando el final de un minuto y el inicio del
    siguiente)."""

    # Cada cuántos eventos se olvidan las claves sin actividad reciente.
    SWEEP_EVERY = 1000

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._events: dict[str, deque[float]] = {}
        self._windows: dict[str, float] = {}
        self._lock = threading.Lock()
        self._now = clock
        self._hits = 0

    def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Registra un evento. Devuelve None si se permite, o los segundos que faltan para
        poder repetirlo si se supera el límite (y entonces no lo registra)."""
        now = self._now()
        with self._lock:
            self._hits += 1
            if self._hits % self.SWEEP_EVERY == 0:
                self._sweep(now)
            events = self._events.setdefault(key, deque())
            self._windows[key] = window_seconds
            self._expire(events, now, window_seconds)
            if len(events) >= limit:
                return events[0] + window_seconds - now
            events.append(now)
            return None

    @staticmethod
    def _expire(events: deque[float], now: float, window_seconds: float) -> None:
        while events and events[0] <= now - window_seconds:
            events.popleft()

    def _sweep(self, now: float) -> None:
        """Olvida las claves sin eventos en su ventana: la memoria no crece con cada IP nueva."""
        for key in list(self._events):
            self._expire(self._events[key], now, self._windows[key])
            if not self._events[key]:
                del self._events[key], self._windows[key]


_limiter = SlidingWindowLimiter()


def get_rate_limiter() -> SlidingWindowLimiter:
    """Dependencia de FastAPI: un limitador por proceso. Las pruebas usan uno nuevo cada vez."""
    return _limiter


Limiter = Annotated[SlidingWindowLimiter, Depends(get_rate_limiter)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]


def _client_key(request: Request) -> str:
    # Detrás de nginx, uvicorn toma la IP de X-Forwarded-For (--proxy-headers), que nginx
    # sobrescribe con la IP real: el cliente no puede inventarse otra para saltarse el límite.
    return request.client.host if request.client else "desconocido"


def _too_many(retry_after: float, message: str) -> HTTPException:
    seconds = max(1, math.ceil(retry_after))
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        message.format(seconds=seconds),
        headers={"Retry-After": str(seconds)},
    )


def _check_budget(session: Session, settings: Settings) -> None:
    if not settings.daily_budget_usd:
        return
    spent = float(UsageRepository(session).today().cost_usd)
    if spent >= settings.daily_budget_usd:
        now = datetime.now(UTC)
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
        raise _too_many(
            (midnight - now).total_seconds(),
            f"Se alcanzó el límite de gasto diario en el proveedor de IA "
            f"(${settings.daily_budget_usd:.2f}). Vuelve a intentarlo mañana.",
        )


def enforce_query_limits(
    request: Request, limiter: Limiter, settings: SettingsDep, session: DbSession
) -> None:
    """Para /query y /search."""
    limit = settings.rate_limit_queries_per_minute
    if limit:
        retry = limiter.hit(f"query:{_client_key(request)}", limit, 60)
        if retry is not None:
            raise _too_many(
                retry, "Demasiadas preguntas seguidas. Espera {seconds} s e inténtalo de nuevo."
            )
    _check_budget(session, settings)


def enforce_upload_limits(
    request: Request, limiter: Limiter, settings: SettingsDep, session: DbSession
) -> None:
    """Para subir y reprocesar documentos (embeddings y resumen cuestan dinero)."""
    limit = settings.rate_limit_uploads_per_hour
    if limit:
        retry = limiter.hit(f"upload:{_client_key(request)}", limit, 3600)
        if retry is not None:
            minutes = max(1, math.ceil(retry / 60))
            raise _too_many(
                retry,
                f"Has alcanzado el máximo de {limit} subidas por hora. "
                f"Inténtalo dentro de {minutes} min.",
            )
    _check_budget(session, settings)


def check_storage_quota(session: Session, settings: Settings, new_bytes: int) -> None:
    """Antes de guardar un archivo nuevo."""
    storage = UsageRepository(session).storage()
    if settings.max_documents and storage.documents >= settings.max_documents:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Se alcanzó el máximo de {settings.max_documents} documentos. Elimina alguno y "
            "vacía la papelera para subir más.",
        )
    max_bytes = settings.max_storage_mb * 1024 * 1024
    if settings.max_storage_mb and storage.bytes + new_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Se alcanzó el espacio máximo ({settings.max_storage_mb} MB). Elimina documentos "
            "y vacía la papelera para liberar espacio.",
        )


QueryLimits = Depends(enforce_query_limits)
UploadLimits = Depends(enforce_upload_limits)
