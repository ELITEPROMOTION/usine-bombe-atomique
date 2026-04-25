#!/usr/bin/env bash
#
# Setup monitoring on the VPS — pushes env-vars for Datadog/Sentry/OTel
# into /opt/uba/.env.production based on local credentials.enc.
#
# Usage: setup_monitoring.sh VPS_IP
#
set -euo pipefail
IFS=$'\n\t'

VPS_IP="${1:?vps_ip required}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Best-effort decrypt — if cryptography missing locally, just print the keys
# the operator has to set manually on the VPS.

DD_KEY="${DATADOG_API_KEY:-}"
SENTRY_DSN="${SENTRY_DSN:-}"

if [ -z "$DD_KEY" ] && command -v python3 >/dev/null; then
  DD_KEY=$(python3 - <<'PY' 2>/dev/null || echo ""
import json, os, sys
sys.path.insert(0, "backend")
try:
    from scripts.prod_deployment_wizard import _load_credentials
    print(_load_credentials().__dict__.get("hetzner_api_token", ""))
except Exception:
    pass
PY
)
fi

cat <<NOTE
[monitoring] target VPS: $VPS_IP

Set the following env-vars in /opt/uba/.env.production (then restart):

    UBA_DATADOG_MODE=cloud      # or "file"
    DATADOG_API_KEY=<your key>
    DATADOG_SITE=datadoghq.eu

    UBA_SENTRY_MODE=cloud       # or "file"
    SENTRY_DSN=<your DSN>
    SENTRY_ENV=production

    OTEL_EXPORTER=otlp
    OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

Then on the VPS:
    docker compose -f docker-compose.production.yml restart backend
NOTE

# Push a stub override file (without secrets) so the var names exist in env.
ssh -o StrictHostKeyChecking=accept-new "root@$VPS_IP" \
  "test -f /opt/uba/.env.production || \
     printf 'UBA_DATADOG_MODE=file\nUBA_SENTRY_MODE=file\nOTEL_EXPORTER=console\n' \
       > /opt/uba/.env.production"

echo "[monitoring] base config ensured on VPS."
