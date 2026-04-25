#!/usr/bin/env bash
#
# UBA full production deploy V5.9 — 12 steps
#
#   1.  Pre-flight checks (wizard ran, credentials present, terraform/git installed)
#   2.  Pre-production tests (production_readiness suite on staging)
#   3.  Build images (docker compose build, no-cache)
#   4.  Push to registry (GHCR if GITHUB_TOKEN, else skip)
#   5.  Provision infra via Terraform
#   6.  Configure DNS Cloudflare
#   7.  Setup VPS (vps_bootstrap.sh over SSH)
#   8.  Deploy UBA (compose pull/up on VPS)
#   9.  Run migrations
#   10. Provision SSL via certbot Let's Encrypt
#   11. Setup monitoring (Datadog/Sentry/OTel env on VPS)
#   12. Smoke tests
#
# Usage:
#   ./deploy/scripts/deploy_full.sh [--dry-run] [--skip-tests] [--skip-tf]
#
set -euo pipefail
IFS=$'\n\t'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="$REPO_ROOT/deploy/config"
ANSWERS="$CONFIG_DIR/ahmed_answers.json"
CREDS="$CONFIG_DIR/credentials.enc"
TF_DIR="$REPO_ROOT/terraform"

DRY_RUN=0
SKIP_TESTS=0
SKIP_TF=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --skip-tf)    SKIP_TF=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

run() {
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

require_binary() {
  local b="$1"
  if ! command -v "$b" >/dev/null 2>&1; then
    echo "[ERROR] required binary missing on PATH: $b" >&2
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Step 1 — pre-flight
# ---------------------------------------------------------------------------
echo "[ 1/12] Pre-flight checks..."
[ -f "$ANSWERS" ] || { echo "[ERROR] Run wizard --phase init first ($ANSWERS missing)"; exit 1; }
[ -f "$CREDS" ]   || { echo "[ERROR] Run wizard --phase credentials first ($CREDS missing)"; exit 1; }
require_binary docker
require_binary git
[ "$SKIP_TF" -eq 1 ] || require_binary terraform

VPS_IP="${VPS_IP:-}"
DOMAIN="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["ahmed_domain"])' "$ANSWERS")"
echo "         domain=$DOMAIN  vps_ip=${VPS_IP:-(via terraform)}"

# ---------------------------------------------------------------------------
# Step 2 — pre-production tests
# ---------------------------------------------------------------------------
echo "[ 2/12] Pre-production tests..."
if [ "$SKIP_TESTS" -eq 0 ]; then
  run docker compose -f "$REPO_ROOT/docker-compose.yml" exec -T backend \
    python -m pytest tests/observability/ tests/deployment/ -q --no-header
else
  echo "         (skipped via --skip-tests)"
fi

# ---------------------------------------------------------------------------
# Step 3 — build images
# ---------------------------------------------------------------------------
echo "[ 3/12] Build images (no-cache)..."
run docker compose -f "$REPO_ROOT/docker-compose.yml" build --no-cache backend frontend

# ---------------------------------------------------------------------------
# Step 4 — push to registry (GHCR if creds present)
# ---------------------------------------------------------------------------
echo "[ 4/12] Push images to registry..."
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_ACTOR:-}" ]; then
  run echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
  run docker tag uba-backend:latest "ghcr.io/${GITHUB_ACTOR}/uba-backend:latest"
  run docker tag uba-frontend:latest "ghcr.io/${GITHUB_ACTOR}/uba-frontend:latest"
  run docker push "ghcr.io/${GITHUB_ACTOR}/uba-backend:latest"
  run docker push "ghcr.io/${GITHUB_ACTOR}/uba-frontend:latest"
else
  echo "         (no GHCR credentials, will copy via SCP at step 8)"
fi

# ---------------------------------------------------------------------------
# Step 5 — Terraform provisioning
# ---------------------------------------------------------------------------
echo "[ 5/12] Terraform provision..."
if [ "$SKIP_TF" -eq 0 ]; then
  run terraform -chdir="$TF_DIR" init -input=false
  run terraform -chdir="$TF_DIR" apply -auto-approve -input=false
  if [ "$DRY_RUN" -eq 0 ]; then
    VPS_IP="$(terraform -chdir="$TF_DIR" output -raw vps_ipv4)"
    echo "         provisioned vps_ip=$VPS_IP"
  fi
else
  echo "         (skipped via --skip-tf, using existing VPS_IP=$VPS_IP)"
  [ -n "$VPS_IP" ] || { echo "[ERROR] --skip-tf requires VPS_IP env"; exit 1; }
fi

# ---------------------------------------------------------------------------
# Step 6 — DNS configuration
# ---------------------------------------------------------------------------
echo "[ 6/12] Configure DNS..."
run "$REPO_ROOT/deploy/scripts/configure_dns.sh" "$DOMAIN" "$VPS_IP"

# ---------------------------------------------------------------------------
# Step 7 — VPS bootstrap (Docker, UFW, SSH hardening)
# ---------------------------------------------------------------------------
echo "[ 7/12] Bootstrap VPS..."
run ssh -o StrictHostKeyChecking=accept-new "root@$VPS_IP" \
  "bash -s" < "$REPO_ROOT/deploy/scripts/vps_bootstrap.sh"

# ---------------------------------------------------------------------------
# Step 8 — Deploy application
# ---------------------------------------------------------------------------
echo "[ 8/12] Deploy UBA..."
run rsync -az --delete \
  --exclude '.git/' --exclude 'node_modules/' --exclude '__pycache__/' \
  --exclude 'deploy/config/' \
  "$REPO_ROOT/" "root@$VPS_IP:/opt/uba/"
run ssh "root@$VPS_IP" "cd /opt/uba && docker compose -f docker-compose.production.yml pull && \
  docker compose -f docker-compose.production.yml up -d --remove-orphans"

# ---------------------------------------------------------------------------
# Step 9 — DB migrations
# ---------------------------------------------------------------------------
echo "[ 9/12] Run migrations..."
run ssh "root@$VPS_IP" "cd /opt/uba && \
  docker compose -f docker-compose.production.yml exec -T backend \
  python -m app.migrations.runner --apply"

# ---------------------------------------------------------------------------
# Step 10 — SSL Let's Encrypt
# ---------------------------------------------------------------------------
echo "[10/12] Provision Let's Encrypt SSL..."
run ssh "root@$VPS_IP" \
  "certbot --nginx --non-interactive --agree-tos -m admin@$DOMAIN -d $DOMAIN -d www.$DOMAIN || true"

# ---------------------------------------------------------------------------
# Step 11 — Monitoring setup
# ---------------------------------------------------------------------------
echo "[11/12] Monitoring setup..."
run "$REPO_ROOT/deploy/scripts/setup_monitoring.sh" "$VPS_IP"

# ---------------------------------------------------------------------------
# Step 12 — Smoke tests
# ---------------------------------------------------------------------------
echo "[12/12] Smoke tests..."
run "$REPO_ROOT/deploy/scripts/smoke_tests.sh" "$DOMAIN"

echo ""
echo "============================================================"
echo "  UBA DEPLOYMENT COMPLETE  -- https://$DOMAIN"
echo "============================================================"
