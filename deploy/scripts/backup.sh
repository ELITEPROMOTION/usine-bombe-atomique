#!/usr/bin/env bash
# backup.sh - Dump Postgres + upload Scaleway Object Storage (Paris).
#
# Variables env attendues :
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#   SCW_ACCESS_KEY, SCW_SECRET_KEY
#   SCW_BUCKET (default: uba-backups)
#   SCW_ENDPOINT (default: https://s3.fr-par.scw.cloud)
#   SCW_REGION (default: fr-par)
#   BACKUP_RETENTION_DAYS (default: 30)
#
# Execute quotidiennement via cron dans le container `backup`.

set -euo pipefail

TS="$(date -u +%Y%m%dT%H%M%SZ)"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

DUMP="$TMPDIR/uba_${TS}.sql.gz"
MANIFEST="$TMPDIR/uba_${TS}.manifest.json"

: "${PGHOST:?PGHOST required}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
: "${PGDATABASE:?PGDATABASE required}"
: "${SCW_ACCESS_KEY:?SCW_ACCESS_KEY required}"
: "${SCW_SECRET_KEY:?SCW_SECRET_KEY required}"
: "${SCW_BUCKET:=uba-backups}"
: "${SCW_ENDPOINT:=https://s3.fr-par.scw.cloud}"
: "${SCW_REGION:=fr-par}"
: "${BACKUP_RETENTION_DAYS:=30}"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
err() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; }

# --- 1. pg_dump (custom format = restore sous-ensemble possible) ---
log "pg_dump $PGDATABASE -> $DUMP"
pg_dump \
  --no-owner --no-privileges \
  --format=custom --compress=9 \
  --file="$DUMP.tmp" \
  --dbname="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:5432/$PGDATABASE"

# Custom format rend le .gz redondant ; on renomme.
mv "$DUMP.tmp" "$TMPDIR/uba_${TS}.pgcustom"
DUMP="$TMPDIR/uba_${TS}.pgcustom"

SIZE_BYTES=$(stat -c%s "$DUMP" 2>/dev/null || stat -f%z "$DUMP")
SHA256=$(sha256sum "$DUMP" | awk '{print $1}')
log "dump size=$SIZE_BYTES sha256=$SHA256"

# --- 2. Manifest JSON ---
cat > "$MANIFEST" <<EOF
{
  "timestamp_utc": "$TS",
  "database": "$PGDATABASE",
  "size_bytes": $SIZE_BYTES,
  "sha256": "$SHA256",
  "pg_version": "$(pg_dump --version 2>&1)",
  "retention_days": $BACKUP_RETENTION_DAYS
}
EOF

# --- 3. Config rclone -> Scaleway ---
export RCLONE_CONFIG_SCW_TYPE=s3
export RCLONE_CONFIG_SCW_PROVIDER=Scaleway
export RCLONE_CONFIG_SCW_ACCESS_KEY_ID="$SCW_ACCESS_KEY"
export RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
export RCLONE_CONFIG_SCW_REGION="$SCW_REGION"
export RCLONE_CONFIG_SCW_ENDPOINT="$SCW_ENDPOINT"
export RCLONE_CONFIG_SCW_ACL=private

KEY="postgres/$(date -u +%Y/%m)/uba_${TS}"

log "upload -> scw:$SCW_BUCKET/$KEY.pgcustom"
rclone copyto "$DUMP" "scw:$SCW_BUCKET/$KEY.pgcustom"

log "upload -> scw:$SCW_BUCKET/$KEY.manifest.json"
rclone copyto "$MANIFEST" "scw:$SCW_BUCKET/$KEY.manifest.json"

# --- 4. Verify remote hash ---
REMOTE_HASH=$(rclone hashsum sha256 "scw:$SCW_BUCKET/$KEY.pgcustom" 2>/dev/null | awk '{print $1}' || true)
if [[ -n "$REMOTE_HASH" && "$REMOTE_HASH" != "$SHA256" ]]; then
  err "hash mismatch local=$SHA256 remote=$REMOTE_HASH"
  exit 3
fi

# --- 5. Rotation : delete > N jours ---
log "rotate retention=${BACKUP_RETENTION_DAYS}d"
rclone delete "scw:$SCW_BUCKET/postgres/" \
  --min-age "${BACKUP_RETENTION_DAYS}d" \
  --include "*.pgcustom" --include "*.manifest.json" \
  --quiet || true

# --- 6. Affiche compte backups + taille ---
COUNT=$(rclone ls "scw:$SCW_BUCKET/postgres/" 2>/dev/null | grep -c '\.pgcustom$' || echo 0)
TOTAL=$(rclone size "scw:$SCW_BUCKET/postgres/" --json 2>/dev/null | grep -oE '"bytes":[0-9]+' | head -1 | cut -d: -f2 || echo 0)
log "backups in bucket: count=$COUNT total_bytes=$TOTAL"

log "OK - backup $TS complete"
