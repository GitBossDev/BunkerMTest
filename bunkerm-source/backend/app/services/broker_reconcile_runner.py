"""Runner CLI mínimo para ejecutar reconciliaciones broker-facing fuera del proceso HTTP."""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict, List

from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.orm import BrokerDesiredState
from services import broker_desired_state_service as desired_state_svc

SUPPORTED_SCOPES = (
    desired_state_svc.MOSQUITTO_CONFIG_SCOPE,
    desired_state_svc.MOSQUITTO_PASSWD_SCOPE,
    desired_state_svc.DYNSEC_CONFIG_SCOPE,
    desired_state_svc.TLS_CERT_STORE_SCOPE,
    desired_state_svc.BROKER_RELOAD_SCOPE,
    desired_state_svc.DEFAULT_ACL_SCOPE,
)


def _is_supported_scope(scope: str) -> bool:
    return scope in SUPPORTED_SCOPES or scope.startswith(
        (
            desired_state_svc.CLIENT_SCOPE_PREFIX,
            desired_state_svc.ROLE_SCOPE_PREFIX,
            desired_state_svc.GROUP_SCOPE_PREFIX,
        )
    )


def _serialize_state(state: Any) -> Dict[str, Any]:
    return {
        "scope": state.scope,
        "version": state.version,
        "status": state.reconcile_status,
        "driftDetected": state.drift_detected,
        "lastError": state.last_error,
    }


async def reconcile_scope(session, scope: str) -> Dict[str, Any]:
    if not _is_supported_scope(scope):
        raise ValueError(f"Unsupported scope: {scope}")

    if scope == desired_state_svc.MOSQUITTO_CONFIG_SCOPE:
        state = await desired_state_svc.reconcile_mosquitto_config(session)
    elif scope == desired_state_svc.MOSQUITTO_PASSWD_SCOPE:
        state = await desired_state_svc.reconcile_mosquitto_passwd(session)
    elif scope == desired_state_svc.DYNSEC_CONFIG_SCOPE:
        state = await desired_state_svc.reconcile_dynsec_config(session)
    elif scope == desired_state_svc.TLS_CERT_STORE_SCOPE:
        state = await desired_state_svc.reconcile_tls_cert_store(session)
    elif scope == desired_state_svc.BROKER_RELOAD_SCOPE:
        state = await desired_state_svc.reconcile_broker_reload_signal(session)
    elif scope == desired_state_svc.DEFAULT_ACL_SCOPE:
        state = await desired_state_svc.reconcile_default_acl(session)
    elif scope.startswith(desired_state_svc.CLIENT_SCOPE_PREFIX):
        username = scope.removeprefix(desired_state_svc.CLIENT_SCOPE_PREFIX)
        state = await desired_state_svc.reconcile_client(session, username)
    elif scope.startswith(desired_state_svc.ROLE_SCOPE_PREFIX):
        role_name = scope.removeprefix(desired_state_svc.ROLE_SCOPE_PREFIX)
        state = await desired_state_svc.reconcile_role(session, role_name)
    else:
        group_name = scope.removeprefix(desired_state_svc.GROUP_SCOPE_PREFIX)
        state = await desired_state_svc.reconcile_group(session, group_name)

    return _serialize_state(state)


async def list_reconcileable_scopes(session) -> List[str]:
    result = await session.execute(
        select(BrokerDesiredState.scope)
        .where(BrokerDesiredState.reconcile_status.in_(("pending", "drift", "error")))
        .order_by(BrokerDesiredState.desired_updated_at.asc(), BrokerDesiredState.scope.asc())
    )
    scopes = [scope for scope in result.scalars().all() if _is_supported_scope(scope)]
    return list(dict.fromkeys(scopes))


async def reconcile_requested_scopes(scopes: List[str]) -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        expanded_scopes = await list_reconcileable_scopes(session) if scopes == ["all"] else scopes
        results: List[Dict[str, Any]] = []
        for scope in expanded_scopes:
            results.append(await reconcile_scope(session, scope))
        return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run broker control-plane reconciliation by scope")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        required=True,
        help="Control-plane scope to reconcile. Repeatable. Use 'all' to reconcile every pending/drift/error scope.",
    )
    return parser


async def _async_main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    results = await reconcile_requested_scopes(args.scopes)
    print(json.dumps(results, indent=2))
    return 1 if any(result["status"] == "error" for result in results) else 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())