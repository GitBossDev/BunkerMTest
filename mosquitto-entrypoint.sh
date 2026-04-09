#!/bin/sh
# =============================================================================
# BunkerM Extended - Mosquitto Standalone Entrypoint
#
# Responsabilidades:
#   1. Sembrar volumenes compartidos en el primer arranque.
#   2. Actuar como supervisor de mosquitto (PID 1 es este script, no mosquitto).
#      Al correr mosquitto como subproceso se puede enviar SIGKILL sin restricciones
#      del kernel (solo PID 1 esta protegido contra SIGKILL desde dentro).
#   3. Gestionar dos tipos de recarga via ficheros de señal:
#        .reload        → SIGHUP al subproceso mosquitto (recarga mosquitto.conf)
#        .dynsec-reload → SIGKILL al subproceso + restart (DynSec relee el JSON)
#   4. Reenviar SIGTERM/INT de Docker al subproceso mosquitto para shutdown limpio.
# =============================================================================
set -e

# ── 1. Seed mosquitto.conf si el volumen esta vacio ───────────────────────────
if [ ! -f /etc/mosquitto/mosquitto.conf ]; then
    echo "[mosquitto-entrypoint] Sembrando mosquitto.conf al volumen compartido..."
    cp /mosquitto-seeds/mosquitto.conf /etc/mosquitto/mosquitto.conf
    chmod 644 /etc/mosquitto/mosquitto.conf
fi

# ── 2. Crear conf.d si no existe ──────────────────────────────────────────────
mkdir -p /etc/mosquitto/conf.d

# ── 3. Seed dynamic-security.json si el volumen esta vacio ───────────────────
if [ ! -f /var/lib/mosquitto/dynamic-security.json ]; then
    echo "[mosquitto-entrypoint] Sembrando dynamic-security.json al volumen compartido..."
    cp /mosquitto-seeds/dynamic-security.json /var/lib/mosquitto/dynamic-security.json
fi

# ── 3b. Sync admin credentials directly in JSON (before mosquitto starts) ────
# Patches /var/lib/mosquitto/dynamic-security.json in-place so the hash always
# matches MQTT_USERNAME / MQTT_PASSWORD from the environment.  Works in every
# state: fresh volume (just seeded), old 'bunker' volume, or a previous random
# password that is no longer known.  No MQTT connection needed.
sync_admin_credentials() {
    python3 - <<'PYEOF'
import json, hashlib, base64, os, secrets, sys

username = os.environ.get('MQTT_USERNAME', 'admin')
password = os.environ.get('MQTT_PASSWORD', 'Usuario@1')
path     = '/var/lib/mosquitto/dynamic-security.json'

try:
    with open(path) as f:
        data = json.load(f)
except Exception as e:
    print('[sync-creds] ERROR reading {}: {}'.format(path, e))
    sys.exit(0)

clients = data.get('clients', [])

salt_bytes = secrets.token_bytes(12)
salt_b64   = base64.b64encode(salt_bytes).decode()
dk         = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt_bytes, 101)
hash_b64   = base64.b64encode(dk).decode()

def patch_client(c):
    c['username']   = username
    c['password']   = hash_b64
    c['salt']       = salt_b64
    c['iterations'] = 101

legacy_names = {'bunker', 'admin'}
target_idx   = None
legacy_idx   = None

for i, c in enumerate(clients):
    if c.get('username') == username:
        target_idx = i
        break
    if c.get('username') in legacy_names and legacy_idx is None:
        legacy_idx = i

if target_idx is not None:
    patch_client(clients[target_idx])
    print('[sync-creds] Updated password for {}'.format(username))
elif legacy_idx is not None:
    old_name = clients[legacy_idx]['username']
    patch_client(clients[legacy_idx])
    print('[sync-creds] Migrated {} -> {}'.format(old_name, username))
else:
    new_client = {
        'username':   username,
        'textname':   'Dynsec admin user',
        'roles':      [{'rolename': 'admin'}],
        'password':   hash_b64,
        'salt':       salt_b64,
        'iterations': 101,
    }
    clients.append(new_client)
    print('[sync-creds] Created new admin client {}'.format(username))

data['clients'] = clients
with open(path, 'w') as f:
    json.dump(data, f, indent='\t')
print('[sync-creds] Credentials synced for {}'.format(username))
PYEOF
}
sync_admin_credentials || echo "[sync-creds] WARNING: credential sync failed — mosquitto may reject connections"

# ── 4. Ajustar permisos en volumenes compartidos ──────────────────────────────
chown -R mosquitto:mosquitto /var/lib/mosquitto /var/log/mosquitto
chmod -R 755 /var/lib/mosquitto
chmod 644 /etc/mosquitto/mosquitto.conf
mkdir -p /var/log/mosquitto
touch /var/log/mosquitto/mosquitto.log
chown mosquitto:mosquitto /var/log/mosquitto/mosquitto.log

# ── 5. Supervisor: mosquitto como subproceso (PID 1 = este script) ────────────
#
# Al ejecutar mosquitto en background (no con exec), este script es PID 1 y
# mosquitto tiene un PID diferente. Esto permite enviarle SIGKILL directamente
# sin las restricciones del kernel que protegen a PID 1.
#
# Tipos de señal via fichero compartido:
#   .reload        → SIGHUP  a mosquitto: recarga mosquitto.conf sin perder conexiones
#   .dynsec-reload → SIGKILL a mosquitto: lo detiene sin flush del estado DynSec,
#                    preservando el JSON recien importado; el supervisor lo reinicia.
#
MOSQUITTO_PID=""

start_mosquitto() {
    echo "[supervisor] Iniciando mosquitto..."
    # Redirect stdout (log_dest stdout) to the shared log file so clientlogs
    # can tail it. Shell redirect is more reliable than log_dest file after
    # container restarts. Supervisor messages still go to container stdout.
    mosquitto -c /etc/mosquitto/mosquitto.conf >> /var/log/mosquitto/mosquitto.log 2>&1 &
    MOSQUITTO_PID=$!
    echo "[supervisor] Mosquitto iniciado (PID $MOSQUITTO_PID)"
}

# Reenviar SIGTERM/INT al subproceso mosquitto para shutdown limpio
cleanup() {
    echo "[supervisor] Señal de shutdown recibida — deteniendo mosquitto (PID $MOSQUITTO_PID)..."
    kill "$MOSQUITTO_PID" 2>/dev/null
    wait "$MOSQUITTO_PID" 2>/dev/null
    exit 0
}
trap cleanup TERM INT

start_mosquitto

# Bucle principal del supervisor
while true; do
    if [ -f /var/lib/mosquitto/.dynsec-reload ]; then
        rm -f /var/lib/mosquitto/.dynsec-reload
        echo "[supervisor] Recarga DynSec solicitada — SIGKILL a mosquitto (PID $MOSQUITTO_PID)..."
        kill -KILL "$MOSQUITTO_PID" 2>/dev/null
        wait "$MOSQUITTO_PID" 2>/dev/null || true
        sleep 1
        start_mosquitto

    elif [ -f /var/lib/mosquitto/.reload ]; then
        rm -f /var/lib/mosquitto/.reload
        echo "[supervisor] Reload solicitado — SIGHUP a mosquitto (PID $MOSQUITTO_PID)..."
        kill -HUP "$MOSQUITTO_PID" 2>/dev/null || echo "[supervisor] SIGHUP fallido"

    elif ! kill -0 "$MOSQUITTO_PID" 2>/dev/null; then
        # Mosquitto termino inesperadamente — reiniciar
        echo "[supervisor] Mosquitto termino inesperadamente (PID $MOSQUITTO_PID), reiniciando..."
        sleep 1
        start_mosquitto
    fi

    sleep 2
done

