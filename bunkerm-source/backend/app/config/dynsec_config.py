# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# backend/app/config/dynsec_config.py
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Security, UploadFile, File, status, Response, Request
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

# Router setup
router = APIRouter(tags=["dynsec_config"])

# Configure logging
logger = logging.getLogger(__name__)

# Environment variables
_API_KEY_CACHE: dict = {"key": "", "ts": 0.0}

def _get_current_api_key() -> str:
    """Return the active API key, refreshing from file every 5 s."""
    import time as _t
    now = _t.time()
    if _API_KEY_CACHE["key"] and now - _API_KEY_CACHE["ts"] < 5.0:
        return _API_KEY_CACHE["key"]
    key = os.getenv("API_KEY", "")
    if not key or key == "default_api_key_replace_in_production":
        try:
            with open("/nextjs/data/.api_key") as _fh:
                file_key = _fh.read().strip()
                if file_key:
                    key = file_key
        except Exception:
            pass
    if not key:
        key = "default_api_key_replace_in_production"
    _API_KEY_CACHE["key"] = key
    _API_KEY_CACHE["ts"] = now
    return key

DYNSEC_JSON_PATH = os.getenv("DYNSEC_JSON_PATH", "/var/lib/mosquitto/dynamic-security.json")
BACKUP_DIR = os.getenv("DYNSEC_BACKUP_DIR", "/tmp/dynsec_backups")
MOSQUITTO_ADMIN_USERNAME = os.getenv("MOSQUITTO_ADMIN_USERNAME", "admin")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Create backup directory if it doesn't exist
os.makedirs(BACKUP_DIR, exist_ok=True)

# Default configuration that must be preserved
DEFAULT_CONFIG = {
    "defaultACLAccess": {
        "publishClientSend": True,
        "publishClientReceive": True,
        "subscribe": True,
        "unsubscribe": True
    },
    "clients": [{
        "username": "admin",
        "textname": "Dynsec admin user",
        "roles": [{
            "rolename": "admin"
        }],
        "password": "Q/H+scYSXErJ8YgAnd8TGNpIbJmNVQelnNwGpWir/MuSWS1KvhRCB894bdvHiBahVpLH03lZkZtJB0inO7HJ+Q==",
        "salt": "YWRtbjIwMjV4S205",
        "iterations": 101
    }],
    "groups": [],
    "roles": [{
        "rolename": "admin",
        "acls": [{
            "acltype": "publishClientSend",
            "topic": "#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "publishClientSend",
            "topic": "$CONTROL/dynamic-security/#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "publishClientReceive",
            "topic": "$CONTROL/dynamic-security/#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "publishClientReceive",
            "topic": "$SYS/#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "publishClientReceive",
            "topic": "#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "subscribePattern",
            "topic": "#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "subscribePattern",
            "topic": "$CONTROL/dynamic-security/#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "subscribePattern",
            "topic": "$SYS/#",
            "priority": 0,
            "allow": True
        }, {
            "acltype": "unsubscribePattern",
            "topic": "#",
            "priority": 0,
            "allow": True
        }]
    }]
}

VALID_ROLE_ACL_TYPES = {
    "publishClientSend",
    "publishClientReceive",
    "subscribeLiteral",
    "subscribePattern",
    "unsubscribeLiteral",
    "unsubscribePattern",
}


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have leading/trailing whitespace")
    return value


def _require_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _validate_client_refs(entries: Any, field_name: str, known_names: set[str], ref_key: str) -> None:
    if not isinstance(entries, list):
        raise ValueError(f"{field_name} must be a list")
    seen_names: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{field_name}[{index}] must be an object")
        ref_name = _require_non_empty_string(entry.get(ref_key), f"{field_name}[{index}].{ref_key}")
        if ref_name not in known_names:
            raise ValueError(f"{field_name}[{index}].{ref_key} references an undefined entity: {ref_name}")
        if ref_name in seen_names:
            raise ValueError(f"{field_name} contains duplicate reference: {ref_name}")
        seen_names.add(ref_name)

        priority = entry.get("priority", 0 if ref_key == "username" else 1)
        _require_non_negative_int(priority, f"{field_name}[{index}].priority")


def _validate_role_acls(role_name: str, acls: Any) -> None:
    if not isinstance(acls, list):
        raise ValueError(f"roles[{role_name}].acls must be a list")
    seen_acl_keys: set[tuple[str, str]] = set()
    for index, acl in enumerate(acls):
        if not isinstance(acl, dict):
            raise ValueError(f"roles[{role_name}].acls[{index}] must be an object")
        acl_type = _require_non_empty_string(acl.get("acltype"), f"roles[{role_name}].acls[{index}].acltype")
        if acl_type not in VALID_ROLE_ACL_TYPES:
            raise ValueError(
                f"roles[{role_name}].acls[{index}].acltype must be one of: {', '.join(sorted(VALID_ROLE_ACL_TYPES))}"
            )
        topic = _require_non_empty_string(acl.get("topic"), f"roles[{role_name}].acls[{index}].topic")
        if "\x00" in topic:
            raise ValueError(f"roles[{role_name}].acls[{index}].topic must not contain NUL characters")
        if not isinstance(acl.get("allow"), bool):
            raise ValueError(f"roles[{role_name}].acls[{index}].allow must be boolean")
        priority = acl.get("priority", 0)
        _require_non_negative_int(priority, f"roles[{role_name}].acls[{index}].priority")
        acl_key = (acl_type, topic)
        if acl_key in seen_acl_keys:
            raise ValueError(f"roles[{role_name}].acls contains duplicate acl entry: {acl_type} {topic}")
        seen_acl_keys.add(acl_key)


def _validate_clients_groups_roles(data: Dict[str, Any]) -> None:
    role_names: list[str] = []
    for index, role in enumerate(data["roles"]):
        if not isinstance(role, dict):
            raise ValueError(f"roles[{index}] must be an object")
        role_name = _require_non_empty_string(role.get("rolename"), f"roles[{index}].rolename")
        if role_name in role_names:
            raise ValueError(f"roles contains duplicate rolename: {role_name}")
        role_names.append(role_name)
        _validate_role_acls(role_name, role.get("acls", []))

    group_names: list[str] = []
    for index, group in enumerate(data["groups"]):
        if not isinstance(group, dict):
            raise ValueError(f"groups[{index}] must be an object")
        group_name = _require_non_empty_string(group.get("groupname"), f"groups[{index}].groupname")
        if group_name in group_names:
            raise ValueError(f"groups contains duplicate groupname: {group_name}")
        group_names.append(group_name)

    client_names: list[str] = []
    for index, client in enumerate(data["clients"]):
        if not isinstance(client, dict):
            raise ValueError(f"clients[{index}] must be an object")
        username = _require_non_empty_string(client.get("username"), f"clients[{index}].username")
        if username in client_names:
            raise ValueError(f"clients contains duplicate username: {username}")
        client_names.append(username)

        if username != MOSQUITTO_ADMIN_USERNAME:
            has_password = "password" in client
            has_salt = "salt" in client
            has_iterations = "iterations" in client
            if has_password or has_salt or has_iterations:
                if not (has_password and has_salt and has_iterations):
                    raise ValueError(
                        f"clients[{index}] must define password, salt and iterations together when using credential fields"
                    )
                _require_non_empty_string(client.get("password"), f"clients[{index}].password")
                _require_non_empty_string(client.get("salt"), f"clients[{index}].salt")
                _require_positive_int(client.get("iterations"), f"clients[{index}].iterations")

    known_role_names = set(role_names) | {"admin"}
    known_group_names = set(group_names)
    known_client_names = set(client_names)

    for index, client in enumerate(data["clients"]):
        _validate_client_refs(client.get("roles", []), f"clients[{index}].roles", known_role_names, "rolename")
        _validate_client_refs(client.get("groups", []), f"clients[{index}].groups", known_group_names, "groupname")

    for index, group in enumerate(data["groups"]):
        _validate_client_refs(group.get("roles", []), f"groups[{index}].roles", known_role_names, "rolename")
        _validate_client_refs(group.get("clients", []), f"groups[{index}].clients", known_client_names, "username")


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != _get_current_api_key():
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key"
        )
    return api_key_header


def read_dynsec_json() -> Dict[str, Any]:
    """
    Read the dynamic security JSON file
    """
    try:
        with open(DYNSEC_JSON_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading dynamic security JSON: {str(e)}")
        return {}


def write_dynsec_json(data: Dict[str, Any]) -> bool:
    """
    Write to the dynamic security JSON file using an atomic temp-file rename to
    prevent corruption when writing large configs (25K+ clients).
    """
    try:
        import tempfile
        dir_path = os.path.dirname(DYNSEC_JSON_PATH)
        # Write to a temp file in the same directory so rename is atomic on POSIX.
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".dynsec-tmp-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=4)
            os.chmod(tmp_path, 0o644)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        os.replace(tmp_path, DYNSEC_JSON_PATH)
        os.chmod(DYNSEC_JSON_PATH, 0o644)
        return True
    except Exception as e:
        logger.error(f"Error writing dynamic security JSON: {str(e)}")
        return False

def validate_dynsec_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the dynamic security JSON structure
    """
    required_keys = ["defaultACLAccess", "clients", "groups", "roles"]
    
    # Check if all required keys exist
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key: {key}")
    
    # Ensure "defaultACLAccess" has required fields
    required_acl_fields = ["publishClientSend", "publishClientReceive", "subscribe", "unsubscribe"]
    for field in required_acl_fields:
        if field not in data["defaultACLAccess"]:
            raise ValueError(f"Missing required field in defaultACLAccess: {field}")
        if not isinstance(data["defaultACLAccess"][field], bool):
            raise ValueError(f"defaultACLAccess.{field} must be boolean")
    
    # Validate that "clients", "groups", and "roles" are lists
    if not isinstance(data["clients"], list):
        raise ValueError("'clients' must be a list")
    if not isinstance(data["groups"], list):
        raise ValueError("'groups' must be a list")
    if not isinstance(data["roles"], list):
        raise ValueError("'roles' must be a list")
    
    _validate_clients_groups_roles(data)

    # For files exported by our system, we don't require admin user and role to be present
    # They will be added back during the merge process
    
    return data

def merge_dynsec_configs(imported_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge imported config with default config to preserve critical components.
    The admin user and admin role are taken from the LIVE dynamic-security.json
    (not from the hardcoded DEFAULT_CONFIG) so that any password rotation done
    by sync_admin_credentials in the entrypoint is preserved.
    """
    import copy
    merged_config = copy.deepcopy(DEFAULT_CONFIG)

    # Preservar la ACL por defecto del archivo importado.
    merged_config["defaultACLAccess"] = copy.deepcopy(
        imported_config.get("defaultACLAccess", DEFAULT_CONFIG["defaultACLAccess"])
    )

    # --- Admin user: prefer the live file so password hash is always current ---
    live_admin_user = None
    try:
        live_data = read_dynsec_json()
        for c in live_data.get("clients", []):
            if c.get("username") == MOSQUITTO_ADMIN_USERNAME:
                live_admin_user = c
                break
    except Exception as _e:
        logger.warning(f"merge_dynsec_configs: could not read live admin user: {_e}")

    admin_user = live_admin_user if live_admin_user else DEFAULT_CONFIG["clients"][0]

    # Non-admin users from the imported config
    non_admin_users = [
        user for user in imported_config.get("clients", [])
        if "username" in user and user["username"] != MOSQUITTO_ADMIN_USERNAME
    ]
    merged_config["clients"] = [admin_user] + non_admin_users

    # --- Admin role: always keep the full admin role from DEFAULT_CONFIG ---
    admin_role = DEFAULT_CONFIG["roles"][0]
    non_admin_roles = [
        role for role in imported_config.get("roles", [])
        if "rolename" in role and role["rolename"] != "admin"
    ]
    merged_config["roles"] = [admin_role] + non_admin_roles

    # Importar grupos desde la configuración importada
    merged_config["groups"] = imported_config.get("groups", [])

    return merged_config


def create_backup() -> str:
    """
    Create a backup of the current dynamic security JSON file
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"dynamic-security.json.bak.{timestamp}")
        
        if os.path.exists(DYNSEC_JSON_PATH):
            shutil.copy2(DYNSEC_JSON_PATH, backup_path)
            logger.info(f"Created backup of dynamic security JSON at {backup_path}")
            return backup_path
        else:
            logger.warning(f"Dynamic security JSON file not found at {DYNSEC_JSON_PATH}")
            return ""
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return ""


@router.get("/dynsec-json")
async def get_dynsec_json(api_key: str = Security(get_api_key)):
    """
    Get the current dynamic security JSON configuration
    """
    try:
        data = read_dynsec_json()
        
        if not data:
            return {
                "success": False,
                "message": "Failed to read dynamic security JSON"
            }
        
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        logger.error(f"Error getting dynamic security JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dynamic security JSON: {str(e)}"
        )


@router.get("/export-dynsec-json")
async def export_dynsec_json(api_key: str = Security(get_api_key)):
    """
    Export the dynamic security JSON file for download, excluding default admin user and role
    """
    try:
        logger.info("Export request received")
        data = read_dynsec_json()
        
        if not data:
            logger.error("Failed to read dynamic security JSON file")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to read dynamic security JSON"
            )
        
        # Create a copy of the data for modification
        export_data = data.copy()
        
        # Remove the default admin user from the exported data
        if "clients" in export_data:
            export_data["clients"] = [
                client for client in export_data["clients"] 
                if "username" not in client or client["username"] != MOSQUITTO_ADMIN_USERNAME
            ]
        
        # Remove the default "admin" role from the exported data
        if "roles" in export_data:
            export_data["roles"] = [
                role for role in export_data["roles"] 
                if "rolename" not in role or role["rolename"] != "admin"
            ]
        
        # Create a JSON response with a filename for download
        content = json.dumps(export_data, indent=4)
        filename = f"dynamic-security-export-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        
        logger.info(f"Preparing export response with filename: {filename}")
        
        # Create response with explicit content type and headers
        response = Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/json",
                "Content-Length": str(len(content))
            }
        )
        
        return response
    except HTTPException as he:
        logger.error(f"HTTP exception during export: {str(he)}")
        raise
    except Exception as e:
        logger.error(f"Error exporting dynamic security JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export dynamic security JSON: {str(e)}"
        )


@router.post("/import-dynsec-json")
async def import_dynsec_json(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key)
):
    """
    Import a dynamic security JSON file
    """
    try:
        # Read the uploaded file
        content = await file.read()
        
        try:
            # Parse the JSON content
            imported_data = json.loads(content)
            logger.info(f"Successfully parsed JSON from uploaded file: {file.filename}")
            # Auto-unwrap if exported via the old getDynSecJson endpoint
            # which wraps the config in {"success": true, "data": {...}}
            if "data" in imported_data and "defaultACLAccess" not in imported_data:
                logger.info("Detected wrapped export format — unwrapping 'data' key")
                imported_data = imported_data["data"]
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON format in uploaded file: {file.filename}")
            return {
                "success": False,
                "message": "The uploaded file is not valid JSON"
            }
        
        # Validate the imported JSON structure
        try:
            imported_data = validate_dynsec_json(imported_data)
            logger.info("JSON validation successful")
        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return {
                "success": False,
                "message": f"Invalid dynamic security JSON format: {str(e)}"
            }
        
        # Create a backup of the current configuration
        backup_path = create_backup()
        logger.info(f"Created backup at: {backup_path}")
        
        # Merge imported config with default config to preserve critical components
        merged_config = merge_dynsec_configs(imported_data)
        logger.info("Successfully merged configuration")
        
        # Write the merged configuration
        if write_dynsec_json(merged_config):
            user_count = len(merged_config["clients"]) - 1  # Subtract admin user
            group_count = len(merged_config["groups"])
            role_count = len(merged_config["roles"]) - 1    # Subtract admin role

            # El plugin DynSec de Mosquitto solo relee su JSON en el arranque;
            # SIGHUP (via .reload) NO actualiza el estado en memoria de DynSec.
            # Por eso escribimos .dynsec-reload: el signal relay enviara SIGKILL
            # al proceso mosquitto (sin que guarde su estado antiguo en disco) y
            # el contenedor se reinicia automaticamente gracias a restart:unless-stopped.
            # Asi mosquitto arranca leyendo el JSON recien importado.
            try:
                with open("/var/lib/mosquitto/.dynsec-reload", "w") as _f:
                    _f.write("")
            except Exception as _e:
                logger.warning(f"Could not write dynsec reload signal: {_e}")

            logger.info(f"Successfully imported configuration with {user_count} users, {group_count} groups, {role_count} roles")
            return {
                "success": True,
                "message": f"Successfully imported dynamic security configuration",
                "backup_path": backup_path,
                "stats": {
                    "users": user_count,
                    "groups": group_count,
                    "roles": role_count
                },
                "need_restart": True
            }
        else:
            logger.error("Failed to write dynamic security configuration")
            return {
                "success": False,
                "message": "Failed to write dynamic security configuration"
            }
            
    except Exception as e:
        logger.error(f"Error importing dynamic security JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import dynamic security JSON: {str(e)}"
        )

@router.post("/import-acl")
async def import_acl(request: Request, api_key: str = Security(get_api_key)):
    """
    Import ACL configuration from a JSON body. Validates, merges with defaults,
    writes to disk, and restarts Mosquitto so changes take effect immediately.
    """
    try:
        try:
            imported_data = await request.json()
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Request body is not valid JSON")

        try:
            imported_data = validate_dynsec_json(imported_data)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Invalid ACL format: {str(e)}")

        backup_path = create_backup()
        merged_config = merge_dynsec_configs(imported_data)

        # Write file FIRST, then kill Mosquitto with SIGKILL.
        # Order matters: SIGKILL causes immediate termination with no cleanup
        # callbacks, so Mosquitto cannot flush its in-memory state back to
        # disk and overwrite what we just wrote.
        # (SIGTERM would trigger a graceful shutdown that saves the old state.)
        if not write_dynsec_json(merged_config):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to write ACL configuration")

        # El plugin DynSec de Mosquitto solo relee su JSON en el arranque;
        # SIGHUP (via .reload) NO actualiza el estado en memoria de DynSec.
        # Por eso escribimos .dynsec-reload: el signal relay enviara SIGKILL
        # al proceso mosquitto (sin que guarde su estado antiguo en disco) y
        # el contenedor se reinicia automaticamente gracias a restart:unless-stopped.
        # Asi mosquitto arranca leyendo el JSON recien importado.
        try:
            with open("/var/lib/mosquitto/.dynsec-reload", "w") as _f:
                _f.write("")
        except Exception as _e:
            logger.warning(f"Could not write dynsec reload signal: {_e}")

        user_count = len(merged_config["clients"]) - 1
        group_count = len(merged_config["groups"])
        role_count = len(merged_config["roles"]) - 1
        logger.info(f"ACL imported: {user_count} clients, {group_count} groups, {role_count} roles")

        return {
            "success": True,
            "message": "ACL configuration imported. Broker is reloading.",
            "backup_path": backup_path,
            "stats": {"clients": user_count, "groups": group_count, "roles": role_count},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in import_acl: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Import failed: {str(e)}")


@router.post("/reset-dynsec-json")
async def reset_dynsec_json(api_key: str = Security(get_api_key)):
    """
    Reset dynamic security JSON to default configuration
    """
    try:
        # Create a backup of the current configuration
        backup_path = create_backup()
        
        # Write the default configuration
        if write_dynsec_json(DEFAULT_CONFIG):
            return {
                "success": True,
                "message": "Successfully reset dynamic security configuration to default",
                "backup_path": backup_path,
                "need_restart": True
            }
        else:
            return {
                "success": False,
                "message": "Failed to write default dynamic security configuration"
            }
            
    except Exception as e:
        logger.error(f"Error resetting dynamic security JSON: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset dynamic security JSON: {str(e)}"
        )