#!/usr/bin/env bash
# V8.5F : applique les migrations 035 + 036 dans le container postgres deja
# en cours d'execution. Idempotent (CREATE TABLE IF NOT EXISTS, ADD COLUMN
# IF NOT EXISTS, sceau dans evidence_ledger via DO block).
#
# Usage : bash backend/scripts/v8_5_apply_migrations.sh
#
# Pre-requis : docker-compose stack up, postgres healthy, pgcrypto extension
# deja installee (verifiee via pg_extension).
set -euo pipefail

POSTGRES_USER="${POSTGRES_USER:-uba}"
POSTGRES_DB="${POSTGRES_DB:-uba}"

apply() {
  local f="$1"
  echo "==> Applying $(basename "$f") ..."
  docker compose exec -T postgres psql \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -v ON_ERROR_STOP=1 \
    -f "/docker-entrypoint-initdb.d/$(basename "$f")"
  echo "    OK"
}

apply backend/migrations/versions/035_v8_5_delivery_quality_gates.sql
apply backend/migrations/versions/036_v8_5_validation_score_v2.sql

echo
echo "==> Verifying applied :"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "
SELECT actor FROM evidence_ledger
 WHERE actor LIKE 'migration_03%'
 ORDER BY id;
"

echo
echo "==> Verifying tables :"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "
SELECT tablename FROM pg_tables
 WHERE tablename IN ('delivery_quality_gates','quality_gate_failures')
 ORDER BY tablename;
"

echo
echo "==> Verifying tasks columns V8.5F :"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "
SELECT column_name FROM information_schema.columns
 WHERE table_name = 'tasks'
   AND column_name IN ('validation_breakdown_json','validation_attempts',
                       'validation_decision','quality_gates_history_json')
 ORDER BY column_name;
"

echo
echo "DONE — V8.5F migrations applied."
