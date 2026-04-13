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
RESOURCE_STATS_PID=""

start_resource_stats_collector() {
    python3 - <<'PYEOF' &
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

stats_path = Path('/var/log/mosquitto/broker-resource-stats.json')
cgroup_root = Path('/sys/fs/cgroup')
host_cpus = os.cpu_count() or 1


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except Exception:
        return ''


def read_int(path: Path):
    text = read_text(path)
    if not text or text == 'max':
        return None
    try:
        return int(text)
    except ValueError:
        return None


def read_cpu_usage_usec() -> int:
    text = read_text(cgroup_root / 'cpu.stat')
    for line in text.splitlines():
        key, _, value = line.partition(' ')
        if key == 'usage_usec':
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def read_cpu_limit_cores():
    raw = read_text(cgroup_root / 'cpu.max')
    if not raw:
        return None
    parts = raw.split()
    if len(parts) != 2 or parts[0] == 'max':
        return None
    try:
        quota = int(parts[0])
        period = int(parts[1])
        if quota <= 0 or period <= 0:
            return None
        return quota / period
    except ValueError:
        return None


def parse_cpu_limit_env():
    raw = (os.environ.get('BROKER_CPU_LIMIT_CORES') or '').strip()
    if not raw:
        return None
    try:
        value = float(raw)
        return value if value > 0 else None
    except ValueError:
        return None


def parse_memory_limit_env():
    raw = (os.environ.get('BROKER_MEMORY_LIMIT') or '').strip().lower()
    if not raw:
        return None

    match = re.fullmatch(r'(\d+(?:\.\d+)?)([kmgtp]?i?b?)?', raw)
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2) or ''
    multipliers = {
        '': 1,
        'b': 1,
        'k': 1024,
        'kb': 1024,
        'ki': 1024,
        'kib': 1024,
        'm': 1024 ** 2,
        'mb': 1024 ** 2,
        'mi': 1024 ** 2,
        'mib': 1024 ** 2,
        'g': 1024 ** 3,
        'gb': 1024 ** 3,
        'gi': 1024 ** 3,
        'gib': 1024 ** 3,
        't': 1024 ** 4,
        'tb': 1024 ** 4,
        'ti': 1024 ** 4,
        'tib': 1024 ** 4,
        'p': 1024 ** 5,
        'pb': 1024 ** 5,
        'pi': 1024 ** 5,
        'pib': 1024 ** 5,
    }
    multiplier = multipliers.get(unit)
    if multiplier is None:
        return None
    return int(number * multiplier)


previous_usage = None
previous_ts = None
configured_cpu_limit_cores = parse_cpu_limit_env()
configured_memory_limit_bytes = parse_memory_limit_env()

while True:
    now = time.time()
    cpu_usage = read_cpu_usage_usec()
    cpu_limit_cores = read_cpu_limit_cores() or configured_cpu_limit_cores
    memory_bytes = read_int(cgroup_root / 'memory.current')
    memory_limit_bytes = read_int(cgroup_root / 'memory.max') or configured_memory_limit_bytes

    cpu_pct = None
    if previous_usage is not None and previous_ts is not None and now > previous_ts:
        usage_delta = max(0, cpu_usage - previous_usage)
        elapsed = now - previous_ts
        baseline_cores = cpu_limit_cores if cpu_limit_cores and cpu_limit_cores > 0 else host_cpus
        if baseline_cores > 0 and elapsed > 0:
            cpu_pct = max(0.0, min(usage_delta / (elapsed * 1_000_000 * baseline_cores) * 100.0, 999.0))

    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'cpu_pct': round(cpu_pct, 2) if cpu_pct is not None else None,
        'cpu_limit_cores': round(cpu_limit_cores, 2) if cpu_limit_cores is not None else None,
        'cpu_limit_pct': 100.0 if cpu_limit_cores is not None else None,
        'memory_bytes': memory_bytes,
        'memory_limit_bytes': memory_limit_bytes,
        'memory_pct': round(memory_bytes / memory_limit_bytes * 100.0, 2)
        if memory_bytes is not None and memory_limit_bytes not in (None, 0)
        else None,
    }

    try:
        tmp_path = stats_path.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(payload))
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, stats_path)
        os.chmod(stats_path, 0o644)
    except Exception:
        pass

    previous_usage = cpu_usage
    previous_ts = now
    time.sleep(5)
PYEOF
    RESOURCE_STATS_PID=$!
    echo "[supervisor] Resource stats collector iniciado (PID $RESOURCE_STATS_PID)"
}

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
    kill "$RESOURCE_STATS_PID" 2>/dev/null || true
    kill "$MOSQUITTO_PID" 2>/dev/null
    wait "$MOSQUITTO_PID" 2>/dev/null
    exit 0
}
trap cleanup TERM INT

start_resource_stats_collector
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

