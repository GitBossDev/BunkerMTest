#!/usr/bin/env python3
"""
Script to generate secure secrets for .env.dev file
Usage: python scripts/generate-secrets.py
"""

import secrets
import uuid
import string
from pathlib import Path
from datetime import datetime

def generate_secure_password(length=32):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    # Ensure password has at least one of each type
    password = (
        secrets.choice(string.ascii_lowercase) +
        secrets.choice(string.ascii_uppercase) +
        secrets.choice(string.digits) +
        secrets.choice(string.punctuation)
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
MQTT_BROKER=mosquitto
MQTT_PORT=1900
MQTT_WS_PORT=9001
MQTT_USERNAME=admin
MQTT_PASSWORD={mqtt_password}

# ------------------------------------------
# BunkerM Backend Services
# ------------------------------------------
# API Security
API_KEY={api_key}
JWT_SECRET={jwt_secret}
AUTH_SECRET={auth_secret}

# Service tier (community, pro, enterprise, enterprise_plus)
TIER=enterprise

# Paths
DYNSEC_PATH=/var/lib/mosquitto/dynamic-security.json

# Service Ports
DYNSEC_PORT=1000
MONITOR_PORT=1001
CLIENTLOGS_PORT=1002
AWS_BRIDGE_PORT=1003
AZURE_BRIDGE_PORT=1004
CONFIG_PORT=1005
SMART_ANOMALY_PORT=8100

# ------------------------------------------
# New Extended Services (Funcionalidades Propias)
# ------------------------------------------
DASHBOARD_SERVICE_PORT=1006
BACKUP_SERVICE_PORT=1007
LOAD_SIMULATOR_PORT=1008

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
    print("IMPORTANT:")
    print("1. Update SMTP settings for email notifications")
    print("2. Update Twilio settings for SMS notifications")
    print("3. NEVER commit .env.dev to version control")
    print()
    print("To regenerate Mosquitto admin password hash, run:")
    print(f"  mosquitto_passwd -b -c /tmp/pass admin {env_content.split('MQTT_PASSWORD=')[1].split()[0]}")
