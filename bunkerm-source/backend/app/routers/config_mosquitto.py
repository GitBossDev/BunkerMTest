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

from fastapi import APIRouter, File, HTTPException, Security, UploadFile, status

from core.auth import get_api_key
from core.config import settings

# Importar lógica de negocio del módulo original (se mantiene intacto)
from config.mosquitto_config import (
    DEFAULT_CONFIG,
    _generate_tls_listener_block,
    _signal_mosquitto_reload,
    generate_mosquitto_conf,
    parse_mosquitto_conf,
    validate_listeners,
)
from models.schemas import MosquittoConfig, TLSListenerConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config-mosquitto"])

# Rutas derivadas de la configuración centralizada
_MOSQUITTO_CONF_PATH: str = settings.mosquitto_conf_path
_CERTS_DIR: str = settings.mosquitto_certs_dir
_BACKUP_DIR: str = settings.mosquitto_conf_backup_dir
_BROKER_LOG_PATH: str = settings.broker_log_path
_BROKER_LOG_MAX_LINES: int = 1000

# Extensiones de certificado permitidas
_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}

os.makedirs(_BACKUP_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Configuración Mosquitto
# ---------------------------------------------------------------------------

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
):
    """Valida, hace backup y escribe la nueva configuración de Mosquitto."""
    try:
        listeners_list = [
            {
                "port": lst.port,
                "bind_address": lst.bind_address or "",
                "per_listener_settings": lst.per_listener_settings,
                "max_connections": lst.max_connections,
                "protocol": lst.protocol,
            }
            for lst in config.listeners
        ]

        # Validar puertos duplicados
        current = parse_mosquitto_conf()
        is_valid, err_msg = validate_listeners(current.get("listeners", []), listeners_list)
        if not is_valid:
            logger.error("Listener validation error: %s", err_msg)
            return {"success": False, "message": err_msg}

        # Backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(_BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")
        if os.path.exists(_MOSQUITTO_CONF_PATH):
            shutil.copy2(_MOSQUITTO_CONF_PATH, backup_path)
            logger.info("Backup creado en %s", backup_path)

        # Generar contenido
        new_content = generate_mosquitto_conf(
            config.config,
            listeners_list,
            max_inflight_messages=config.max_inflight_messages,
            max_queued_messages=config.max_queued_messages,
        )

        # Agregar bloque TLS si está habilitado
        if config.tls and config.tls.enabled:
            new_content += _generate_tls_listener_block(config.tls)

        with open(_MOSQUITTO_CONF_PATH, "w") as fh:
            fh.write(new_content)
        os.chmod(_MOSQUITTO_CONF_PATH, 0o644)

        _signal_mosquitto_reload()
        logger.info("Configuración Mosquitto guardada correctamente")
        return {
            "success": True,
            "message": "Mosquitto configuration saved successfully",
            "need_restart": True,
        }

    except Exception as exc:
        logger.error("Error saving Mosquitto configuration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Mosquitto configuration: {exc}",
        )


@router.post("/reset-mosquitto-config")
async def reset_mosquitto_config(api_key: str = Security(get_api_key)):
    """Restaura la configuración de Mosquitto al estado por defecto."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(_BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")
        if os.path.exists(_MOSQUITTO_CONF_PATH):
            shutil.copy2(_MOSQUITTO_CONF_PATH, backup_path)

        with open(_MOSQUITTO_CONF_PATH, "w") as fh:
            fh.write(DEFAULT_CONFIG)
        os.chmod(_MOSQUITTO_CONF_PATH, 0o644)

        _signal_mosquitto_reload()
        logger.info("Configuración Mosquitto reseteada a valores por defecto")
        return {
            "success": True,
            "message": "Mosquitto configuration reset to default",
            "need_restart": True,
        }

    except Exception as exc:
        logger.error("Error resetting Mosquitto configuration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset Mosquitto configuration: {exc}",
        )


@router.post("/restart-mosquitto")
async def restart_mosquitto(api_key: str = Security(get_api_key)):
    """Señaliza al contenedor Mosquitto para recargar configuración vía SIGHUP."""
    try:
        _signal_mosquitto_reload()
        logger.info("Reload signal enviado — Mosquitto recargará config sin cortar conexiones")
        return {"success": True, "message": "Broker reloading config. Connections are not dropped."}
    except Exception as exc:
        logger.error("Failed to signal Mosquitto reload: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to signal Mosquitto reload: {exc}")


@router.post("/remove-mosquitto-listener")
async def remove_mosquitto_listener(
    listener_data: dict,
    api_key: str = Security(get_api_key),
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

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(_BACKUP_DIR, f"mosquitto.conf.bak.{timestamp}")
        if os.path.exists(_MOSQUITTO_CONF_PATH):
            shutil.copy2(_MOSQUITTO_CONF_PATH, backup_path)

        new_content = generate_mosquitto_conf(config_data["config"], listeners_list)
        with open(_MOSQUITTO_CONF_PATH, "w") as fh:
            fh.write(new_content)
        os.chmod(_MOSQUITTO_CONF_PATH, 0o644)

        _signal_mosquitto_reload()
        return {
            "success": True,
            "message": f"Listener on port {port} removed from Mosquitto configuration",
            "need_restart": True,
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
        os.makedirs(_CERTS_DIR, exist_ok=True)
        files = [
            f for f in os.listdir(_CERTS_DIR)
            if os.path.isfile(os.path.join(_CERTS_DIR, f))
            and os.path.splitext(f)[1].lower() in _ALLOWED_CERT_EXTENSIONS
        ]
        return {"success": True, "certs": files, "certs_dir": _CERTS_DIR}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/tls-certs/upload")
async def upload_tls_cert(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
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
        os.makedirs(_CERTS_DIR, exist_ok=True)
        dest = os.path.join(_CERTS_DIR, safe_name)

        # Prevenir path traversal
        if not os.path.abspath(dest).startswith(os.path.abspath(_CERTS_DIR)):
            raise HTTPException(status_code=400, detail="Invalid path")

        content = await file.read()
        with open(dest, "wb") as fh:
            fh.write(content)
        os.chmod(dest, 0o640)
        logger.info("TLS cert subido: %s", safe_name)
        return {"success": True, "filename": safe_name, "path": dest}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error uploading cert: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/tls-certs/{filename}")
async def delete_tls_cert(filename: str, api_key: str = Security(get_api_key)):
    """Elimina un archivo de certificado del directorio de certs."""
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    dest = os.path.join(_CERTS_DIR, safe_name)
    if not os.path.abspath(dest).startswith(os.path.abspath(_CERTS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.isfile(dest):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(dest)
    return {"success": True, "filename": safe_name}


# ---------------------------------------------------------------------------
# Logs del broker
# ---------------------------------------------------------------------------

@router.get("/broker")
async def get_broker_logs(api_key: str = Security(get_api_key)):
    """Devuelve las últimas N líneas del log del broker Mosquitto como lista JSON."""
    log_path = _BROKER_LOG_PATH
    if not os.path.isfile(log_path):
        logger.warning("Broker log file not found: %s", log_path)
        return {"logs": [], "path": log_path, "error": "Log file not found"}
    try:
        with open(log_path, "r", errors="replace") as fh:
            lines = fh.readlines()
        tail = [line.rstrip("\n") for line in lines[-_BROKER_LOG_MAX_LINES:]]
        return {"logs": tail, "path": log_path}
    except Exception as exc:
        logger.error("Failed to read broker log: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to read broker log: {exc}")
