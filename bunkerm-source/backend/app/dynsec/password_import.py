# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/dynsec/password_import.py
import logging
import os
import re
import random
import string
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Security, status
from fastapi.security.api_key import APIKeyHeader
from datetime import datetime
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from services import broker_observability_client
from services import broker_desired_state_service as desired_state_svc
from services import dynsec_service as dynsec_svc

# Router setup
router = APIRouter(tags=["password_import"])

# Configure logging
logger = logging.getLogger(__name__)

# Environment variables
API_KEY = os.getenv("API_KEY")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    from core.auth import get_active_api_key
    if api_key_header != get_active_api_key():
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key"
        )
    return api_key_header

def validate_mosquitto_passwd_file(file_path: str) -> tuple[bool, str, list]:
    """
    Validates if a file has the correct mosquitto_passwd format.
    Returns (success, message, users)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return validate_mosquitto_passwd_file_from_content(f.read())
    except Exception as e:
        logger.error(f"Error validating mosquitto_passwd file: {str(e)}")
        return False, f"Error reading file: {str(e)}", []


def validate_mosquitto_passwd_file_from_content(content: str) -> tuple[bool, str, list]:
    users = []
    lines = content.splitlines()

    if not any(line.strip() for line in lines):
        return False, "File is empty", []

    valid_pattern = re.compile(r'^[^:]+:\$\d+\$[^:]+$')

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        if not valid_pattern.match(line):
            return False, f"Invalid format at line {i+1}: {line}", []

        username = line.split(':')[0]
        users.append(username)

    return True, f"Valid mosquitto_passwd file with {len(users)} users", users

def generate_random_salt(length=16):
    """Generate a random salt for dynamic security users"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def _control_plane_metadata(state) -> dict:
    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "driftDetected": state.drift_detected,
    }

def _ensure_reconcile_success(state, detail_prefix: str) -> None:
    if state.reconcile_status == "error":
        detail = state.last_error or "Unknown reconciliation error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{detail_prefix}: {detail}",
        )


def build_dynsec_config_with_passwd_users(usernames: List[str]) -> tuple[dict, int]:
    dynsec_data = desired_state_svc.get_observed_dynsec_config()
    dynsec_data.setdefault("clients", [])
    current_clients = dynsec_data.get("clients", [])
    current_usernames = {client.get("username") for client in current_clients}
    added_count = 0

    for username in usernames:
        if username in current_usernames:
            continue
        current_clients.append(
            {
                "username": username,
                "roles": [],
                "salt": generate_random_salt(),
                "iterations": 101,
            }
        )
        current_usernames.add(username)
        added_count += 1

    dynsec_data["clients"] = current_clients
    return dynsec_data, added_count

@router.post("/import-password-file")
async def import_password_file(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a mosquitto_passwd file and update dynamic security
    """
    logger.info(f"Password file import requested: {file.filename}")

    try:
        raw_content = await file.read()
        try:
            passwd_content = raw_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password file must be valid UTF-8: {exc}",
            ) from exc

        normalized_content = desired_state_svc._normalize_mosquitto_passwd_content(passwd_content)
        is_valid, message, users = validate_mosquitto_passwd_file_from_content(normalized_content)

        if not is_valid:
            logger.warning(f"Invalid mosquitto_passwd file: {message}")
            return {
                "success": False, 
                "message": message,
                "results": {
                    "total": 0,
                    "imported": 0,
                    "skipped": 0,
                    "failed": 0,
                    "details": []
                }
            }

        passwd_state = await desired_state_svc.set_mosquitto_passwd_desired_from_content(db, normalized_content)
        passwd_state = await desired_state_svc.reconcile_or_wait(
            passwd_state,
            desired_state_svc.reconcile_mosquitto_passwd,
            db,
        )
        _ensure_reconcile_success(passwd_state, "Mosquitto passwd reconciliation failed")

        desired_dynsec, dynsec_count = build_dynsec_config_with_passwd_users(users)
        dynsec_state = await desired_state_svc.set_dynsec_config_desired(db, desired_dynsec)
        dynsec_state = await desired_state_svc.reconcile_or_wait(
            dynsec_state,
            desired_state_svc.reconcile_dynsec_config,
            db,
        )
        _ensure_reconcile_success(dynsec_state, "DynSec password import reconciliation failed")

        # Create results for the frontend
        details = []
        for username in users:
            details.append({
                "username": username,
                "status": "SUCCESS",
                "message": "User imported successfully"
            })
        
        # If dynsec update failed, add a warning message
        result_message = f"Successfully imported password file with {len(users)} users"
        if dynsec_count > 0:
            result_message += f" and added {dynsec_count} users to dynamic security"
            
        logger.info(result_message)
        
        return {
            "success": True, 
            "message": result_message,
            "results": {
                "total": len(users),
                "imported": len(users),
                "skipped": 0,
                "failed": 0,
                "details": details,
                "dynsec_updated": True,
                "dynsec_added": dynsec_count
            },
            "controlPlane": _control_plane_metadata(passwd_state),
            "dynsecControlPlane": _control_plane_metadata(dynsec_state),
        }
    
    except Exception as e:
        logger.error(f"Error importing password file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import password file: {str(e)}"
        )

@router.post("/sync-passwd-to-dynsec")
async def sync_passwd_to_dynsec(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync all users from mosquitto_passwd file to dynamic security
    """
    try:
        logger.info("Syncing mosquitto_passwd users to dynamic security")

        observed_passwd = desired_state_svc.get_observed_mosquitto_passwd()
        if not observed_passwd["exists"]:
            return {
                "success": False,
                "message": "Password file not found"
            }

        passwd_state = await desired_state_svc.set_mosquitto_passwd_desired_from_content(
            db,
            observed_passwd["content"],
        )
        passwd_state = await desired_state_svc.reconcile_or_wait(
            passwd_state,
            desired_state_svc.reconcile_mosquitto_passwd,
            db,
        )
        _ensure_reconcile_success(passwd_state, "Mosquitto passwd sync reconciliation failed")

        users = observed_passwd["users"]
        if not users:
            return {
                "success": True,
                "message": "No users found in password file to sync"
            }

        desired_dynsec, count = build_dynsec_config_with_passwd_users(users)
        dynsec_state = await desired_state_svc.set_dynsec_config_desired(db, desired_dynsec)
        dynsec_state = await desired_state_svc.reconcile_or_wait(
            dynsec_state,
            desired_state_svc.reconcile_dynsec_config,
            db,
        )
        _ensure_reconcile_success(dynsec_state, "DynSec passwd sync reconciliation failed")

        message = "No new users to add to dynamic security"
        if count > 0:
            message = f"Added {count} users to dynamic security"

        return {
            "success": True,
            "message": message,
            "count": count,
            "users": users[:10] + (["..."] if len(users) > 10 else []),
            "controlPlane": _control_plane_metadata(dynsec_state),
            "passwdControlPlane": _control_plane_metadata(passwd_state),
        }
    
    except Exception as e:
        logger.error(f"Error syncing passwd to dynsec: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync password file to dynamic security: {str(e)}"
        )

@router.post("/restart-mosquitto")
async def restart_mosquitto(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Restart the Mosquitto broker service
    """
    try:
        logger.info("Restart Mosquitto broker requested")
        state = await desired_state_svc.set_broker_reload_desired(
            db,
            {"reason": "manual-dynsec-reload", "requestedBy": "dynsec-password-import-router"},
        )
        state = await desired_state_svc.reconcile_or_wait(
            state,
            desired_state_svc.reconcile_broker_reload_signal,
            db,
        )
        _ensure_reconcile_success(state, "Mosquitto reload signal failed")
        logger.info("Reload signal delegated to broker-facing control-plane")
        return {
            "success": True,
            "message": "Mosquitto broker reloading configuration",
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }
    
    except Exception as e:
        logger.error(f"Error restarting Mosquitto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart Mosquitto: {str(e)}"
        )

@router.get("/password-file-status")
async def check_password_file_status(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if the password file exists and get basic stats
    """
    try:
        status_payload = await desired_state_svc.get_mosquitto_passwd_status(db)
        observed = status_payload["observed"] or {
            "exists": False,
            "sizeBytes": 0,
            "userCount": 0,
            "users": [],
            "sha256": None,
        }

        modified_time = None
        try:
            source = broker_observability_client.fetch_broker_passwd_source_status_sync().get("source") or {}
            modified_time = source.get("modifiedAt")
        except Exception:
            modified_time = None

        response = {
            "exists": observed["exists"],
            "size_bytes": observed["sizeBytes"],
            "modified": modified_time,
            "user_count": observed["userCount"],
            "scope": status_payload["scope"],
            "version": status_payload["version"],
            "status": status_payload["status"],
            "desired": status_payload["desired"],
            "applied": status_payload["applied"],
            "observed": status_payload["observed"],
            "driftDetected": status_payload["driftDetected"],
            "lastError": status_payload["lastError"],
            "desiredUpdatedAt": status_payload["desiredUpdatedAt"],
            "reconciledAt": status_payload["reconciledAt"],
            "appliedAt": status_payload["appliedAt"],
        }
        if not observed["exists"]:
            response["message"] = "Password file does not exist"
        return response
    
    except Exception as e:
        logger.error(f"Error checking password file status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check password file status: {str(e)}"
        )