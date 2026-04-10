#!/bin/sh
# Entrypoint for the standalone mosquitto container.
# Ensures runtime directories are writable and the password file exists before
# handing off to the mosquitto daemon.

set -e

# Ensure persistence and log directories exist and belong to the mosquitto process
mkdir -p /var/lib/mosquitto /var/log/mosquitto
chown -R mosquitto:mosquitto /var/lib/mosquitto /var/log/mosquitto 2>/dev/null || true

# Create the password file on first start so mosquitto does not abort.
# The bunkerm config service populates it via mosquitto_passwd at runtime.
if [ ! -f /var/lib/mosquitto/mosquitto_passwd ]; then
    touch /var/lib/mosquitto/mosquitto_passwd
    chown mosquitto:mosquitto /var/lib/mosquitto/mosquitto_passwd 2>/dev/null || true
fi

exec /usr/sbin/mosquitto -c /etc/mosquitto/mosquitto.conf "$@"
