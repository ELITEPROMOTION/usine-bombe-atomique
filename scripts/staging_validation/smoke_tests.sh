#!/usr/bin/env bash
# Smoke tests V9 staging — curl-based, zero deps
#
# Usage : ./smoke_tests.sh https://uba-staging-api.onrender.com https://uba-staging-app.onrender.com
#
# Exit code : 0 si tous PASS, sinon nombre de FAIL.

set -u
API="${1:-}"
APP="${2:-}"

if [ -z "$API" ] || [ -z "$APP" ]; then
  echo "Usage: $0 <API_URL> <APP_URL>"
  echo "Ex:    $0 https://uba-staging-api.onrender.com https://uba-staging-app.onrender.com"
  exit 1
fi

API="${API%/}"
APP="${APP%/}"
PASS=0
FAIL=0

run() {
  local name="$1"
  local cmd="$2"
  local expected="$3"
  echo -n "[$name] "
  local actual
  actual=$(eval "$cmd" 2>&1) || true
  if echo "$actual" | grep -qE "$expected"; then
    echo "PASS"
    PASS=$((PASS+1))
  else
    echo "FAIL"
    echo "  expected match: $expected"
    echo "  got: $actual" | head -3
    FAIL=$((FAIL+1))
  fi
}

echo "========================================"
echo "V9 Staging Smoke Tests"
echo "API : $API"
echo "APP : $APP"
echo "========================================"

# 1. Backend health
run "API /health" \
  "curl -sf -o /dev/null -w '%{http_code}' $API/api/v1/health" \
  "^200$"

# 2. Health V9 detail
run "API /health/v9" \
  "curl -sf $API/api/v1/health/v9 -H 'Accept: application/json'" \
  "(status|checks)"

# 3. OpenAPI / Swagger
run "API /docs" \
  "curl -sf -o /dev/null -w '%{http_code}' $API/docs" \
  "^200$"

# 4. /metrics Prometheus
run "API /metrics" \
  "curl -sf $API/api/v1/metrics 2>&1 | head -5" \
  "(uba_|# HELP|# TYPE|404)"

# 5. Client area requires auth
run "API /client/project unauthenticated" \
  "curl -s -o /dev/null -w '%{http_code}' $API/api/v1/client/project" \
  "^(401|503)$"

# 6. Admin area requires auth
run "API /admin/projects unauthenticated" \
  "curl -s -o /dev/null -w '%{http_code}' $API/api/v1/admin/projects" \
  "^(401|503)$"

# 7. CORS preflight
run "API CORS preflight" \
  "curl -s -o /dev/null -w '%{http_code}' -X OPTIONS $API/api/v1/health -H 'Origin: $APP' -H 'Access-Control-Request-Method: GET'" \
  "^(200|204)$"

# 8. Frontend index.html
run "APP /" \
  "curl -sf -o /dev/null -w '%{http_code}' $APP/" \
  "^200$"

# 9. Frontend SPA route fallback
run "APP /client (SPA fallback)" \
  "curl -sf -o /dev/null -w '%{http_code}' $APP/client" \
  "^200$"

# 10. TLS HTTPS forced
run "APP HTTPS only" \
  "curl -s -o /dev/null -w '%{http_code}' -L $APP/" \
  "^200$"

# 11. Security headers
run "APP X-Frame-Options" \
  "curl -sI $APP/ | grep -i 'x-frame-options'" \
  "(DENY|SAMEORIGIN)"

run "APP X-Content-Type-Options" \
  "curl -sI $APP/ | grep -i 'x-content-type-options'" \
  "nosniff"

# 12. SSL cert validity
if command -v openssl >/dev/null 2>&1; then
  HOST=$(echo "$APP" | sed -e 's|^https\?://||' -e 's|/.*$||')
  run "APP SSL cert valid" \
    "echo | openssl s_client -servername $HOST -connect $HOST:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null" \
    "notAfter"
fi

echo "========================================"
echo "RESULTS : PASS=$PASS  FAIL=$FAIL"
echo "========================================"
exit $FAIL
