#!/bin/sh
# =============================================================================
# BunkerM Extended - Mosquitto Standalone Entrypoint
#
# Responsibilities:
#   1. Seed shared volumes on first start (mosquitto.conf, dynamic-security.json)
#   2. Run a signal relay in the background: watches for /var/lib/mosquitto/.reload
#      and sends SIGHUP to the mosquitto process (PID 1) so it reloads config
#      and DynSec without a full restart.
#   3. Exec mosquitto as PID 1 so Docker signals are forwarded correctly.
# =============================================================================
set -e

# ── 1. Seed mosquitto.conf if the shared volume is empty ─────────────────────
if [ ! -f /etc/mosquitto/mosquitto.conf ]; then
    echo "[mosquitto-entrypoint] Seeding mosquitto.conf to shared volume..."
    cp /mosquitto-seeds/mosquitto.conf /etc/mosquitto/mosquitto.conf
    chmod 644 /etc/mosquitto/mosquitto.conf
fi

# ── 2. Ensure conf.d directory exists ────────────────────────────────────────
mkdir -p /etc/mosquitto/conf.d

# ── 3. Seed dynamic-security.json if the shared volume is empty ──────────────
if [ ! -f /var/lib/mosquitto/dynamic-security.json ]; then
    echo "[mosquitto-entrypoint] Seeding dynamic-security.json to shared volume..."
    cp /mosquitto-seeds/dynamic-security.json /var/lib/mosquitto/dynamic-security.json
fi

# ── 4. Set correct permissions on shared volumes ─────────────────────────────
chown -R mosquitto:mosquitto /var/lib/mosquitto /var/log/mosquitto
chmod -R 755 /var/lib/mosquitto
chmod 644 /etc/mosquitto/mosquitto.conf
mkdir -p /var/log/mosquitto
touch /var/log/mosquitto/mosquitto.log
chown mosquitto:mosquitto /var/log/mosquitto/mosquitto.log

# ── 5. Signal relay: watches .reload flag and sends SIGHUP ───────────────────
#
# BunkerM's Python backends write /var/lib/mosquitto/.reload whenever they
# need mosquitto to reload (bridge config changes, DynSec import, etc.).
# This loop picks it up and sends SIGHUP to PID 1 (mosquitto itself).
# Using SIGHUP is safe: mosquitto re-reads config + DynSec without dropping
# existing client connections.
#
signal_relay() {
    while true; do
        if [ -f /var/lib/mosquitto/.reload ]; then
            rm -f /var/lib/mosquitto/.reload
            echo "[signal-relay] Reload requested — sending SIGHUP to mosquitto..."
            kill -HUP 1 2>/dev/null || echo "[signal-relay] SIGHUP failed (mosquitto not ready yet?)"
        fi
        sleep 2
    done
}
signal_relay &

# ── 6. Start mosquitto as PID 1 ──────────────────────────────────────────────
echo "[mosquitto-entrypoint] Starting mosquitto..."
exec mosquitto -c /etc/mosquitto/mosquitto.conf
