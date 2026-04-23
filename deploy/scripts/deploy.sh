#!/usr/bin/env bash
# deploy.sh - deploiement atomique UBA production.
#
# A lancer SUR LE VPS dans /srv/uba/
# Usage :
#   ./deploy.sh              -> pull + rolling restart
#   ./deploy.sh --full       -> rebuild local + restart complet
#   ./deploy.sh --migrate    -> applique migrations SQL en attente
#   ./deploy.sh --rollback   -> revient a l'image precedente
#
# Presuppose :
#   - docker + docker-compose-plugin installes
#   - .env.production present et rempli
#   - SSH key GitHub registered (pour ghcr.io si registry prive)

set -euo pipefail

cd "$(dirname "$0")/../.."

: "${UBA_DIR:=$(pwd)}"
: "${COMPOSE:=docker compose -f docker-compose.production.yml}"
: "${HEALTH_URL:=https://uba.dendani.dz/api/v1/health}"
: "${DOCKER_REGISTRY:=ghcr.io/dendani}"

log() { printf '\033[36m[%s]\033[0m %s\n' "$(date -Is)" "$*"; }
err() { printf '\033[31m[%s] ERROR:\033[0m %s\n' "$(date -Is)" "$*" >&2; }
die() { err "$*"; exit 1; }

# --- 1. Parse args ---
MODE="rolling"
while [[ $# -gt 0 ]]; do
  case $1 in
    --full)     MODE="full"; shift ;;
    --migrate)  MODE="migrate"; shift ;;
    --rollback) MODE="rollback"; shift ;;
    -h|--help)
      sed -n '/^# deploy/,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

# --- 2. Sanity checks ---
[[ -f .env.production ]] || die "missing .env.production"
[[ -f docker-compose.production.yml ]] || die "missing docker-compose.production.yml"
command -v docker >/dev/null || die "docker not installed"

# --- 3. Persister version actuelle pour rollback ---
CURRENT_TAG="$(cat .uba_current_version 2>/dev/null || echo latest)"
NEW_TAG="${UBA_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"

if [[ "$MODE" == "rollback" ]]; then
  PREV_TAG="$(cat .uba_previous_version 2>/dev/null || die "no previous version saved")"
  log "rollback $CURRENT_TAG -> $PREV_TAG"
  export UBA_VERSION="$PREV_TAG"
  $COMPOSE pull backend frontend worker worker_automation worker_automation_2 || true
  $COMPOSE up -d backend frontend worker worker_automation worker_automation_2
  echo "$PREV_TAG" > .uba_current_version
  mv .uba_previous_version .uba_rolledback_from 2>/dev/null || true
  exit 0
fi

# --- 4. Sauvegarder pre-deploy ---
log "pre-deploy backup"
$COMPOSE exec -T backup /backup.sh || log "backup skipped (service down)"

# --- 5. Pull images + start ---
case $MODE in
  full)
    log "FULL rebuild local"
    $COMPOSE build --pull backend frontend
    $COMPOSE down
    $COMPOSE up -d
    ;;
  rolling|migrate)
    log "pull images (version=$NEW_TAG)"
    UBA_VERSION="$NEW_TAG" $COMPOSE pull backend frontend worker worker_automation worker_automation_2

    log "apply stack (rolling)"
    UBA_VERSION="$NEW_TAG" $COMPOSE up -d --remove-orphans

    if [[ "$MODE" == "migrate" ]]; then
      log "applying pending migrations"
      $COMPOSE exec -T backend python -c "
import asyncio, os
from pathlib import Path
from app.database import init_pool, close_pool
async def run():
    pool = await init_pool()
    applied = set()
    async with pool.acquire() as c:
        await c.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
          name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())''')
        rows = await c.fetch('SELECT name FROM schema_migrations')
        applied = {r['name'] for r in rows}
    for f in sorted(Path('/app/migrations/versions').glob('*.sql')):
        if f.name in applied: continue
        print(f'applying {f.name}')
        sql = f.read_text()
        async with pool.acquire() as c, c.transaction():
            await c.execute(sql)
            await c.execute('INSERT INTO schema_migrations(name) VALUES(\$1)', f.name)
    await close_pool()
asyncio.run(run())
"
    fi
    ;;
esac

# --- 6. Health gate ---
log "health check (60s timeout)"
for i in $(seq 1 30); do
  if curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1; then
    log "backend healthy"
    break
  fi
  sleep 2
  [[ $i -eq 30 ]] && die "backend unhealthy - consider ./deploy.sh --rollback"
done

# --- 7. Post-deploy smoke tests ---
log "smoke tests"
for route in / /ceo /automation /api/v1/workflows/scheduled; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://uba.dendani.dz$route" || echo 000)
  log "  $route -> HTTP $code"
  [[ "$code" == "200" || "$code" == "401" || "$code" == "302" ]] || err "  unexpected status on $route"
done

# --- 8. Memo version ---
mv .uba_current_version .uba_previous_version 2>/dev/null || true
echo "$NEW_TAG" > .uba_current_version

log "deploy OK (version=$NEW_TAG)"
$COMPOSE ps --format "table {{.Name}}\t{{.Status}}" | head -20
