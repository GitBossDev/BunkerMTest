#!/usr/bin/env python3
"""
Script to generate secure secrets for .env.dev file
Usage: python scripts/generate-secrets.py
"""

import secrets
import uuid
import string
import hashlib
import base64
import json
from pathlib import Path
from datetime import datetime

# Caracteres seguros para docker-compose/.env y para URLs embebidas
# (evita $, #, @, :, comillas, backslash y espacios).
SAFE_ENV_PUNCTUATION = "._-+=^~"

ENV_FILE = Path(__file__).parent.parent / '.env.dev'


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key:
            values[key] = value
    return values

def generate_secure_password(length=32):
    """Generate a secure random password safe for compose/.env interpolation."""
    alphabet = string.ascii_letters + string.digits + SAFE_ENV_PUNCTUATION
    # Ensure password has at least one of each type
    password = (
        secrets.choice(string.ascii_lowercase) +
        secrets.choice(string.ascii_uppercase) +
        secrets.choice(string.digits) +
        secrets.choice(SAFE_ENV_PUNCTUATION)
    )
    password += ''.join(secrets.choice(alphabet) for _ in range(length - 4))
    # Shuffle the password
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    return ''.join(password_list)

def generate_uuid():
    """Generate a random UUID"""
    return str(uuid.uuid4())


def existing_or_new(existing: dict[str, str], key: str, generator):
    value = existing.get(key)
    if value:
        return value
    return generator()


def existing_or_default(existing: dict[str, str], key: str, default: str) -> str:
    if key in existing:
        return existing[key]
    return default

def generate_secrets():
    """Generate all required secrets and print .env.dev file"""
    existing = parse_env_file(ENV_FILE)

    postgres_user = existing_or_default(existing, 'POSTGRES_USER', 'bhm')
    postgres_password = existing_or_new(existing, 'POSTGRES_PASSWORD', lambda: generate_secure_password(24))
    postgres_db = existing_or_default(existing, 'POSTGRES_DB', 'bhm_db')
    postgres_port = existing_or_default(existing, 'POSTGRES_PORT', '5432')

    mqtt_broker = existing_or_default(existing, 'MQTT_BROKER', 'mosquitto')
    mqtt_port = existing_or_default(existing, 'MQTT_PORT', '1900')
    mqtt_ws_port = existing_or_default(existing, 'MQTT_WS_PORT', '9001')
    mqtt_username = existing_or_default(existing, 'MQTT_USERNAME', 'admin')
    mqtt_password = existing_or_new(existing, 'MQTT_PASSWORD', lambda: generate_secure_password(20))
    broker_cpu_limit = existing_or_default(existing, 'BROKER_CPU_LIMIT_CORES', '2')
    broker_memory_limit = existing_or_default(existing, 'BROKER_MEMORY_LIMIT', '4g')

    api_key = existing_or_new(existing, 'API_KEY', generate_uuid)
    jwt_secret = existing_or_new(existing, 'JWT_SECRET', lambda: generate_secure_password(48))
    auth_secret = existing_or_new(existing, 'AUTH_SECRET', lambda: generate_secure_password(48))
    nextauth_secret = existing_or_new(existing, 'NEXTAUTH_SECRET', lambda: generate_secure_password(32))
    pgadmin_password = existing_or_new(existing, 'PGADMIN_DEFAULT_PASSWORD', lambda: generate_secure_password(16))
    admin_ui_password = existing_or_new(existing, 'ADMIN_INITIAL_PASSWORD', lambda: generate_secure_password(16))

    frontend_url = existing_or_default(existing, 'NEXT_PUBLIC_API_URL', 'http://localhost:2000')
    nextauth_url = existing_or_default(existing, 'NEXTAUTH_URL', frontend_url)
    nginx_port = existing_or_default(existing, 'NGINX_PORT', '2000')
    admin_initial_email = existing_or_default(existing, 'ADMIN_INITIAL_EMAIL', 'admin@bhm.local')
    pgadmin_default_email = existing_or_default(existing, 'PGADMIN_DEFAULT_EMAIL', 'admin@bhm.local')
    pgadmin_port = existing_or_default(existing, 'PGADMIN_PORT', '5050')
    backup_retention_days = existing_or_default(existing, 'BACKUP_RETENTION_DAYS', '7')
    backup_schedule = existing_or_default(existing, 'BACKUP_SCHEDULE_CRON', '0 2 * * *')

    smtp_host = existing_or_default(existing, 'SMTP_HOST', 'smtp.gmail.com')
    smtp_port = existing_or_default(existing, 'SMTP_PORT', '587')
    smtp_username = existing_or_default(existing, 'SMTP_USERNAME', 'ramon.revilla.lomas@gmail.com')
    smtp_password = existing_or_default(existing, 'SMTP_PASSWORD', 'puqlsrklypyjkioi')
    smtp_from_email = existing_or_default(existing, 'SMTP_FROM_EMAIL', smtp_username)
    smtp_use_tls = existing_or_default(existing, 'SMTP_USE_TLS', 'true')
    alert_notify_enabled = existing_or_default(existing, 'ALERT_NOTIFY_ENABLED', 'true')
    alert_notify_email_enabled = existing_or_default(existing, 'ALERT_NOTIFY_EMAIL_ENABLED', 'true')
    alert_notify_email_to = existing_or_default(existing, 'ALERT_NOTIFY_EMAIL_TO', smtp_username)
    alert_notify_email_from = existing_or_default(existing, 'ALERT_NOTIFY_EMAIL_FROM', '')
    alert_notify_smtp_host = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_HOST', '')
    alert_notify_smtp_port = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_PORT', '')
    alert_notify_smtp_username = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_USERNAME', '')
    alert_notify_smtp_password = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_PASSWORD', '')
    alert_notify_smtp_starttls = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_STARTTLS', '')
    alert_notify_smtp_ssl = existing_or_default(existing, 'ALERT_NOTIFY_SMTP_SSL', 'false')
    smtp_health_check_on_startup = existing_or_default(existing, 'SMTP_HEALTH_CHECK_ON_STARTUP', 'true')

    twilio_account_sid = existing_or_default(existing, 'TWILIO_ACCOUNT_SID', 'your_twilio_account_sid')
    twilio_auth_token = existing_or_default(existing, 'TWILIO_AUTH_TOKEN', 'your_twilio_auth_token')
    twilio_from_number = existing_or_default(existing, 'TWILIO_FROM_NUMBER', '+1234567890')

    debug_enabled = existing_or_default(existing, 'DEBUG', 'true')
    log_level = existing_or_default(existing, 'LOG_LEVEL', 'DEBUG')
    reload_enabled = existing_or_default(existing, 'RELOAD', 'true')

    db_url = f"postgresql://{postgres_user}:{postgres_password}@postgres:5432/{postgres_db}"
    
    # Create .env.dev content
    env_content = f"""# ==========================================
# Broker Health Manager - Development Environment
# ==========================================
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# NEVER commit this file to version control

# ------------------------------------------
# PostgreSQL Configuration
# ------------------------------------------
POSTGRES_USER={postgres_user}
POSTGRES_PASSWORD={postgres_password}
POSTGRES_DB={postgres_db}
POSTGRES_PORT={postgres_port}

# Database connection string
DATABASE_URL={db_url}
CONTROL_PLANE_DATABASE_URL={db_url}
HISTORY_DATABASE_URL={db_url}
REPORTING_DATABASE_URL={db_url}
IDENTITY_DATABASE_URL={db_url}

# ------------------------------------------
# MQTT Broker (Mosquitto) Configuration
# ------------------------------------------
# Credenciales para clientes MQTT externos e internos.
# No confundir con ADMIN_INITIAL_PASSWORD, que es solo para la UI web.
MQTT_BROKER={mqtt_broker}
MQTT_PORT={mqtt_port}
MQTT_WS_PORT={mqtt_ws_port}
MQTT_USERNAME={mqtt_username}
MQTT_PASSWORD={mqtt_password}
# CPU admite decimales, por ejemplo 0.5.
BROKER_CPU_LIMIT_CORES={broker_cpu_limit}
# Memoria debe incluir unidad, por ejemplo 512m, 1g o 1536m.
BROKER_MEMORY_LIMIT={broker_memory_limit}

# ------------------------------------------
# Broker Health Manager Backend Services
# ------------------------------------------
# API Security
API_KEY={api_key}
JWT_SECRET={jwt_secret}
AUTH_SECRET={auth_secret}

# Paths
DYNSEC_PATH=/var/lib/mosquitto/dynamic-security.json

# Backend API (unified uvicorn process — internal port, not exposed to host)
BHM_API_PORT=9001

# ------------------------------------------
# Frontend Configuration
# ------------------------------------------
NEXT_PUBLIC_API_URL={frontend_url}
NEXTAUTH_URL={nextauth_url}
NEXTAUTH_SECRET={nextauth_secret}

# ------------------------------------------
# Nginx Configuration
# ------------------------------------------
NGINX_PORT={nginx_port}

# ------------------------------------------
# Frontend / UI Admin Credentials
# ------------------------------------------
# Initial admin account for the Broker Health Manager web UI.
# Change this password after first login.
ADMIN_INITIAL_EMAIL={admin_initial_email}
ADMIN_INITIAL_PASSWORD={admin_ui_password}

# ------------------------------------------
# pgAdmin (Optional - for database management)
# ------------------------------------------
PGADMIN_DEFAULT_EMAIL={pgadmin_default_email}
PGADMIN_DEFAULT_PASSWORD={pgadmin_password}
PGADMIN_PORT={pgadmin_port}

# ------------------------------------------
# Backup Configuration
# ------------------------------------------
BACKUP_RETENTION_DAYS={backup_retention_days}
BACKUP_SCHEDULE_CRON={backup_schedule}

# ------------------------------------------
# Email Notifications (SMTP) - UPDATE THESE
# ------------------------------------------
SMTP_HOST={smtp_host}
SMTP_PORT={smtp_port}
SMTP_USERNAME={smtp_username}
SMTP_PASSWORD={smtp_password}
SMTP_FROM_EMAIL={smtp_from_email}
SMTP_USE_TLS={smtp_use_tls}


# Alert notifications wiring (monitor -> email)
ALERT_NOTIFY_ENABLED={alert_notify_enabled}
ALERT_NOTIFY_EMAIL_ENABLED={alert_notify_email_enabled}
ALERT_NOTIFY_EMAIL_TO={alert_notify_email_to}

# Optional explicit overrides. Leave empty to reuse SMTP_* above.
ALERT_NOTIFY_EMAIL_FROM={alert_notify_email_from}
ALERT_NOTIFY_SMTP_HOST={alert_notify_smtp_host}
ALERT_NOTIFY_SMTP_PORT={alert_notify_smtp_port}
ALERT_NOTIFY_SMTP_USERNAME={alert_notify_smtp_username}
ALERT_NOTIFY_SMTP_PASSWORD={alert_notify_smtp_password}
ALERT_NOTIFY_SMTP_STARTTLS={alert_notify_smtp_starttls}
ALERT_NOTIFY_SMTP_SSL={alert_notify_smtp_ssl}

SMTP_HEALTH_CHECK_ON_STARTUP={smtp_health_check_on_startup}

# ------------------------------------------
# SMS Notifications (Twilio) - UPDATE THESE
# ------------------------------------------
TWILIO_ACCOUNT_SID={twilio_account_sid}
TWILIO_AUTH_TOKEN={twilio_auth_token}
TWILIO_FROM_NUMBER={twilio_from_number}

# ------------------------------------------
# Development Settings
# ------------------------------------------
DEBUG={debug_enabled}
LOG_LEVEL={log_level}
RELOAD={reload_enabled}
"""
    
    return env_content

if __name__ == '__main__':
    print("# ==========================================")
    print("# Generating secure secrets for .env.dev")
    print("# ==========================================")
    print()
    
    env_content = generate_secrets()
    
    # Write to .env.dev file
    env_file = ENV_FILE

    with open(env_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(env_content)
    
    print(f"[OK] Secrets generated and saved to: {env_file}")
    print()

    # ── Patch mosquitto seed JSON with the generated MQTT_PASSWORD hash ──────
    # This ensures that on a clean volume, the seed credentials match what the
    # backend services will receive via MQTT_PASSWORD on the first boot.
    seed_json_path = Path(__file__).parent.parent / 'bunkerm-source' / 'backend' / 'mosquitto' / 'dynsec' / 'dynamic-security.json'
    if seed_json_path.exists():
        try:
            mqtt_user = next(
                line.split('=', 1)[1]
                for line in env_content.splitlines()
                if line.startswith('MQTT_USERNAME=')
            )
            mqtt_pass = next(
                line.split('=', 1)[1]
                for line in env_content.splitlines()
                if line.startswith('MQTT_PASSWORD=')
            )
            # Generate a fresh 12-byte salt
            salt_bytes = secrets.token_bytes(12)
            salt_b64 = base64.b64encode(salt_bytes).decode()
            dk = hashlib.pbkdf2_hmac('sha512', mqtt_pass.encode('utf-8'), salt_bytes, 101)
            password_b64 = base64.b64encode(dk).decode()

            with open(seed_json_path, 'r') as fh:
                seed = json.load(fh)

            # Find and update the admin client entry
            for client in seed.get('clients', []):
                if client.get('username') == mqtt_user:
                    client['password'] = password_b64
                    client['salt'] = salt_b64
                    client['iterations'] = 101
                    break

            with open(seed_json_path, 'w') as fh:
                json.dump(seed, fh, indent='\t')

            print(f"[OK] Mosquitto seed JSON updated for user '{mqtt_user}': {seed_json_path}")
        except Exception as exc:
            print(f"[WARNING] Could not update mosquitto seed JSON: {exc}")
    else:
        print(f"[WARNING] Mosquitto seed JSON not found at: {seed_json_path}")
        print("         Run after cloning bunkerm-source/ so the seed matches .env.dev credentials.")
    print()
    print("IMPORTANT:")
    print("1. Update SMTP settings for email notifications")
    print("2. Update Twilio settings for SMS notifications")
    print("3. NEVER commit .env.dev to version control")
    print()
    print("To regenerate Mosquitto admin password hash, run:")
    print(f"  mosquitto_passwd -b -c /tmp/pass admin {env_content.split('MQTT_PASSWORD=')[1].split()[0]}")
