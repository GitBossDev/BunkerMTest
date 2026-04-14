# Copyright (c) 2025 BunkerM
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
#
# app/routers/config_dynsec.py
"""
Router de configuración DynSec — consolida los endpoints del antiguo
microservicio config (puerto 1005, sub-router dynsec_config_router).
Delegamos la lógica de lectura/escritura/validación al módulo original.
"""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, Security, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_api_key
from core.database import get_db

# Importar lógica de negocio del módulo original (se mantiene intacto)
from config.dynsec_config import (
    DEFAULT_CONFIG,
    create_backup,
    merge_dynsec_configs,
    read_dynsec_json,
    validate_dynsec_json,
)
from services import broker_desired_state_service as desired_state_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config-dynsec"])


def _ensure_reconcile_success(state, detail_prefix: str) -> None:
    if state.reconcile_status == "error":
        detail = state.last_error or "Unknown reconciliation error"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{detail_prefix}: {detail}",
        )


# ---------------------------------------------------------------------------
# Endpoints de gestión del JSON DynSec
# ---------------------------------------------------------------------------

@router.get("/dynsec-json/status")
async def get_dynsec_json_status(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await desired_state_svc.get_dynsec_config_status(db)
    except Exception as exc:
        logger.error("Error getting DynSec control-plane status: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get DynSec control-plane status: {exc}",
        )

@router.get("/dynsec-json")
async def get_dynsec_json(api_key: str = Security(get_api_key)):
    """Devuelve la configuración DynSec completa en JSON."""
    try:
        data = read_dynsec_json()
        if not data:
            return {"success": False, "message": "Failed to read dynamic security JSON"}
        return {"success": True, "data": data}
    except Exception as exc:
        logger.error("Error getting dynamic security JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dynamic security JSON: {exc}",
        )


@router.get("/export-dynsec-json")
async def export_dynsec_json(api_key: str = Security(get_api_key)):
    """
    Exporta el JSON DynSec para descarga, omitiendo el usuario/rol admin por defecto.
    """
    import json
    from datetime import datetime

    try:
        data = read_dynsec_json()
        if not data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to read dynamic security JSON",
            )

        export_data = data.copy()

        # Excluir usuario admin del export
        if "clients" in export_data:
            export_data["clients"] = [
                c for c in export_data["clients"]
                if c.get("username") != "admin"
            ]
        # Excluir rol admin del export
        if "roles" in export_data:
            export_data["roles"] = [
                r for r in export_data["roles"]
                if r.get("rolename") != "admin"
            ]

        content = json.dumps(export_data, indent=4)
        filename = f"dynamic-security-export-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/json",
                "Content-Length": str(len(content)),
            },
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error exporting dynamic security JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export dynamic security JSON: {exc}",
        )


@router.post("/import-dynsec-json")
async def import_dynsec_json(
    file: UploadFile = File(...),
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Importa un archivo JSON DynSec, valida y fusiona con la configuración actual."""
    import json

    try:
        content = await file.read()
        try:
            imported_data = json.loads(content)
            # Desempaquetar formato legado {"success": true, "data": {...}}
            if "data" in imported_data and "defaultACLAccess" not in imported_data:
                logger.info("Detectado formato exportación envuelto — desempaquetando 'data'")
                imported_data = imported_data["data"]
        except json.JSONDecodeError:
            return {"success": False, "message": "The uploaded file is not valid JSON"}

        try:
            imported_data = validate_dynsec_json(imported_data)
        except ValueError as exc:
            return {"success": False, "message": f"Invalid dynamic security JSON format: {exc}"}

        backup_path = create_backup()
        merged_config = merge_dynsec_configs(imported_data)

        state = await desired_state_svc.set_dynsec_config_desired(db, merged_config)
        state = await desired_state_svc.reconcile_dynsec_config(db)
        _ensure_reconcile_success(state, "DynSec import reconciliation failed")

        user_count = len(merged_config["clients"]) - 1
        group_count = len(merged_config["groups"])
        role_count = len(merged_config["roles"]) - 1
        return {
            "success": True,
            "message": "Successfully imported dynamic security configuration",
            "backup_path": backup_path,
            "stats": {"users": user_count, "groups": group_count, "roles": role_count},
            "need_restart": True,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }

    except Exception as exc:
        logger.error("Error importing dynamic security JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import dynamic security JSON: {exc}",
        )


@router.post("/import-acl")
async def import_acl(
    request: Request,
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Importa configuración ACL desde un cuerpo JSON.
    Valida, fusiona con defaults, escribe a disco y señaliza reinicio de Mosquitto.
    """
    try:
        try:
            imported_data = await request.json()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body is not valid JSON",
            )

        try:
            imported_data = validate_dynsec_json(imported_data)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid ACL format: {exc}",
            )

        backup_path = create_backup()
        merged_config = merge_dynsec_configs(imported_data)

        state = await desired_state_svc.set_dynsec_config_desired(db, merged_config)
        state = await desired_state_svc.reconcile_dynsec_config(db)
        _ensure_reconcile_success(state, "DynSec ACL import reconciliation failed")

        user_count = len(merged_config["clients"]) - 1
        group_count = len(merged_config["groups"])
        role_count = len(merged_config["roles"]) - 1
        logger.info("ACL importado: %d clientes, %d grupos, %d roles", user_count, group_count, role_count)

        return {
            "success": True,
            "message": "ACL configuration imported. Broker is reloading.",
            "backup_path": backup_path,
            "stats": {"clients": user_count, "groups": group_count, "roles": role_count},
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
        logger.error("Error in import_acl: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {exc}",
        )


@router.post("/reset-dynsec-json")
async def reset_dynsec_json(
    api_key: str = Security(get_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Resetea la configuración DynSec al estado por defecto."""
    try:
        backup_path = create_backup()
        state = await desired_state_svc.set_dynsec_config_desired(db, DEFAULT_CONFIG)
        state = await desired_state_svc.reconcile_dynsec_config(db)
        _ensure_reconcile_success(state, "DynSec reset reconciliation failed")
        return {
            "success": True,
            "message": "Successfully reset dynamic security configuration to default",
            "backup_path": backup_path,
            "need_restart": True,
            "controlPlane": {
                "scope": state.scope,
                "version": state.version,
                "status": state.reconcile_status,
                "driftDetected": state.drift_detected,
            },
        }

    except Exception as exc:
        logger.error("Error resetting dynamic security JSON: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset dynamic security JSON: {exc}",
        )
