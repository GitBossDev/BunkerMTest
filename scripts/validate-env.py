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
import re
import sys
from pathlib import Path


# Nombres de variables que se inyectan directamente por Compose (no vienen de .env.dev)
# y por lo tanto no se deben reportar como faltantes.
COMPOSE_INTERNAL = {
    "MQTT_BROKER",      # hardcoded como nombre de servicio
    "MQTT_PORT",        # hardcoded como numero de puerto
    "MOSQUITTO_IP",     # hardcoded como nombre de servicio
    "MOSQUITTO_PORT",   # hardcoded como numero de puerto
}


def parse_env_file(path: Path) -> set[str]:
    """Read .env.dev and return the set of variable names that are defined."""
    defined: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # Ignorar lineas en blanco y comentarios
        if not line or line.startswith("#"):
            continue
        name = line.split("=", 1)[0].strip()
        if name:
            defined.add(name)
    return defined


def parse_required_vars(compose_path: Path) -> list[str]:
    """
    Scan docker-compose.dev.yml for variables referenced as ${VAR} (no :- fallback).
    Returns a deduplicated list preserving first-occurrence order.
    """
    text = compose_path.read_text(encoding="utf-8")

    # ${VAR} — variable requerida, sin valor por defecto
    required_pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
    # ${VAR:-...} — variable con fallback; se extrae su nombre para excluirlo
    optional_pattern = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):-[^}]*\}")

    optional_vars: set[str] = {m.group(1) for m in optional_pattern.finditer(text)}

    seen: set[str] = set()
    required: list[str] = []
    for match in required_pattern.finditer(text):
        var = match.group(1)
        if var in seen or var in optional_vars or var in COMPOSE_INTERNAL:
            continue
        seen.add(var)
        required.append(var)

    return required


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate required environment variables before deploying"
    )
    parser.add_argument(
        "--env-file",
        default=".env.dev",
        help="Path to the .env file (default: .env.dev)",
    )
    parser.add_argument(
        "--compose",
        default="docker-compose.dev.yml",
        help="Path to the compose file (default: docker-compose.dev.yml)",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    compose_path = Path(args.compose)

    # Verificar que los archivos requeridos existen
    if not env_path.exists():
        print(f"[ERROR] {env_path} not found.")
        print("        Run: .\\deploy.ps1 -Action setup")
        return 1

    if not compose_path.exists():
        print(f"[ERROR] {compose_path} not found.")
        return 1

    defined = parse_env_file(env_path)
    required = parse_required_vars(compose_path)
    missing = [v for v in required if v not in defined]

    if missing:
        print(f"[ERROR] {len(missing)} required variable(s) missing from {env_path}:\n")
        for var in missing:
            print(f"  - {var}")
        print()
        print("Run '.\\deploy.ps1 -Action setup' to regenerate secrets,")
        print("or add the missing variables manually to .env.dev")
        return 1

    print(f"[OK] All {len(required)} required environment variables are defined in {env_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERROR] Unexpected failure while validating environment: {exc}")
        sys.exit(1)
