from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def load_api_key(explicit_api_key: str | None, env_file: Path | None) -> str | None:
    if explicit_api_key:
        return explicit_api_key
    if env_file is None or not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def summarize(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "minMs": round(min(values), 2),
        "maxMs": round(max(values), 2),
        "meanMs": round(statistics.fmean(values), 2),
        "medianMs": round(statistics.median(values), 2),
    }


def parse_iso_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def status_url(base_url: str, username: str) -> str:
    return f"{base_url}/api/dynsec/clients/{username}/status"


def create_url(base_url: str) -> str:
    return f"{base_url}/api/dynsec/clients"


def role_url(base_url: str, username: str) -> str:
    return f"{base_url}/api/dynsec/clients/{username}/roles"


def fetch_client_status(session: requests.Session, base_url: str, username: str, headers: dict[str, str]) -> dict[str, Any]:
    response = session.get(status_url(base_url, username), headers=headers, timeout=15)
    response.raise_for_status()
    return response.json()


def wait_until_applied(
    session: requests.Session,
    base_url: str,
    username: str,
    role_name: str,
    headers: dict[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None

    while time.monotonic() <= deadline:
        payload = fetch_client_status(session, base_url, username, headers)
        last_payload = payload
        observed_roles = {entry.get("rolename") for entry in payload.get("observed", {}).get("roles", [])}
        if payload.get("status") == "applied" and role_name in observed_roles:
            return payload
        time.sleep(poll_interval_seconds)

    raise TimeoutError(f"Client {username} did not settle as applied before timeout: {json.dumps(last_payload or {}, ensure_ascii=True)}")


def ensure_client(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
    role_name: str,
    role_priority: int,
    headers: dict[str, str],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    create_response = session.post(
        create_url(base_url),
        headers={**headers, "Content-Type": "application/json"},
        json={"username": username, "password": password},
        timeout=20,
    )
    create_response.raise_for_status()

    role_response = session.post(
        role_url(base_url, username),
        headers={**headers, "Content-Type": "application/json"},
        json={"role_name": role_name, "priority": role_priority},
        timeout=20,
    )
    role_response.raise_for_status()

    settled_status = wait_until_applied(
        session=session,
        base_url=base_url,
        username=username,
        role_name=role_name,
        headers=headers,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )

    desired_updated_at = parse_iso_timestamp(settled_status.get("desiredUpdatedAt"))
    applied_at = parse_iso_timestamp(settled_status.get("appliedAt"))
    reconcile_window_ms = None
    if desired_updated_at is not None and applied_at is not None:
        reconcile_window_ms = round((applied_at - desired_updated_at).total_seconds() * 1000.0, 2)

    return {
        "username": username,
        "createMessage": create_response.json().get("message"),
        "roleMessage": role_response.json().get("message"),
        "status": settled_status.get("status"),
        "version": settled_status.get("version"),
        "driftDetected": settled_status.get("driftDetected"),
        "desiredUpdatedAt": settled_status.get("desiredUpdatedAt"),
        "appliedAt": settled_status.get("appliedAt"),
        "reconciledAt": settled_status.get("reconciledAt"),
        "reconcileWindowMs": reconcile_window_ms,
        "endToEndMs": round((time.perf_counter() - started_at) * 1000.0, 2),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provisiona clientes MQTT por API y mide el tiempo de apply broker-facing.")
    parser.add_argument("--base-url", default="http://localhost:22000")
    parser.add_argument("--runtime-label", default="kind")
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--api-key")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--password", default="123456")
    parser.add_argument("--role-name", default="subscribe-and-publish")
    parser.add_argument("--role-priority", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--output")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env_file = Path(args.env_file) if args.env_file else None
    api_key = load_api_key(args.api_key, env_file)
    if not api_key:
        parser.error("API key is required via --api-key or env file")

    session = requests.Session()
    headers = {"X-API-Key": api_key}
    base_url = normalize_base_url(args.base_url)

    client_results: list[dict[str, Any]] = []
    for offset in range(args.count):
        username = str(args.start_index + offset)
        client_results.append(
            ensure_client(
                session=session,
                base_url=base_url,
                username=username,
                password=args.password,
                role_name=args.role_name,
                role_priority=args.role_priority,
                headers=headers,
                timeout_seconds=args.timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        )

    reconcile_windows = [item["reconcileWindowMs"] for item in client_results if item["reconcileWindowMs"] is not None]
    end_to_end_values = [item["endToEndMs"] for item in client_results]

    payload = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "runtimeLabel": args.runtime_label,
        "baseUrl": base_url,
        "count": args.count,
        "startIndex": args.start_index,
        "roleName": args.role_name,
        "clients": client_results,
        "summary": {
            "reconcileWindow": summarize(reconcile_windows),
            "endToEnd": summarize(end_to_end_values),
        },
    }

    serialized = json.dumps(payload, ensure_ascii=True, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")

    print(serialized)
    return 0


if __name__ == "__main__":
    sys.exit(main())