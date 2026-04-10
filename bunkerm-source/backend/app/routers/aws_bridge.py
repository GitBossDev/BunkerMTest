# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/routers/aws_bridge.py
"""
Router de AWS IoT Bridge — consolida el antiguo microservicio aws-bridge (puerto 1003).
Mantiene la lógica de validación de certificados y generación de configuración inline.
"""
import json
import logging
import os
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, Security, UploadFile, status
from pydantic import BaseModel
from typing import List

from core.auth import get_api_key
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/aws-bridge", tags=["aws-bridge"])

# Rutas de Mosquitto (idénticas al servicio original)
_CERT_PATH: str = os.getenv("MOSQUITTO_CERT_PATH", "/etc/mosquitto/certs")
_CONF_PATH: str = os.getenv("MOSQUITTO_CONF_PATH", "/etc/mosquitto/conf.d")


# ---------------------------------------------------------------------------
# Modelos internos
# ---------------------------------------------------------------------------

class BridgeConfig(BaseModel):
    aws_endpoint: str
    client_id: str
    topics: List[str]


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _validate_certificate(content: bytes) -> bool:
    """Verifica que el contenido sea un archivo PEM válido (cert o clave)."""
    try:
        text = content.decode("utf-8")
        is_cert = "-----BEGIN CERTIFICATE-----" in text and "-----END CERTIFICATE-----" in text
        is_key = "-----BEGIN PRIVATE KEY-----" in text and "-----END PRIVATE KEY-----" in text
        is_rsa = "-----BEGIN RSA PRIVATE KEY-----" in text and "-----END RSA PRIVATE KEY-----" in text
        return is_cert or is_key or is_rsa
    except Exception:
        return False


def _safe_filename(name: str) -> str:
    """Sanea un nombre de archivo: solo alfanumérico, guion, punto, guion bajo."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(name or "unknown"))


def _save_certificate(content: bytes, filename: str) -> str:
    """Guarda el certificado en el directorio de certs y devuelve la ruta completa."""
    os.makedirs(_CERT_PATH, exist_ok=True)
    filepath = os.path.join(_CERT_PATH, filename)
    with open(filepath, "wb") as fh:
        fh.write(content)
    os.chmod(filepath, 0o600)
    return filepath


def _generate_bridge_config(
    bridge_name: str,
    aws_endpoint: str,
    client_id: str,
    topics: List[str],
    cert_paths: dict,
) -> str:
    """Genera el contenido de configuración Mosquitto para el bridge AWS IoT."""
    lines = [
        f"# AWS IoT Bridge Configuration for {bridge_name}",
        f"connection {bridge_name}",
        f"address {aws_endpoint}:8883",
        "",
        "# Bridge settings",
        f"clientid {client_id}",
        "cleansession true",
        "start_type automatic",
        "",
        "# Security configuration",
        f"bridge_cafile {cert_paths['ca']}",
        f"bridge_certfile {cert_paths['cert']}",
        f"bridge_keyfile {cert_paths['key']}",
        "",
        "# Topic configuration",
    ]
    for topic in topics:
        lines.append(f"topic {topic} both 0")
    lines += ["", "# Additional settings", "try_private true", "notifications true"]
    return "\n".join(lines)


def _signal_mosquitto_reload() -> None:
    """Escribe el archivo trigger para que el relay envíe SIGHUP al broker."""
    try:
        with open("/var/lib/mosquitto/.reload", "w") as fh:
            fh.write("")
        logger.info("Reload signal enviado al contenedor Mosquitto")
    except Exception as exc:
        logger.error("Failed to signal mosquitto reload: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("")
async def create_aws_bridge(
    request: Request,
    bridge_config: str = Form(...),
    cert_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    ca_file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
):
    """
    Configura un bridge MQTT hacia AWS IoT Core.
    Recibe la configuración del bridge como JSON en un campo de formulario y
    los tres archivos de certificado (cert, key, ca) como uploads.
    """
    logger.info(
        "Request: %s %s Client: %s",
        request.method,
        request.url,
        request.client.host if request.client else "unknown",
    )

    try:
        # Parsear configuración del bridge desde el campo form
        try:
            config_data = json.loads(bridge_config)
            bridge_cfg = BridgeConfig(**config_data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bridge configuration: {exc}",
            )

        logger.info("Creando AWS bridge para cliente: %s", bridge_cfg.client_id)

        # Validar y guardar certificados
        cert_paths: dict = {}
        for upload, file_type in [(cert_file, "cert"), (key_file, "key"), (ca_file, "ca")]:
            content = await upload.read()
            if not _validate_certificate(content):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {file_type} certificate",
                )
            safe_name = _safe_filename(f"{bridge_cfg.client_id}_{file_type}.pem")
            filepath = _save_certificate(content, safe_name)
            cert_paths[file_type] = filepath
            logger.info("Cert %s guardado en %s", file_type, filepath)

        # Generar y escribir configuración del bridge
        bridge_name = f"aws_bridge_{bridge_cfg.client_id}"
        config_content = _generate_bridge_config(
            bridge_name,
            bridge_cfg.aws_endpoint,
            bridge_cfg.client_id,
            bridge_cfg.topics,
            cert_paths,
        )

        os.makedirs(_CONF_PATH, exist_ok=True)
        config_path = os.path.join(_CONF_PATH, f"{bridge_name}.conf")
        with open(config_path, "w") as fh:
            fh.write(config_content)
        logger.info("Configuración bridge guardada en %s", config_path)

        _signal_mosquitto_reload()
        logger.info("AWS bridge configurado correctamente para %s", bridge_cfg.client_id)
        return {"status": "success", "message": "AWS IoT bridge configured successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error creating AWS bridge: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        )
