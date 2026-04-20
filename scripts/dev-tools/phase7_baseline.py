from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class EndpointProbe:
    name: str
    path: str
    allowed_statuses: tuple[int, ...]
    auth_mode: str = "none"


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def load_env_value(env_file: Path | None, key: str) -> str | None:
    if env_file is None or not env_file.exists():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def percentile(values: list[float], target_percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if len(values) == 1:
        return values[0]

    ordered_values = sorted(values)
    rank = (len(ordered_values) - 1) * target_percentile
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return ordered_values[lower_index]

    lower_value = ordered_values[lower_index]
    upper_value = ordered_values[upper_index]
    return lower_value + (upper_value - lower_value) * (rank - lower_index)


def summarize_durations_ms(durations_ms: list[float]) -> dict[str, float]:
    if not durations_ms:
        return {}

    return {
        "minMs": round(min(durations_ms), 2),
        "maxMs": round(max(durations_ms), 2),
        "meanMs": round(statistics.fmean(durations_ms), 2),
        "medianMs": round(statistics.median(durations_ms), 2),
        "p95Ms": round(percentile(durations_ms, 0.95), 2),
    }


def build_default_probes(
    reporting_path: str | None,
    security_path: str | None,
    reporting_auth: str,
    security_auth: str,
) -> list[EndpointProbe]:
    probes = [
        EndpointProbe(name="webUi", path="/", allowed_statuses=(200, 301, 302, 307, 308)),
        EndpointProbe(name="authMe", path="/api/auth/me", allowed_statuses=(401, 403)),
        EndpointProbe(name="monitorHealth", path="/api/monitor/health", allowed_statuses=(200,)),
        EndpointProbe(name="dynsecRoles", path="/api/dynsec/roles", allowed_statuses=(200,), auth_mode="api-key"),
    ]

    if reporting_path:
        probes.append(
            EndpointProbe(
                name="reporting",
                path=reporting_path,
                allowed_statuses=(200,),
                auth_mode=reporting_auth,
            )
        )

    if security_path:
        probes.append(
            EndpointProbe(
                name="security",
                path=security_path,
                allowed_statuses=(200,),
                auth_mode=security_auth,
            )
        )

    return probes


def probe_http_endpoint(
    session: requests.Session,
    base_url: str,
    probe: EndpointProbe,
    samples: int,
    timeout_seconds: float,
    api_key: str | None,
    authenticated_session: requests.Session | None,
) -> dict[str, Any]:
    durations_ms: list[float] = []
    statuses: list[int] = []
    errors: list[str] = []

    headers: dict[str, str] = {}
    request_session = session
    if probe.auth_mode == "api-key":
        if not api_key:
            return {
                "name": probe.name,
                "path": probe.path,
                "status": "skipped",
                "reason": "API key required but not provided",
            }
        headers["X-API-Key"] = api_key
    elif probe.auth_mode == "session":
        if authenticated_session is None:
            return {
                "name": probe.name,
                "path": probe.path,
                "status": "skipped",
                "reason": "Authenticated session required but not provided",
            }
        request_session = authenticated_session

    for _ in range(samples):
        started_at = time.perf_counter()
        try:
            response = request_session.get(
                f"{base_url}{probe.path}",
                headers=headers,
                timeout=timeout_seconds,
                allow_redirects=False,
            )
            durations_ms.append((time.perf_counter() - started_at) * 1000.0)
            statuses.append(response.status_code)
            if response.status_code not in probe.allowed_statuses:
                errors.append(f"unexpected status {response.status_code}")
        except requests.RequestException as exc:
            durations_ms.append((time.perf_counter() - started_at) * 1000.0)
            errors.append(str(exc))

    success_count = sum(1 for status in statuses if status in probe.allowed_statuses)
    failed_count = max(samples - success_count, 0)
    result_status = "ok" if failed_count == 0 else "degraded"

    return {
        "name": probe.name,
        "path": probe.path,
        "status": result_status,
        "allowedStatuses": list(probe.allowed_statuses),
        "statuses": statuses,
        "samples": samples,
        "successCount": success_count,
        "failedCount": failed_count,
        "latency": summarize_durations_ms(durations_ms),
        "errors": errors[:5],
    }


def probe_tcp_port(host: str, port: int, samples: int, timeout_seconds: float) -> dict[str, Any]:
    durations_ms: list[float] = []
    errors: list[str] = []

    for _ in range(samples):
        started_at = time.perf_counter()
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(timeout_seconds)
        try:
            connection.connect((host, port))
            durations_ms.append((time.perf_counter() - started_at) * 1000.0)
        except OSError as exc:
            durations_ms.append((time.perf_counter() - started_at) * 1000.0)
            errors.append(str(exc))
        finally:
            connection.close()

    failed_count = len(errors)
    return {
        "name": "mqttTcpConnect",
        "target": f"{host}:{port}",
        "status": "ok" if failed_count == 0 else "degraded",
        "samples": samples,
        "successCount": samples - failed_count,
        "failedCount": failed_count,
        "latency": summarize_durations_ms(durations_ms),
        "errors": errors[:5],
    }


def load_api_key(explicit_api_key: str | None, env_file: Path | None) -> str | None:
    if explicit_api_key:
        return explicit_api_key
    return load_env_value(env_file, "API_KEY")


def load_login_credentials(
    explicit_email: str | None,
    explicit_password: str | None,
    env_file: Path | None,
) -> tuple[str | None, str | None]:
    email = explicit_email or load_env_value(env_file, "ADMIN_INITIAL_EMAIL")
    password = explicit_password or load_env_value(env_file, "ADMIN_INITIAL_PASSWORD")
    return email, password


def build_authenticated_session(base_url: str, email: str, password: str, timeout_seconds: float) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return session


def run_phase7_baseline(args: argparse.Namespace) -> dict[str, Any]:
    base_url = normalize_base_url(args.base_url)
    env_file = Path(args.env_file) if args.env_file else None
    api_key = load_api_key(args.api_key, env_file)
    login_email, login_password = load_login_credentials(args.login_email, args.login_password, env_file)
    probes = build_default_probes(
        args.reporting_path,
        args.security_path,
        args.reporting_auth,
        args.security_auth,
    )

    session = requests.Session()
    authenticated_session = None
    if any(probe.auth_mode == "session" for probe in probes):
        if login_email and login_password:
            authenticated_session = build_authenticated_session(
                base_url=base_url,
                email=login_email,
                password=login_password,
                timeout_seconds=args.timeout_seconds,
            )
    endpoint_results = [
        probe_http_endpoint(
            session=session,
            base_url=base_url,
            probe=probe,
            samples=args.samples,
            timeout_seconds=args.timeout_seconds,
            api_key=api_key,
            authenticated_session=authenticated_session,
        )
        for probe in probes
    ]
    mqtt_result = probe_tcp_port(
        host=args.mqtt_host,
        port=args.mqtt_port,
        samples=args.samples,
        timeout_seconds=args.timeout_seconds,
    )

    degraded_checks = [
        result["name"]
        for result in [*endpoint_results, mqtt_result]
        if result.get("status") == "degraded"
    ]

    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base_url,
        "samples": args.samples,
        "timeoutSeconds": args.timeout_seconds,
        "runtimeLabel": args.runtime_label,
        "endpoints": endpoint_results,
        "mqtt": mqtt_result,
        "overallStatus": "ok" if not degraded_checks else "degraded",
        "degradedChecks": degraded_checks,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Captura baseline inicial de Fase 7 para HTTP y MQTT.")
    parser.add_argument("--base-url", default="http://localhost:22000")
    parser.add_argument("--runtime-label", default="kind")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=21900)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--env-file", default=".env.dev")
    parser.add_argument("--api-key")
    parser.add_argument("--reporting-path")
    parser.add_argument("--reporting-auth", choices=["none", "api-key", "session"], default="api-key")
    parser.add_argument("--security-path")
    parser.add_argument("--security-auth", choices=["none", "api-key", "session"], default="api-key")
    parser.add_argument("--login-email")
    parser.add_argument("--login-password")
    parser.add_argument("--output")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    report = run_phase7_baseline(args)

    payload = json.dumps(report, ensure_ascii=True, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["overallStatus"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())