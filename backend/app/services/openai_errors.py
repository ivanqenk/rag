"""Clasificación de errores de la API de OpenAI compartida por los proveedores."""

import openai

# OpenAI responde 429 tanto por exceso de velocidad (reintentar sirve) como por falta de
# saldo (reintentar no sirve: hay que añadir crédito). Se distinguen por el código del error.
_QUOTA_CODES = {"insufficient_quota", "credit_balance_exhausted"}


def is_quota_exhausted(exc: openai.OpenAIError) -> bool:
    return isinstance(exc, openai.RateLimitError) and bool({exc.code, exc.type} & _QUOTA_CODES)
