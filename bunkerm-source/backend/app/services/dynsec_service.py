"""
Lógica de negocio para DynSec: lectura/escritura del JSON de configuración
y ejecución de comandos mosquitto_ctrl.
Extraído de dynsec/main.py para separarlos de la capa HTTP.
"""
import json
import logging
import os
import subprocess
import tempfile
import threading
from typing import Any, Dict, List

from core.config import settings

logger = logging.getLogger(__name__)

# Lock compartido para toda escritura sobre el archivo DynSec
_dynsec_lock = threading.Lock()

# Comando base para mosquitto_ctrl (se completa con subcomando y parámetros).
# Las credenciales se pasan SOLO via archivo temporal de configuracion (modo 0o600)
# para que no aparezcan en la salida de `ps aux` (HIGH-4).
# _build_base_command() ya no se usa; se conserva a modo de referencia interna.
def _build_base_command() -> List[str]:
    return [
        "mosquitto_ctrl",
        "-h", os.getenv("MOSQUITTO_IP", settings.mqtt_broker),
        "-p", os.getenv("MOSQUITTO_PORT", str(settings.mqtt_port)),
        "-u", os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username),
        "-P", os.getenv("MOSQUITTO_ADMIN_PASSWORD", settings.mqtt_password),
        "dynsec",
    ]

# ---------------------------------------------------------------------------
# Lectura / escritura del JSON de DynSec
# ---------------------------------------------------------------------------

def read_dynsec() -> Dict[str, Any]:
    """Lee y devuelve el JSON de DynSec. Lanza excepción ante cualquier error."""
    with open(settings.dynsec_path, "r") as fh:
        return json.load(fh)


def write_dynsec(data: Dict[str, Any]) -> None:
    """
    Escritura atómica del JSON de DynSec: escribe en un tmp y luego hace rename.
    Así evitamos corromper el archivo ante caídas durante la escritura.
    """
    dir_path = os.path.dirname(settings.dynsec_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".dynsec-tmp-")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent="\t")
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    os.replace(tmp_path, settings.dynsec_path)


# ---------------------------------------------------------------------------
# Ejecución de comandos mosquitto_ctrl
# ---------------------------------------------------------------------------

def execute_mosquitto_command(subcommand: List[str]) -> Dict[str, Any]:
    """
    Ejecuta un subcomando de mosquitto_ctrl dynsec y devuelve un dict con
    success, output y error_output. No lanza excepciones.

    Las credenciales se escriben en un archivo temporal con permisos 0o600 y se
    pasan a mosquitto_ctrl via -c, evitando que la contraseña aparezca en ps aux
    (que solo muestra argumentos de linea de comandos, no el contenido de archivos).
    El archivo se borra en el bloque finally aunque falle el proceso.
    """
    broker_host = os.getenv("MOSQUITTO_IP", settings.mqtt_broker)
    broker_port  = os.getenv("MOSQUITTO_PORT", str(settings.mqtt_port))
    username     = os.getenv("MOSQUITTO_ADMIN_USERNAME", settings.mqtt_username)
    password     = os.getenv("MOSQUITTO_ADMIN_PASSWORD", settings.mqtt_password)

    # Escribir credenciales en archivo temporal con permisos restrictivos
    config_content = (
        f"host {broker_host}\n"
        f"port {broker_port}\n"
        f"username {username}\n"
        f"password {password}\n"
    )
    fd, tmp_path = tempfile.mkstemp(prefix=".mqctrl-", suffix=".conf")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(config_content)
        os.chmod(tmp_path, 0o600)

        cmd = ["mosquitto_ctrl", "-c", tmp_path, "dynsec"] + subcommand
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            success = result.returncode == 0
            if not success:
                logger.warning("mosquitto_ctrl falló: %s", result.stderr)
            return {
                "success": success,
                "output": result.stdout,
                "error_output": result.stderr,
            }
        except subprocess.TimeoutExpired:
            logger.error("mosquitto_ctrl agotó el tiempo de espera")
            return {"success": False, "output": "", "error_output": "Broker unreachable: command timed out", "timeout": True}
        except Exception as exc:
            logger.error("Error ejecutando mosquitto_ctrl: %s", exc)
            return {"success": False, "output": "", "error_output": str(exc)}
    finally:
        # Eliminar el archivo de credenciales sea cual sea el resultado
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Helpers para operaciones frecuentes sobre el JSON de DynSec
# ---------------------------------------------------------------------------

def find_client(data: Dict[str, Any], username: str) -> Dict[str, Any] | None:
    """Busca un cliente por username en el JSON de DynSec."""
    for client in data.get("clients", []):
        if client.get("username") == username:
            return client
    return None


def find_role(data: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    """Busca un rol por nombre en el JSON de DynSec."""
    for role in data.get("roles", []):
        if role.get("rolename") == name:
            return role
    return None


def find_group(data: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    """Busca un grupo por nombre en el JSON de DynSec."""
    for group in data.get("groups", []):
        if group.get("groupname") == name:
            return group
    return None
