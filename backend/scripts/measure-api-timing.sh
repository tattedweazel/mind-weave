#!/usr/bin/env bash
#
# Measure response times for key Mind Weave API endpoints.
#
# Usage:
#   ./scripts/measure-api-timing.sh [BASE_URL]
#
# BASE_URL defaults to http://localhost:8000/api/v1
#
# The script uses curl's write-out format to report DNS lookup, TCP connect,
# TLS handshake, time to first byte (TTFB), and total transfer time.
#
# For authenticated endpoints, pass a cookie file:
#   ./scripts/measure-api-timing.sh http://localhost:8000/api/v1 --cookie cookies.txt

set -euo pipefail

BASE="${1:-http://localhost:8000/api/v1}"
shift 2>/dev/null || true

CURL_EXTRA_ARGS=("$@")

FMT='  dns:%{time_namelookup}s  tcp:%{time_connect}s  tls:%{time_appconnect}s  ttfb:%{time_starttransfer}s  total:%{time_total}s  status:%{http_code}  size:%{size_download}B\n'

echo "=== Mind Weave API Timing ==="
echo "Base: $BASE"
echo ""

run() {
    local label="$1"
    local method="$2"
    local url="$3"
    printf "%-35s" "$label"
    if [[ ${#CURL_EXTRA_ARGS[@]} -gt 0 ]]; then
        curl -s -o /dev/null -w "$FMT" -X "$method" "$url" "${CURL_EXTRA_ARGS[@]}" 2>/dev/null || echo "  FAILED"
    else
        curl -s -o /dev/null -w "$FMT" -X "$method" "$url" 2>/dev/null || echo "  FAILED"
    fi
}

run "GET  /health"               GET  "$BASE/health"
run "GET  /auth/me"              GET  "$BASE/auth/me"
run "POST /workspaces/bootstrap" POST "$BASE/workspaces/bootstrap"
run "GET  /models/"              GET  "$BASE/models/"
run "GET  /personas/"            GET  "$BASE/personas/"
run "GET  /documents/"           GET  "$BASE/documents/"
run "GET  /palettes/"            GET  "$BASE/palettes/"
run "GET  /workflow-definitions/" GET  "$BASE/workflow-definitions/"

echo ""
echo "Tip: Pass --cookie cookies.txt for authenticated endpoints."
echo "     Server-Timing header is also returned on each response."
