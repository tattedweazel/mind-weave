#!/usr/bin/env bash
# Mind Weave — edge / upstream connectivity checklist (run ON THE SERVER).
#
# Use when https://app.<your-domain>/ appears to "time out" from browsers.
# Distinguishes: (A) nothing listening on :443, (B) TLS works but upstream hangs,
# (C) FastAPI not ready vs nginx OK.
#
# Optional env:
#   PUBLIC_APP_URL   e.g. https://app.example.com/  — curl from this host to itself via public IP/DNS
#   APP_HOST         e.g. app.example.com           — SNI + Host for local HTTPS curl
#   API_HOST         e.g. api.example.com           — same for API vhost
#
# Examples:
#   ./scripts/diagnose_edge_connectivity.sh
#   PUBLIC_APP_URL=https://app.example.com/ APP_HOST=app.example.com ./scripts/diagnose_edge_connectivity.sh

set -u

echo "== Listening sockets (443 / 8000 / 5173) =="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep -E ':443|:8000|:5173' || echo "(no matches — nothing on these ports?)"
else
  echo "ss not found; install iproute2/iproute2mac or use: lsof -nP -iTCP -sTCP:LISTEN"
fi

echo
echo "== FastAPI health (127.0.0.1:8000) =="
if curl -sS -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" --max-time 5 http://127.0.0.1:8000/api/v1/health 2>&1; then
  :
else
  echo "curl failed — uvicorn may be down or not on 8000"
fi

echo
echo "== Vite dev (127.0.0.1:5173) — only if nginx proxies app to Vite =="
curl -sS -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" --max-time 3 http://127.0.0.1:5173/ 2>&1 || echo "(connection refused or timeout — Vite not running?)"

if [[ -n "${APP_HOST:-}" ]]; then
  echo
  echo "== Local HTTPS with SNI (nginx on loopback) Host=${APP_HOST} =="
  curl -vkI --max-time 15 --resolve "${APP_HOST}:443:127.0.0.1" "https://${APP_HOST}/" 2>&1 | head -40 || true
fi

if [[ -n "${API_HOST:-}" ]]; then
  echo
  echo "== Local HTTPS API Host=${API_HOST} =="
  curl -skI --max-time 15 --resolve "${API_HOST}:443:127.0.0.1" "https://${API_HOST}/api/v1/health" 2>&1 | head -25 || true
fi

if [[ -n "${PUBLIC_APP_URL:-}" ]]; then
  echo
  echo "== Same machine → PUBLIC_APP_URL (routing / hairpin NAT) =="
  curl -vkI --max-time 15 "${PUBLIC_APP_URL}" 2>&1 | head -40 || true
fi

echo
echo "== nginx error log hints (paths vary by OS) =="
echo "  Debian/Ubuntu: sudo tail -n 80 /var/log/nginx/error.log"
echo "  macOS Homebrew:  tail -n 80 \"\$(brew --prefix)/var/log/nginx/error.log\""
echo "Look for: upstream timed out | connect() failed | Connection refused | invalid URL prefix"

echo
echo "== Repo reference: which upstream owns app vs api =="
echo "  docs/examples/nginx/mind-weave.conf.example"
echo "  api.*  → proxy_pass http://127.0.0.1:8000 (including location /)"
echo "  app.*  → proxy_pass http://127.0.0.1:5173 OR static root+try_files (see commented production block)"
