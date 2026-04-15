# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/routers/config_mosquitto.py
"""
Router de configuración Mosquitto — consolida todos los endpoints del antiguo
microservicio config (puerto 1005, sub-router mosquitto_config_router).
Delegamos la lógica de parseo/generación al módulo original para no duplicar código.
"""
import logging
import os
import re
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Security, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_api_key
from core.config import settings
from core.database import get_db

# Importar lógica de negocio del módulo original (se mantiene intacto)
from config.mosquitto_config import (
    DEFAULT_CONFIG,
    _generate_tls_listener_block,
    generate_mosquitto_conf,
    parse_mosquitto_conf,
    validate_listeners,
)
from models.schemas import MosquittoConfig, TLSListenerConfig
from services import broker_observability_client
from services import broker_desired_state_service as desired_state_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config-mosquitto"])

# Rutas derivadas de la configuración centralizada
_MOSQUITTO_CONF_PATH: str = settings.mosquitto_conf_path
_CERTS_DIR: str = settings.mosquitto_certs_dir
_BACKUP_DIR: str = settings.mosquitto_conf_backup_dir
_BROKER_LOG_MAX_LINES: int = 1000

# Extensiones de certificado permitidas
_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}

os.makedirs(_BACKUP_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Configuración Mosquitto
# ---------------------------------------------------------------------------

def _serialize_mosquitto_config(config: MosquittoConfig) -> dict:
    return {
        "config": config.config,
        "listeners": [
            {
                "port": listener.port,
                "bind_address": listener.bind_address or "",
                "per_listener_settings": listener.per_listener_settings,
                "max_connections": listener.max_connections,
                "protocol": listener.protocol,
            }
            for listener in config.listeners
        ],
        "max_inflight_messages": config.max_inflight_messages,
        "max_queued_messages": config.max_queued_messages,
        "tls": config.tls.model_dump() if config.tls else None,
    }


def _ensure_reconcile_success(state, detail_prefix: str) -> None:
    if state.reconcile_status == "error":
        detail = state.last_error or "Unknown reconciliation error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{detail_prefix}: {detail}",
        )


@router.get("/mosquitto-config/status")
async def get_mosquitto_config_status(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Expone estado deseado/aplicado/observado del control-plane para mosquitto.conf."""
    return await desired_state_svc.get_mosquitto_config_status(db)

@router.get("/mosquitto-config")
async def get_mosquitto_config(api_key: str = Security(get_api_key)):
    """Devuelve la configuración actual de Mosquitto junto a info TLS y certs disponibles."""
    try:
        config_data = parse_mosquitto_conf()

        if not config_data["config"]:
            return {"success": False, "message": "Failed to parse Mosquitto configuration"}

        # Detectar listener TLS (tiene cafile o certfile en metadatos _raw)
        listeners = config_data.get("listeners", [])
        tls_info = None
        for lst in listeners:
            raw = lst.get("_raw", {})
            if raw.get("cafile") or raw.get("certfile"):
                tls_info = {
                    "enabled": True,
                    "port": lst["port"],
                    "cafile": raw.get("cafile"),
                    "certfile": raw.get("certfile"),
                    "keyfile": raw.get("keyfile"),
                    "require_certificate": raw.get("require_certificate", "false") == "true",
                    "tls_version": raw.get("tls_version"),
                }
                break

        # Listar archivos de certificado disponibles
        certs: list = []
        try:
            os.makedirs(_CERTS_DIR, exist_ok=True)
            certs = [
                f for f in os.listdir(_CERTS_DIR)
                if os.path.isfile(os.path.join(_CERTS_DIR, f))
            ]
        except Exception:
            pass

        return {
            "success": True,
            "config": config_data["config"],
            "listeners": config_data["listeners"],
            "max_inflight_messages": config_data.get("max_inflight_messages"),
            "max_queued_messages": config_data.get("max_queued_messages"),
            "tls": tls_info,
            "available_certs": certs,
            "certs_dir": _CERTS_DIR,
        }

    except Exception as exc:
        logger.error("Error getting Mosquitto configuration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get Mosquitto configuration: {exc}",
        )


@router.post("/mosquitto-config")
async def save_mosquitto_config(
    config: MosquittoConfig,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Valida, hace backup y escribe la nueva configuración de Mosquitto."""
    try:
        payload = _serialize_mosquitto_config(config)
        listeners_list = payload["listeners"]

        # Validar puertos duplicados
        current = parse_mosquitto_conf()
        is_valid, err_msg = validate_listeners(current.get("listeners", []), listeners_list)
        if not is_valid:
            logger.error("Listener validation error: %s", err_msg)
            return {"success": False, "message": err_msg}

        state = await desired_state_svc.set_mosquitto_config_desired(db, payload)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_mosquitto_config,
            db,
        )
        _ensure_reconcile_success(state, "Mosquitto configuration reconciliation failed")
        logger.info("Configuración Mosquitto guardada correctamente")
        return {
            "success": True,
            "message": "Mosquitto configuration saved successfully",
            "need_restart": True,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }

    except Exception as exc:
        logger.error("Error saving Mosquitto configuration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Mosquitto configuration: {exc}",
        )


@router.post("/reset-mosquitto-config")
async def reset_mosquitto_config(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Restaura la configuración de Mosquitto al estado por defecto."""
    try:
        state = await desired_state_svc.reset_mosquitto_config_desired(db)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_mosquitto_config,
            db,
        )
        _ensure_reconcile_success(state, "Mosquitto configuration reset reconciliation failed")
        logger.info("Configuración Mosquitto reseteada a valores por defecto")
        return {
            "success": True,
            "message": "Mosquitto configuration reset to default",
            "need_restart": True,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }

    except Exception as exc:
        logger.error("Error resetting Mosquitto configuration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset Mosquitto configuration: {exc}",
        )


@router.post("/restart-mosquitto")
async def restart_mosquitto(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Señaliza al contenedor Mosquitto para recargar configuración vía SIGHUP."""
    try:
        state = await desired_state_svc.set_broker_reload_desired(
            db,
            {"reason": "manual-config-reload", "requestedBy": "config-router"},
        )
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_broker_reload_signal,
            db,
        )
        _ensure_reconcile_success(state, "Mosquitto reload signal failed")
        logger.info("Reload signal delegado al control-plane broker-facing")
        return {
            "success": True,
            "message": "Broker reloading config. Connections are not dropped.",
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }
    except Exception as exc:
        logger.error("Failed to signal Mosquitto reload: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to signal Mosquitto reload: {exc}")


@router.post("/remove-mosquitto-listener")
async def remove_mosquitto_listener(
    listener_data: dict,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Elimina un listener específico de la configuración de Mosquitto."""
    try:
        port = listener_data.get("port")
        if not port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Listener port is required",
            )

        config_data = parse_mosquitto_conf()
        listeners_list = config_data["listeners"]
        found = False
        for i, lst in enumerate(listeners_list):
            if lst.get("port") == port:
                listeners_list.pop(i)
                found = True
                break

        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Listener with port {port} not found",
            )

        state = await desired_state_svc.set_mosquitto_config_desired(
            db,
            {
                "config": config_data["config"],
                "listeners": listeners_list,
                "max_inflight_messages": config_data.get("max_inflight_messages"),
                "max_queued_messages": config_data.get("max_queued_messages"),
                "tls": None,
            },
        )
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_mosquitto_config,
            db,
        )
        _ensure_reconcile_success(state, "Mosquitto listener removal reconciliation failed")
        return {
            "success": True,
            "message": f"Listener on port {port} removed from Mosquitto configuration",
            "need_restart": True,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error removing listener: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove listener: {exc}",
        )


# ---------------------------------------------------------------------------
# Certificados TLS
# ---------------------------------------------------------------------------

@router.get("/tls-certs")
async def list_tls_certs(api_key: str = Security(get_api_key)):
    """Lista los archivos de certificado TLS disponibles en el directorio de certs."""
    try:
        observed = desired_state_svc.get_observed_tls_cert_store()
        files = [entry["filename"] for entry in observed.get("certs", [])]
        return {"success": True, "certs": files, "certs_dir": _CERTS_DIR}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/tls-certs/status")
async def get_tls_certs_status(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Expone estado deseado/aplicado/observado del store TLS del broker."""
    return await desired_state_svc.get_tls_cert_store_status(db)


@router.post("/tls-certs/upload")
async def upload_tls_cert(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Sube un archivo PEM/CRT/KEY al directorio de certs."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_CERT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(_ALLOWED_CERT_EXTENSIONS)} files are accepted",
        )

    # Sanear nombre: solo alfanumérico, guion, punto
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(file.filename or "unknown"))
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    try:
        content = await file.read()
        state = await desired_state_svc.upsert_tls_cert_desired(db, safe_name, content)
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_tls_cert_store,
            db,
        )
        _ensure_reconcile_success(state, "TLS cert store reconciliation failed")
        dest = os.path.join(_CERTS_DIR, safe_name)
        logger.info("TLS cert subido: %s", safe_name)
        return {
            "success": True,
            "filename": safe_name,
            "path": dest,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error uploading cert: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/tls-certs/{filename}")
async def delete_tls_cert(
    filename: str,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Elimina un archivo de certificado del directorio de certs."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    if os.path.splitext(safe_name)[1].lower() not in _ALLOWED_CERT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid certificate filename")
    dest = os.path.join(_CERTS_DIR, safe_name)
    if not os.path.abspath(dest).startswith(os.path.abspath(_CERTS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(dest):
        raise HTTPException(status_code=404, detail="File not found")
    state = await desired_state_svc.delete_tls_cert_desired(db, safe_name)
    state = await desired_state_svc.reconcile_or_wait(
        state,
        desired_state_svc.reconcile_tls_cert_store,
        db,
    )
    _ensure_reconcile_success(state, "TLS cert deletion reconciliation failed")
    return {
        "success": True,
        "filename": safe_name,
        "controlPlane": {
            "scope": state.scope,
            "version": state.version,
            "status": state.reconcile_status,
            "driftDetected": state.drift_detected,
        },
    }


# ---------------------------------------------------------------------------
# Logs del broker
# ---------------------------------------------------------------------------

@router.get("/broker")
async def get_broker_logs(api_key: str = Security(get_api_key)):
    """Devuelve las últimas N líneas del log del broker Mosquitto como lista JSON."""
    try:
        return await broker_observability_client.fetch_broker_logs(limit=_BROKER_LOG_MAX_LINES)
    except broker_observability_client.BrokerObservabilityUnavailable as exc:
        logger.error("Failed to read broker log via broker observability service: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Broker observability service unavailable: {exc}",
        )


@router.get("/broker/source-status")
async def get_broker_log_source_status(api_key: str = Security(get_api_key)):
    """Expone el estado operativo de la fuente de logs del broker."""
    try:
        return await broker_observability_client.fetch_broker_log_source_status()
    except broker_observability_client.BrokerObservabilityUnavailable as exc:
        logger.error("Failed to read broker log source status via broker observability service: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Broker observability service unavailable: {exc}",
        )
