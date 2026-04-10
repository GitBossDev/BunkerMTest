# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/routers/azure_bridge.py
"""
Router de Azure IoT Hub Bridge — consolida el antiguo microservicio azure-bridge (puerto 1004).
"""
import logging
import os
import re
from typing import List

from fastapi import APIRouter, File, HTTPException, Request, Security, UploadFile, status
from pydantic import BaseModel

from core.auth import get_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/azure-bridge", tags=["azure-bridge"])

# Rutas de Mosquitto
_CERT_PATH: str = os.getenv("MOSQUITTO_CERT_PATH", "/etc/mosquitto/certs")
_CONF_PATH: str = os.getenv("MOSQUITTO_CONF_PATH", "/etc/mosquitto/conf.d")


# ---------------------------------------------------------------------------
# Modelos internos
# ---------------------------------------------------------------------------

class BridgeConfig(BaseModel):
    hub_name: str
    device_id: str
    sas_token: str
    topics: List[str]
    api_version: str = "2019-03-31"


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _validate_certificate(content: bytes) -> bool:
    """Verifica que el contenido sea un certificado PEM válido."""
    try:
        text = content.decode("utf-8")
        return "-----BEGIN CERTIFICATE-----" in text and "-----END CERTIFICATE-----" in text
    except Exception:
        return False


def _safe_filename(name: str) -> str:
    """Sanea un nombre de archivo."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(name or "unknown"))


def _save_certificate(content: bytes, filename: str) -> str:
    """Guarda el certificado en el directorio de certs y devuelve la ruta completa."""
    os.makedirs(_CERT_PATH, exist_ok=True)
    filepath = os.path.join(_CERT_PATH, filename)
    with open(filepath, "wb") as fh:
        fh.write(content)
    os.chmod(filepath, 0o644)
    return filepath


def _generate_bridge_config(
    bridge_name: str,
    hub_name: str,
    device_id: str,
    sas_token: str,
    topics: List[str],
    api_version: str,
    ca_path: str,
) -> str:
    """Genera el contenido de configuración Mosquitto para el bridge Azure IoT Hub."""
    config = (
        f"connection {bridge_name}\n"
        f"address {hub_name}.azure-devices.net:8883\n"
        f"remote_username {hub_name}.azure-devices.net/{device_id}/?api-version={api_version}\n"
        f"remote_password {sas_token}\n"
        f"remote_clientid {device_id}\n"
        f"bridge_cafile {ca_path}\n"
        "\n"
        "# Enable clean session\n"
        "cleansession true\n"
        "\n"
        "# Keep alive interval\n"
        "keepalive_interval 60\n"
        "\n"
        "# Start type\n"
        "start_type automatic\n"
        "\n"
        "# Retry interval\n"
        "retry_interval 10\n"
        "\n"
        "# Bridge attempt unsubscribe\n"
        "bridge_attempt_unsubscribe true\n"
        "\n"
    )
    for topic in topics:
        if topic.endswith("/#"):
            base = topic[:-2]
            config += f"topic {base}/# out 1\n"
        else:
            config += f"topic {topic} out 1\n"
    return config


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
async def create_azure_bridge(
    request: Request,
    bridge_config: BridgeConfig,
    ca_file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
):
    """
    Configura un bridge MQTT hacia Azure IoT Hub.
    Recibe la configuración del bridge como JSON en el cuerpo y el
    certificado CA como upload.
    """
    logger.info(
        "Request: %s %s Client: %s",
        request.method,
        request.url,
        request.client.host if request.client else "unknown",
    )
    logger.info("Creando Azure bridge para dispositivo: %s", bridge_config.device_id)

    try:
        # Validar y guardar certificado CA
        content = await ca_file.read()
        if not _validate_certificate(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CA certificate",
            )

        safe_name = _safe_filename(f"azure_{bridge_config.device_id}_ca.pem")
        ca_path = _save_certificate(content, safe_name)
        logger.info("Certificado CA guardado en %s", ca_path)

        # Generar y escribir configuración del bridge
        bridge_name = f"azure_bridge_{bridge_config.device_id}"
        config_content = _generate_bridge_config(
            bridge_name,
            bridge_config.hub_name,
            bridge_config.device_id,
            bridge_config.sas_token,
            bridge_config.topics,
            bridge_config.api_version,
            ca_path,
        )

        os.makedirs(_CONF_PATH, exist_ok=True)
        config_path = os.path.join(_CONF_PATH, f"{bridge_name}.conf")
        with open(config_path, "w") as fh:
            fh.write(config_content)
        logger.info("Configuración bridge guardada en %s", config_path)

        _signal_mosquitto_reload()
        logger.info("Azure bridge configurado correctamente para %s", bridge_config.device_id)
        return {"status": "success", "message": "Azure IoT Hub bridge configured successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error creating Azure bridge: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        )
