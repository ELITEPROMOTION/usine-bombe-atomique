#!/usr/bin/env bash
#
# Post-deploy smoke tests. Exits non-zero if any critical endpoint fails.
#
# Usage: smoke_tests.sh DOMAIN
#
set -euo pipefail
IFS=$'\n\t'

DOMAIN="${1:?domain required}"
BASE="https://${DOMAIN}"
FAILED=0

probe() {
  local path="$1" expected="${2:-200}"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${BASE}${path}" || echo 000)
  if [ "$code" = "$expected" ] || [ "$code" = "401" ] || [ "$code" = "302" ]; then
    printf "  OK   %-50s -> %s\n" "$path" "$code"
  else
    printf "  FAIL %-50s -> %s\n" "$path" "$code"
    FAILED=$((FAILED + 1))
  fi
}

echo "[smoke] base=${BASE}"
probe "/api/v1/health"
probe "/api/v1/observability/datadog/status"
probe "/api/v1/observability/sentry/status"
probe "/api/v1/observability/otel/status"
probe "/api/v1/health/v2"
probe "/api/v1/slo/status"
probe "/api/v1/resilience/breakers"
probe "/docs"
probe "/"

if [ "$FAILED" -gt 0 ]; then
  echo "[smoke] $FAILED endpoint(s) failed."
  exit 1
fi
echo "[smoke] all OK."
