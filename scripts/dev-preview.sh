#!/usr/bin/env bash
set -u

# Print the local PropGuard AI preview URLs without stopping or restarting
# any existing development server.

HOST="${HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

FRONTEND_URL="http://${HOST}:${FRONTEND_PORT}"
DASHBOARD_URL="${FRONTEND_URL}/dashboard"
BACKEND_URL="http://${HOST}:${BACKEND_PORT}"
HEALTH_URL="${BACKEND_URL}/api/health"

open_browser=false
if [[ "${1:-}" == "--open" ]]; then
  open_browser=true
fi

http_status() {
  local url="$1"
  local status
  status="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 2 "$url" 2>/dev/null || true)"
  if [[ "$status" =~ ^[23][0-9][0-9]$ ]]; then
    echo "$status"
  fi
}

listener() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR > 1 {print $1 " pid=" $2 " " $9}' | head -n 1
}

frontend_status="$(http_status "$DASHBOARD_URL")"
backend_status="$(http_status "$HEALTH_URL")"
frontend_listener="$(listener "$FRONTEND_PORT")"
backend_listener="$(listener "$BACKEND_PORT")"

echo "PropGuard AI local preview"
echo
echo "Dashboard: ${DASHBOARD_URL}"
echo "Frontend:  ${FRONTEND_URL}"
echo "Backend:   ${BACKEND_URL}"
echo
echo "Status:"
if [[ -n "$frontend_status" ]]; then
  echo "  frontend OK  HTTP ${frontend_status}  ${frontend_listener:-listener unknown}"
else
  echo "  frontend not reachable on ${HOST}:${FRONTEND_PORT}"
fi

if [[ -n "$backend_status" ]]; then
  echo "  backend  OK  HTTP ${backend_status}  ${backend_listener:-listener unknown}"
else
  echo "  backend  not reachable on ${HOST}:${BACKEND_PORT}"
fi

echo
echo "This script is read-only for dev servers: it does not stop, kill, or restart anything."

if [[ -z "$frontend_status" || -z "$backend_status" ]]; then
  cat <<EOF

If you need to start them manually:
  cd backend && python -m uvicorn app.main:app --host ${HOST} --port ${BACKEND_PORT}
  cd frontend && NEXT_PUBLIC_API_URL=${BACKEND_URL} npm run dev -- --hostname ${HOST} --port ${FRONTEND_PORT}
EOF
fi

if [[ "$open_browser" == true ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$DASHBOARD_URL"
  else
    echo
    echo "--open requested, but the 'open' command is not available."
  fi
fi
