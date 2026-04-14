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
import shutil
import random
import string
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Security, status
from fastapi.security.api_key import APIKeyHeader
from datetime import datetime
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from services import broker_desired_state_service as desired_state_svc
from services import dynsec_service as dynsec_svc

# Router setup
router = APIRouter(tags=["password_import"])

# Configure logging
logger = logging.getLogger(__name__)

# Environment variables
API_KEY = os.getenv("API_KEY")
UPLOAD_DIR = "/tmp/mosquitto_uploads"

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Create upload directory if it doesn't exist
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    users = []
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            
        if not lines:
            return False, "File is empty", []
            
        valid_pattern = re.compile(r'^[^:]+:\$\d+\$[^:]+$')
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            if not valid_pattern.match(line):
                return False, f"Invalid format at line {i+1}: {line}", []
                
            username = line.split(':')[0]
            users.append(username)
            
        return True, f"Valid mosquitto_passwd file with {len(users)} users", users
    except Exception as e:
        logger.error(f"Error validating mosquitto_passwd file: {str(e)}")
        return False, f"Error reading file: {str(e)}", []

def generate_random_salt(length=16):
    """Generate a random salt for dynamic security users"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def _ensure_reconcile_success(state, detail_prefix: str) -> None:
    if state.reconcile_status == "error":
        detail = state.last_error or "Unknown reconciliation error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{detail_prefix}: {detail}",
        )


def build_dynsec_config_with_passwd_users(usernames: List[str]) -> tuple[dict, int]:
    dynsec_data = dynsec_svc.read_dynsec()
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
    
    # Create a unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{file.filename}")
    
    try:
        # Save uploaded file to temporary location
        with open(temp_file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Validate the file
        is_valid, message, users = validate_mosquitto_passwd_file(temp_file_path)
        
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
        
        # Backup existing file if it exists
        if os.path.exists(settings.mosquitto_passwd_path):
            backup_path = f"{settings.mosquitto_passwd_path}.bak.{timestamp}"
            shutil.copy2(settings.mosquitto_passwd_path, backup_path)
            logger.info(f"Created backup of existing password file at {backup_path}")
        
        # Import the file to the destination
        shutil.copy2(temp_file_path, settings.mosquitto_passwd_path)
        
        # Ensure proper permissions - using 644 to match your Dockerfile configuration
        # This allows owner read/write and everyone else read access
        os.chmod(settings.mosquitto_passwd_path, 0o644)
        
        desired_dynsec, dynsec_count = build_dynsec_config_with_passwd_users(users)
        state = await desired_state_svc.set_dynsec_config_desired(db, desired_dynsec)
        state = await desired_state_svc.reconcile_dynsec_config(db)
        _ensure_reconcile_success(state, "DynSec password import reconciliation failed")
        
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
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }
    
    except Exception as e:
        logger.error(f"Error importing password file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import password file: {str(e)}"
        )
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

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
        
        # Check if password file exists
        if not os.path.exists(settings.mosquitto_passwd_path):
            return {
                "success": False,
                "message": "Password file not found"
            }
            
        # Extract users from the password file
        users = []
        with open(settings.mosquitto_passwd_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    username = line.split(':')[0]
                    users.append(username)
                    
        if not users:
            return {
                "success": True,
                "message": "No users found in password file to sync"
            }
                    
        desired_dynsec, count = build_dynsec_config_with_passwd_users(users)
        state = await desired_state_svc.set_dynsec_config_desired(db, desired_dynsec)
        state = await desired_state_svc.reconcile_dynsec_config(db)
        _ensure_reconcile_success(state, "DynSec passwd sync reconciliation failed")

        message = "No new users to add to dynamic security"
        if count > 0:
            message = f"Added {count} users to dynamic security"

        return {
            "success": True,
            "message": message,
            "count": count,
            "users": users[:10] + (["..."] if len(users) > 10 else []),
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }
    
    except Exception as e:
        logger.error(f"Error syncing passwd to dynsec: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync password file to dynamic security: {str(e)}"
        )

@router.post("/restart-mosquitto")
async def restart_mosquitto(
    api_key: str = Security(get_api_key)
):
    """
    Restart the Mosquitto broker service
    """
    try:
        logger.info("Restart Mosquitto broker requested")

        # Signal the standalone mosquitto container to reload via SIGHUP.
        # Writing .reload to the shared volume triggers the entrypoint's signal
        # relay which sends SIGHUP — mosquitto re-reads config + DynSec without
        # dropping any existing client connections.
        with open("/var/lib/mosquitto/.reload", "w") as _f:
            _f.write("")
        logger.info("Reload signal written for mosquitto standalone container")
        return {"success": True, "message": "Mosquitto broker reloading configuration"}
    
    except Exception as e:
        logger.error(f"Error restarting Mosquitto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restart Mosquitto: {str(e)}"
        )

@router.get("/password-file-status")
async def check_password_file_status(api_key: str = Security(get_api_key)):
    """
    Check if the password file exists and get basic stats
    """
    try:
        if not os.path.exists(settings.mosquitto_passwd_path):
            return {
                "exists": False,
                "message": "Password file does not exist"
            }
            
        # Get file stats and user count
        file_stats = os.stat(settings.mosquitto_passwd_path)
        file_size = file_stats.st_size
        modified_time = datetime.fromtimestamp(file_stats.st_mtime).isoformat()
        
        # Count users in the file
        user_count = 0
        try:
            with open(settings.mosquitto_passwd_path, 'r') as f:
                for line in f:
                    if line.strip():
                        user_count += 1
        except Exception as e:
            logger.warning(f"Error reading password file: {str(e)}")
                
        return {
            "exists": True,
            "size_bytes": file_size,
            "modified": modified_time,
            "user_count": user_count
        }
    
    except Exception as e:
        logger.error(f"Error checking password file status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check password file status: {str(e)}"
        )