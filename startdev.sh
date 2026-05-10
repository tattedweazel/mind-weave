#!/usr/bin/env bash
# Mind Weave — start FastAPI backend + Vite frontend with LAN-friendly CORS/TRUSTED_HOSTS/VITE_API_BASE.
# Prefer from repo root: `make dev` (canonical in docs); this script is the single implementation.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

if [[ ! -f backend/pyproject.toml ]] || [[ ! -f frontend/package.json ]]; then
  printf '%s\n' "startdev.sh must run from the Mind Weave repository root (missing backend/pyproject.toml or frontend/package.json)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' "uv is required (install from https://docs.astral.sh/uv/). Then: cd backend && uv sync — or uv --project backend sync from the repo root." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  printf '%s\n' "npm is required (install Node.js LTS)." >&2
  exit 1
fi

if [[ ! -d frontend/node_modules ]]; then
  printf '%s\n' "Frontend dependencies missing. Run: cd frontend && npm install" >&2
  exit 1
fi

# shellcheck disable=SC1090
eval "$(uv run --project backend python backend/scripts/dev_bootstrap_env_exports.py)"

BACKEND_PID=""
FRONTEND_PID=""
_STARTDEV_CLEANUP_DONE=false

cleanup() {
  if ${_STARTDEV_CLEANUP_DONE}; then
    return 0
  fi
  _STARTDEV_CLEANUP_DONE=true
  for pid in "${BACKEND_PID}" "${FRONTEND_PID}"; do
    [[ -z "${pid}" ]] && continue
    pkill -TERM -P "${pid}" 2>/dev/null || true
    kill -TERM "${pid}" 2>/dev/null || true
  done
  if [[ -n "${BACKEND_PID}" ]]; then wait "${BACKEND_PID}" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID}" ]]; then wait "${FRONTEND_PID}" 2>/dev/null || true; fi
}

trap cleanup INT TERM EXIT

printf '\nMind Weave dev environment starting...\n\n'
printf 'Detected LAN IP: %s\n' "${BOOTSTRAP_LAN_IP}"

printf '%s\n' "---"
printf '%s\n' "Backend URLs (bind 0.0.0.0:8000):"
printf '%s\n' "  • ${VITE_API_BASE}"
[[ "${BOOTSTRAP_LAN_IP}" != "127.0.0.1" ]] && printf '%s\n' "  • http://127.0.0.1:8000" && printf '%s\n' "  • http://localhost:8000"

printf '%s\n' "---"
printf '%s\n' "Frontend (Vite, --host):"
printf '%s\n' "  • ${FRONTEND_URL}"

printf '%s\n' "---"
printf '%s\n' "FRONTEND_URL (server redirects / OAuth bookkeeping): ${FRONTEND_URL}"
printf '%s\n' "SPA → API via VITE_API_BASE: ${VITE_API_BASE}"

printf '%s\n' "---"
printf '%s\n' "CORS_ORIGINS / TRUSTED_HOSTS are set only for these child processes (your backend/.env is not rewritten)."
printf '%s\n' "CORS allowed origins:"
python3 -c 'import json, sys
try:
    for o in json.loads(sys.argv[1]):
        print(f"  - {o}")
except Exception:
    pass' "${CORS_ORIGINS}" || true

printf '%s\n' "---"
printf '%s\n' "Trusted Hosts:"
python3 -c 'import json, sys
try:
    for h in json.loads(sys.argv[1]):
        print(f"  - {h}")
except Exception:
    pass' "${TRUSTED_HOSTS}" || true

[[ "${BOOTSTRAP_LAN_IP}" != "127.0.0.1" ]] && printf '%s\n' "---" \
  && printf '%s\n' "Google OAuth note: redirects and Cloud Console URIs usually target localhost." \
  && printf '%s\n' "  If login fails while using a LAN browser URL, use http://localhost:5173 or add matching URIs."

printf '%s\n' "---"
printf '%s\n' "Press Ctrl+C to stop all services."
printf '\n'

(
  cd "${ROOT}/backend" || exit 1
  export CORS_ORIGINS TRUSTED_HOSTS FRONTEND_URL
  exec uv run python -m fastapi dev app/main.py --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

(
  cd "${ROOT}/frontend" || exit 1
  export VITE_API_BASE
  exec npm run dev:lan
) &
FRONTEND_PID=$!

wait "${FRONTEND_PID}"
