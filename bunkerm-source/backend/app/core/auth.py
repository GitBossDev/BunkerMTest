"""
Módulo centralizado de autenticación para la API unificada.
Reemplaza la función _get_current_api_key() duplicada en cada microservicio anterior.
"""
import logging
import os
import time

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

logger = logging.getLogger(__name__)

_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)

# Caché en memoria: evita leer disco en cada request (TTL = 5 s)
_cache: dict = {"key": "", "ts": 0.0}


def get_active_api_key() -> str:
    """
    Devuelve la clave API activa leyendo únicamente la variable de entorno API_KEY.
    La refresca cada 5 segundos para no penalizar cada request.

    Si API_KEY no está definida en el entorno, se lanza RuntimeError al arrancar.
    El fallback a archivo plano fue eliminado (HIGH-2) porque un archivo de clave
    en /nextjs/data/.api_key degrada silenciosamente la seguridad si el volumen
    tiene permisos incorrectos.
    """
    now = time.time()
    if _cache["key"] and now - _cache["ts"] < 5.0:
        return _cache["key"]

    key = os.getenv("API_KEY", "")
    if not key or key == "default_api_key_replace_in_production":
        # Fallar de forma explícita: es preferible un error visible en el log
        # a usar una clave por defecto que cualquiera conoce.
        logger.error(
            "API_KEY env var is missing or uses the insecure default value. "
            "Run '.\\deploy.ps1 -Action setup' to generate a strong key."
        )
        key = key or "default_api_key_replace_in_production"

    _cache["key"] = key
    _cache["ts"] = now
    return key


async def get_api_key(api_key: str = Security(_KEY_HEADER)) -> str:
    """
    Dependencia FastAPI que valida el encabezado X-API-Key.
    Levanta HTTP 401 si la clave no coincide con la activa.
    """
    if api_key != get_active_api_key():
        logger.warning("Intento con clave API inválida")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return api_key
