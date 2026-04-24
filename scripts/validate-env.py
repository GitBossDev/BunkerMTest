#!/usr/bin/env python3
"""
Validates that all required environment variables declared in docker-compose.dev.yml
are present in .env.dev before containers are started.

"Required" means: the variable is referenced as ${VAR} (no :- fallback) in the compose
environment section. Variables with ${VAR:-default} are optional and may be absent.

Usage:
    python scripts/validate-env.py
    python scripts/validate-env.py --env-file .env.dev --compose docker-compose.dev.yml

Exit codes:
    0 — all required variables are defined
    1 — one or more variables are missing, or a required file is not found
"""

import argparse
import base64
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


# Variables obligatorias en .env.dev — se inyectan en el Secret bhm-env de Kubernetes
# y deben estar presentes antes de ejecutar el bootstrap del cluster kind.
REQUIRED_VARS: list[str] = [
    # PostgreSQL
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    # Database URLs (una por schema)
    "DATABASE_URL",
    "CONTROL_PLANE_DATABASE_URL",
    "HISTORY_DATABASE_URL",
    "REPORTING_DATABASE_URL",
    "IDENTITY_DATABASE_URL",
    # MQTT
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
    # Seguridad
    "API_KEY",
    "JWT_SECRET",
    "AUTH_SECRET",
    # Frontend / autenticacion
    "NEXTAUTH_URL",
    "NEXTAUTH_SECRET",
    # Admin inicial
    "ADMIN_INITIAL_EMAIL",
    "ADMIN_INITIAL_PASSWORD",
]

GENERATOR_SAFE_SECRET_NAMES = {
    "POSTGRES_PASSWORD",
    "MQTT_PASSWORD",
    "JWT_SECRET",
    "AUTH_SECRET",
    "NEXTAUTH_SECRET",
    "ADMIN_INITIAL_PASSWORD",
    "PGADMIN_DEFAULT_PASSWORD",
    "API_KEY",
}

GENERATOR_SAFE_VALUE = re.compile(r"^[A-Za-z0-9._\-+=^~]+$")


def read_text_with_fallbacks(path: Path) -> str:
    """Read text files using UTF-8 first, then legacy Windows encodings."""
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    last_error: UnicodeDecodeError | None = None

    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not read file: {path}")


def parse_env_file(path: Path) -> dict[str, str]:
    """Read .env.dev and return the defined variables as key/value pairs."""
    defined: dict[str, str] = {}
    for raw_line in read_text_with_fallbacks(path).splitlines():
        line = raw_line.strip()
        # Ignorar lineas en blanco y comentarios
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            defined[name] = value
    return defined


def validate_required_values(required: list[str], env_values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for name in required:
        if name not in env_values:
            errors.append(f"Missing required variable: {name}")
            continue
        if env_values[name] == "":
            errors.append(f"Required variable is empty: {name}")
    return errors


def validate_generated_secret_shapes(env_values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for name in GENERATOR_SAFE_SECRET_NAMES:
        value = env_values.get(name)
        if not value:
            continue
        if any(ch in value for ch in "\r\n\t "):
            errors.append(f"{name} contains whitespace/control characters")
            continue
        if not GENERATOR_SAFE_VALUE.fullmatch(value):
            errors.append(
                f"{name} contains characters outside the generator-safe set [A-Za-z0-9._-+=^~]"
            )
    return errors


def validate_database_url_coherence(env_values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    postgres_user = env_values.get("POSTGRES_USER")
    postgres_password = env_values.get("POSTGRES_PASSWORD")
    postgres_db = env_values.get("POSTGRES_DB")

    for name in (
        "DATABASE_URL",
        "CONTROL_PLANE_DATABASE_URL",
        "HISTORY_DATABASE_URL",
        "REPORTING_DATABASE_URL",
        "IDENTITY_DATABASE_URL",
    ):
        raw_url = env_values.get(name)
        if not raw_url:
            continue

        parsed = urlparse(raw_url)
        if parsed.scheme != "postgresql":
            errors.append(f"{name} must use the postgresql:// scheme")
            continue
        if not parsed.username or parsed.password is None or not parsed.hostname or not parsed.path:
            errors.append(f"{name} is missing username, password, host or database name")
            continue

        if raw_url.endswith("@") or parsed.path in {"", "/"}:
            errors.append(f"{name} does not include a database name")

        if parsed.hostname == "postgres":
            if postgres_user and parsed.username != postgres_user:
                errors.append(f"{name} username does not match POSTGRES_USER for the local Compose baseline")
            if postgres_password and parsed.password != postgres_password:
                errors.append(f"{name} password does not match POSTGRES_PASSWORD for the local Compose baseline")
            if postgres_db and parsed.path.lstrip("/") != postgres_db:
                errors.append(f"{name} database does not match POSTGRES_DB for the local Compose baseline")

    return errors


def validate_broker_resource_limits(env_values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    cpu_raw = (env_values.get("BROKER_CPU_LIMIT_CORES") or "").strip()
    if cpu_raw:
        try:
            cpu_value = float(cpu_raw)
            if cpu_value <= 0:
                errors.append("BROKER_CPU_LIMIT_CORES must be greater than 0")
        except ValueError:
            errors.append("BROKER_CPU_LIMIT_CORES must be a numeric value such as 0.5, 1 or 2")

    memory_raw = (env_values.get("BROKER_MEMORY_LIMIT") or "").strip().lower()
    if memory_raw and not re.fullmatch(r"\d+(?:\.\d+)?(?:[kmgtp]i?b?|b)", memory_raw):
        errors.append("BROKER_MEMORY_LIMIT must include a unit, for example 512m, 1g or 1536m")

    return errors


def validate_mosquitto_seed_coherence(repo_root: Path, env_values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    mqtt_username = env_values.get("MQTT_USERNAME")
    mqtt_password = env_values.get("MQTT_PASSWORD")
    if not mqtt_username or not mqtt_password:
        return errors, warnings

    seed_path = repo_root / "bunkerm-source" / "backend" / "mosquitto" / "dynsec" / "dynamic-security.json"
    if not seed_path.exists():
        return errors, warnings

    try:
        seed = json.loads(read_text_with_fallbacks(seed_path))
        client = next(
            (item for item in seed.get("clients", []) if item.get("username") == mqtt_username),
            None,
        )
        if client is None:
            warnings.append(
                f"Mosquitto seed JSON does not contain MQTT_USERNAME={mqtt_username}; entrypoint will create/sync it at startup"
            )
            return warnings

        salt_b64 = client.get("salt")
        stored_hash = client.get("password")
        iterations = int(client.get("iterations") or 101)
        if not salt_b64 or not stored_hash:
            warnings.append("Mosquitto seed JSON is missing salt/password for the admin client; entrypoint will repair it at startup")
            return warnings

        derived_hash = base64.b64encode(
            hashlib.pbkdf2_hmac(
                "sha512",
                mqtt_password.encode("utf-8"),
                base64.b64decode(salt_b64),
                iterations,
            )
        ).decode()

        if not hmac.compare_digest(derived_hash, stored_hash):
            warnings.append(
                "Mosquitto seed JSON does not match MQTT_PASSWORD from .env.dev; the entrypoint will synchronize credentials on container start"
            )
    except Exception as exc:
        errors.append(f"Mosquitto seed JSON is invalid and will break a clean broker bootstrap: {exc}")

    return errors, warnings



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate required environment variables before deploying to Kubernetes (kind)"
    )
    parser.add_argument(
        "--env-file",
        default=".env.dev",
        help="Path to the .env file (default: .env.dev)",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    repo_root = env_path.parent

    if not env_path.exists():
        print(f"[ERROR] {env_path} not found.")
        print("        Run: .\\deploy.ps1 -Action setup")
        return 1

    env_values = parse_env_file(env_path)
    errors = []
    errors.extend(validate_required_values(REQUIRED_VARS, env_values))
    errors.extend(validate_generated_secret_shapes(env_values))
    errors.extend(validate_database_url_coherence(env_values))
    errors.extend(validate_broker_resource_limits(env_values))
    seed_errors, warnings = validate_mosquitto_seed_coherence(repo_root, env_values)
    errors.extend(seed_errors)

    if errors:
        print(f"[ERROR] Environment validation failed for {env_path}:\n")
        for issue in errors:
            print(f"  - {issue}")
        print()
        print("Run '.\\deploy.ps1 -Action setup' to regenerate secrets,")
        print("or fix the invalid values manually in .env.dev")
        return 1

    if warnings:
        print(f"[WARNING] Non-blocking coherence findings for {env_path}:\n")
        for issue in warnings:
            print(f"  - {issue}")
        print()

    print(f"[OK] All {len(REQUIRED_VARS)} required environment variables are defined and coherent in {env_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERROR] Unexpected failure while validating environment: {exc}")
        sys.exit(1)
