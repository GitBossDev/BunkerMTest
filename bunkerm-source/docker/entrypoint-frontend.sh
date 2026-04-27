#!/bin/bash
# entrypoint-frontend.sh
#
# Sustituye variables de entorno en la plantilla nginx, luego arranca nginx y
# Next.js standalone en paralelo.
#
# Variables consumidas:
#   BACKEND_URL  — upstream del servicio API, ej. http://bhm-api:9001
#   API_KEY      — inyectada en las rutas /api/logs/* para autenticar al API
#
# Exit codes:
#   El script no retorna hasta que nginx o node termina. Si cualquiera de los
#   dos procesos muere, el contenedor se reinicia via K8s (restartPolicy).

set -e

BACKEND_URL="${BACKEND_URL:-http://bhm-api:9001}"
API_KEY="${API_KEY:-replace_in_production}"

# Escapar caracteres especiales en API_KEY para uso seguro en sed
ESCAPED_API_KEY=$(printf '%s\n' "$API_KEY" | sed -e 's/[\/&]/\\&/g')

# Sustituir las variables en el archivo de configuración
sed -e "s|\${BACKEND_URL}|$BACKEND_URL|g" \
    -e "s|\${API_KEY}|$ESCAPED_API_KEY|g" \
    < /etc/nginx/conf.d/default.conf.template \
    > /etc/nginx/conf.d/default.conf

# Arrancar Next.js en background.
# Se fuerza HOSTNAME=0.0.0.0 porque Kubernetes inyecta HOSTNAME=<nombre-del-pod>
# y Next.js standalone lo usa para el bind; si se deja el pod-name nginx no puede
# alcanzarlo via 127.0.0.1:3000 y devuelve 502.
HOSTNAME=0.0.0.0 node /nextjs/server.js &
NEXTJS_PID=$!

# Arrancar nginx en primer plano (gestiona el ciclo de vida del contenedor)
nginx -g 'daemon off;' &
NGINX_PID=$!

# Esperar a que cualquier proceso termine; si uno muere, terminar el otro
wait -n "$NEXTJS_PID" "$NGINX_PID"
EXIT_CODE=$?

kill "$NEXTJS_PID" "$NGINX_PID" 2>/dev/null || true
exit $EXIT_CODE
