#!/usr/bin/env bash
# Deploy V9 staging sur Fly.io — automation post `flyctl auth login`
#
# Usage :
#   bash scripts/staging_validation/deploy_fly.sh
#
# Pre-requis :
#   1. flyctl installe (cf. playbook V9_TEMPORARY_HOSTING_PLAYBOOK.md)
#   2. flyctl auth login deja fait (browser flow)
#   3. Lance depuis la racine du repo (pwd contient fly_backend.toml)

set -euo pipefail

if [ ! -f "fly_backend.toml" ] || [ ! -f "fly_frontend.toml" ]; then
  echo "ERROR: must be run from repo root (fly_backend.toml + fly_frontend.toml requis)"
  exit 1
fi

if ! command -v flyctl >/dev/null 2>&1; then
  echo "ERROR: flyctl not in PATH. Cf. V9_TEMPORARY_HOSTING_PLAYBOOK.md etape 1."
  exit 1
fi

if ! flyctl auth whoami >/dev/null 2>&1; then
  echo "ERROR: flyctl pas connecte. Lance: flyctl auth login"
  exit 1
fi

REGION="${FLY_REGION:-cdg}"
ORG="${FLY_ORG:-personal}"
BACKEND_APP="uba-staging-api"
FRONTEND_APP="uba-staging-app"
DB_APP="uba-staging-db"

echo "========================================"
echo "V9 staging deploy Fly.io"
echo "Backend  : $BACKEND_APP"
echo "Frontend : $FRONTEND_APP"
echo "DB       : $DB_APP"
echo "Region   : $REGION"
echo "Org      : $ORG"
echo "========================================"

# ----------------------------------------------------------------------
# 1. Postgres dev (free tier sans carte)
# ----------------------------------------------------------------------
if flyctl postgres list --json 2>/dev/null | grep -q "\"$DB_APP\""; then
  echo "[1/5] Postgres '$DB_APP' deja existant, skip create"
else
  echo "[1/5] Creating Postgres dev '$DB_APP'..."
  flyctl postgres create \
    --name "$DB_APP" \
    --region "$REGION" \
    --vm-size shared-cpu-1x \
    --volume-size 1 \
    --initial-cluster-size 1 \
    --org "$ORG"
fi

# ----------------------------------------------------------------------
# 2. Backend app create + attach DB
# ----------------------------------------------------------------------
if flyctl apps list --json 2>/dev/null | grep -q "\"Name\":\"$BACKEND_APP\""; then
  echo "[2/5] Backend app '$BACKEND_APP' deja existant"
else
  echo "[2/5] Creating backend app '$BACKEND_APP'..."
  flyctl apps create "$BACKEND_APP" --org "$ORG"
fi

# Attach Postgres (idempotent — re-run no-op si deja attache)
echo "[2/5] Attach Postgres -> $BACKEND_APP..."
flyctl postgres attach "$DB_APP" --app "$BACKEND_APP" --yes 2>&1 \
  | grep -v "already attached" || true

# ----------------------------------------------------------------------
# 3. Backend secrets
# ----------------------------------------------------------------------
echo "[3/5] Setting backend secrets..."
JWT_ADMIN=$(openssl rand -hex 32)
JWT_CLIENT=$(openssl rand -hex 32)

flyctl secrets set \
  --app "$BACKEND_APP" \
  JWT_ADMIN_SECRET="$JWT_ADMIN" \
  JWT_CLIENT_SECRET="$JWT_CLIENT" \
  --stage

echo "  JWT secrets generes (32 bytes hex)."
echo "  ⚠ Sauvegarde-les si tu veux acceder depuis local :"
echo "  JWT_ADMIN_SECRET=$JWT_ADMIN"
echo "  JWT_CLIENT_SECRET=$JWT_CLIENT"

# Optional secrets — manuel si Stripe test mode
if [ -n "${STRIPE_API_KEY:-}" ]; then
  flyctl secrets set --app "$BACKEND_APP" \
    STRIPE_API_KEY="$STRIPE_API_KEY" \
    STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET:-}" \
    --stage
  echo "  Stripe secrets set."
fi

if [ -n "${SENTRY_DSN:-}" ]; then
  flyctl secrets set --app "$BACKEND_APP" SENTRY_DSN="$SENTRY_DSN" --stage
  echo "  Sentry DSN set."
fi

# ----------------------------------------------------------------------
# 4. Backend deploy
# ----------------------------------------------------------------------
echo "[4/5] Deploying backend..."
flyctl deploy \
  --config fly_backend.toml \
  --app "$BACKEND_APP" \
  --remote-only \
  --strategy rolling

BACKEND_URL="https://${BACKEND_APP}.fly.dev"
echo "  Backend deployed : $BACKEND_URL"

# Smoke test backend
echo "[4/5] Smoke test backend..."
sleep 5
if curl -sf "$BACKEND_URL/api/v1/health" >/dev/null; then
  echo "  Backend health OK ✓"
else
  echo "  WARN: backend health check failed. Check logs: flyctl logs --app $BACKEND_APP"
fi

# ----------------------------------------------------------------------
# 5. Frontend create + deploy
# ----------------------------------------------------------------------
if flyctl apps list --json 2>/dev/null | grep -q "\"Name\":\"$FRONTEND_APP\""; then
  echo "[5/5] Frontend app '$FRONTEND_APP' deja existant"
else
  echo "[5/5] Creating frontend app '$FRONTEND_APP'..."
  flyctl apps create "$FRONTEND_APP" --org "$ORG"
fi

echo "[5/5] Deploying frontend..."
flyctl deploy \
  --config fly_frontend.toml \
  --app "$FRONTEND_APP" \
  --remote-only \
  --strategy rolling

FRONTEND_URL="https://${FRONTEND_APP}.fly.dev"
echo "  Frontend deployed : $FRONTEND_URL"

# Smoke test frontend
sleep 3
if curl -sf -L "$FRONTEND_URL/" >/dev/null; then
  echo "  Frontend health OK ✓"
else
  echo "  WARN: frontend health check failed."
fi

# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------
echo ""
echo "========================================"
echo "DEPLOY DONE ✓"
echo "========================================"
echo "Backend  : $BACKEND_URL"
echo "Frontend : $FRONTEND_URL"
echo "Postgres : $DB_APP"
echo ""
echo "Next steps :"
echo "  1. Ouvre $FRONTEND_URL dans le browser"
echo "  2. Lance smoke tests :"
echo "       bash scripts/staging_validation/smoke_tests.sh \\"
echo "         $BACKEND_URL $FRONTEND_URL"
echo ""
echo "Logs en temps reel :"
echo "  flyctl logs --app $BACKEND_APP"
echo "  flyctl logs --app $FRONTEND_APP"
echo ""
echo "SSH dans le container backend :"
echo "  flyctl ssh console --app $BACKEND_APP"
echo "========================================"
