"""Cliente HTTP interno para la API broker-owned de observabilidad."""
from __future__ import annotations

from typing import Any, Dict

import httpx

from core.config import settings


class BrokerObservabilityUnavailable(RuntimeError):
    pass


def _build_url(path: str) -> str:
    return f"{settings.broker_observability_url.rstrip('/')}{path}"


async def _get_json(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not settings.broker_observability_enabled:
        raise BrokerObservabilityUnavailable("broker_observability_disabled")

    try:
        async with httpx.AsyncClient(timeout=settings.broker_observability_timeout_seconds) as client:
            response = await client.get(_build_url(path), params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise BrokerObservabilityUnavailable(str(exc)) from exc


def _get_json_sync(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not settings.broker_observability_enabled:
        raise BrokerObservabilityUnavailable("broker_observability_disabled")

    try:
        with httpx.Client(timeout=settings.broker_observability_timeout_seconds) as client:
            response = client.get(_build_url(path), params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise BrokerObservabilityUnavailable(str(exc)) from exc


async def fetch_broker_logs(limit: int = 1000) -> Dict[str, Any]:
    return await _get_json("/internal/broker/logs", params={"limit": limit})


def fetch_broker_logs_sync(limit: int = 1000) -> Dict[str, Any]:
    return _get_json_sync("/internal/broker/logs", params={"limit": limit})


async def fetch_broker_log_source_status() -> Dict[str, Any]:
    return await _get_json("/internal/broker/logs/source-status")


def fetch_broker_log_source_status_sync() -> Dict[str, Any]:
    return _get_json_sync("/internal/broker/logs/source-status")


async def fetch_broker_resource_stats() -> Dict[str, Any]:
    return await _get_json("/internal/broker/resource-stats")


def fetch_broker_resource_stats_sync() -> Dict[str, Any]:
    return _get_json_sync("/internal/broker/resource-stats")


async def fetch_broker_resource_source_status() -> Dict[str, Any]:
    return await _get_json("/internal/broker/resource-stats/source-status")


def fetch_broker_resource_source_status_sync() -> Dict[str, Any]:
    return _get_json_sync("/internal/broker/resource-stats/source-status")