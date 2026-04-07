#!/bin/sh

# Create required directories and files
# Note: /var/lib/mosquitto, /etc/mosquitto, and /var/log/mosquitto are shared
# Docker volumes managed by the bunkerm-mosquitto standalone container. BunkerM
# mounts them read/write to access DynSec JSON, mosquitto.conf, and broker logs.
mkdir -p /var/log/supervisor /var/log/nginx /var/log/api /nextjs/data
touch /var/log/api/api_activity.log
chmod -R 755 /var/log/supervisor
chmod -R 755 /var/log/api
mkdir -p /nextjs/data && chmod 755 /nextjs/data

# ── API key bootstrap ──────────────────────────────────────────────────────────
# Priority:
#   1. API_KEY env var set by the user at runtime (docker run -e API_KEY=...)
#   2. Persisted key file from a previous run  (volume-mounted /nextjs/data/)
#   3. Generate a fresh cryptographically-random key (first-ever startup)
KEY_FILE="/nextjs/data/.api_key"
DEFAULT_KEY="default_api_key_replace_in_production"

if [ -n "$API_KEY" ] && [ "$API_KEY" != "$DEFAULT_KEY" ]; then
    # Explicit env var supplied — persist it so the UI and Python file-readers agree
    echo "$API_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "[BunkerM] Using API key from environment variable."
elif [ -f "$KEY_FILE" ] && [ -s "$KEY_FILE" ]; then
    export API_KEY=$(cat "$KEY_FILE")
    echo "[BunkerM] Loaded existing API key from persistent storage."
else
    export API_KEY=$(openssl rand -hex 32)
    echo "$API_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "[BunkerM] Generated new API key and saved to persistent storage."
fi
# ──────────────────────────────────────────────────────────────────────────────

# Inject API key into nginx config for broker/client log proxy locations
sed -i "s/__API_KEY__/${API_KEY}/g" /etc/nginx/conf.d/default.conf

pkill nginx 2>/dev/null || true
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
