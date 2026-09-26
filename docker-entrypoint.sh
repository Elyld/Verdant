#!/bin/sh
# Verdant container entrypoint.
#
#   HOST=127.0.0.1        bind only loopback (e.g. cloudflared on the same machine)
#   PORT=8000             listen port (default 8000)
#   TUNNEL_MODE=true      trust the tunnel's X-Forwarded-* headers so the app
#                         sees real client IPs (rate limiting, logs). Only set
#                         this when a trusted reverse proxy/tunnel is the sole
#                         client — never with the port published to a LAN.
set -eu

ARGS="--host ${HOST:-0.0.0.0} --port ${PORT:-8000}"
if [ "${TUNNEL_MODE:-false}" = "true" ]; then
  ARGS="$ARGS --proxy-headers"
fi

# shellcheck disable=SC2086
exec uvicorn app.main:app $ARGS
