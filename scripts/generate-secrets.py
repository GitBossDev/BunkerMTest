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

def generate_secrets():
    """Generate all required secrets and print .env.dev file"""
    
    # Generate secrets
    postgres_password = generate_secure_password(24)
    mqtt_password = generate_secure_password(20)
    api_key = generate_uuid()
    jwt_secret = generate_secure_password(48)
    auth_secret = generate_secure_password(48)
    nextauth_secret = generate_secure_password(32)
    pgadmin_password = generate_secure_password(16)
    admin_ui_password = generate_secure_password(16)
    
    # Create .env.dev content
    env_content = f"""# ==========================================
# BunkerM Extended - Development Environment
# ==========================================
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# NEVER commit this file to version control

# ------------------------------------------
# PostgreSQL Configuration
# ------------------------------------------
POSTGRES_USER=bunkerm
POSTGRES_PASSWORD={postgres_password}
POSTGRES_DB=bunkerm_db
POSTGRES_PORT=5432

# Database connection string
DATABASE_URL=postgresql://bunkerm:{postgres_password}@postgres:5432/bunkerm_db

# ------------------------------------------
# MQTT Broker (Mosquitto) Configuration
# ------------------------------------------
# Credenciales para clientes MQTT externos e internos.
# No confundir con ADMIN_INITIAL_PASSWORD, que es solo para la UI web.
MQTT_BROKER=mosquitto
MQTT_PORT=1900
MQTT_WS_PORT=9001
MQTT_USERNAME=admin
MQTT_PASSWORD={mqtt_password}
BROKER_CPU_LIMIT_CORES=2
BROKER_MEMORY_LIMIT=4g

# ------------------------------------------
# BunkerM Backend Services
# ------------------------------------------
# API Security
API_KEY={api_key}
JWT_SECRET={jwt_secret}
AUTH_SECRET={auth_secret}

# Paths
DYNSEC_PATH=/var/lib/mosquitto/dynamic-security.json

# Backend API (unified uvicorn process — internal port, not exposed to host)
BUNKERM_API_PORT=9001

# ------------------------------------------
# Frontend Configuration
# ------------------------------------------
NEXT_PUBLIC_API_URL=http://localhost:2000
NEXTAUTH_URL=http://localhost:2000
NEXTAUTH_SECRET={nextauth_secret}

# ------------------------------------------
# Nginx Configuration
# ------------------------------------------
NGINX_PORT=2000

# ------------------------------------------
# Frontend / UI Admin Credentials
# ------------------------------------------
# Initial admin account for the BunkerM web UI.
# Change this password after first login.
ADMIN_INITIAL_EMAIL=admin@brokerpanel.com
ADMIN_INITIAL_PASSWORD={admin_ui_password}

# ------------------------------------------
# pgAdmin (Optional - for database management)
# ------------------------------------------
PGADMIN_DEFAULT_EMAIL=admin@bunkerm.local
PGADMIN_DEFAULT_PASSWORD={pgadmin_password}
PGADMIN_PORT=5050

# ------------------------------------------
# Backup Configuration
# ------------------------------------------
BACKUP_RETENTION_DAYS=7
BACKUP_SCHEDULE_CRON=0 2 * * *

# ------------------------------------------
# Email Notifications (SMTP) - UPDATE THESE
# ------------------------------------------
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM_EMAIL=noreply@bunkerm.local
SMTP_USE_TLS=true

# ------------------------------------------
# SMS Notifications (Twilio) - UPDATE THESE
# ------------------------------------------
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890

# ------------------------------------------
# Development Settings
# ------------------------------------------
DEBUG=true
LOG_LEVEL=DEBUG
RELOAD=true
"""
    
    return env_content

if __name__ == '__main__':
    print("# ==========================================")
    print("# Generating secure secrets for .env.dev")
    print("# ==========================================")
    print()
    
    env_content = generate_secrets()
    
    # Write to .env.dev file
    env_file = Path(__file__).parent.parent / '.env.dev'
    
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    print(f"[OK] Secrets generated and saved to: {env_file}")
    print()

    # ── Patch mosquitto seed JSON with the generated MQTT_PASSWORD hash ──────
    # This ensures that on a clean volume, the seed credentials match what the
    # backend services will receive via MQTT_PASSWORD on the first boot.
    seed_json_path = Path(__file__).parent.parent / 'bunkerm-source' / 'backend' / 'mosquitto' / 'dynsec' / 'dynamic-security.json'
    if seed_json_path.exists():
        try:
            mqtt_user = 'admin'
            # Extract the generated password from the written env_content
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
