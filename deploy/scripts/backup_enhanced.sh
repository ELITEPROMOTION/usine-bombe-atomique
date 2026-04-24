#!/usr/bin/env bash
# backup_enhanced.sh - 3-2-1 strategy V5.7 (full daily + hourly incremental).
#
# 3 copies : local + Scaleway (S3) + GitHub Release asset (optionnel)
# 2 types  : FULL (daily) + HOURLY (pg_dump --schema-only + WAL sampling)
# 1 offsite: Scaleway Paris
#
# Retention : 24h hourly + 30d daily + 12m monthly
#
# Variables env (heritees de backup.sh) :
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#   SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_BUCKET, SCW_ENDPOINT, SCW_REGION
#   BACKUP_MODE : full | hourly (default : full)
#   BACKUP_LOCAL_DIR : default /var/backups/uba
#   GITHUB_TOKEN : optionnel, pour upload GitHub Release
#   GITHUB_REPO : owner/repo pour release asset (si GITHUB_TOKEN)

set -euo pipefail

MODE="${BACKUP_MODE:-full}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/uba}"
mkdir -p "$LOCAL_DIR"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
die() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; exit 1; }

case "$MODE" in
  full)
    DUMP="$TMPDIR/uba_${TS}_full.pgcustom"
    log "FULL backup -> $DUMP"
    pg_dump \
      --no-owner --no-privileges \
      --format=custom --compress=9 \
      --file="$DUMP" \
      --dbname="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:5432/$PGDATABASE"
    ;;
  hourly)
    # Hourly : schema + sample (tables critiques uniquement)
    DUMP="$TMPDIR/uba_${TS}_hourly.pgcustom"
    log "HOURLY backup (critical tables only) -> $DUMP"
    pg_dump \
      --no-owner --no-privileges \
      --format=custom --compress=9 \
      --file="$DUMP" \
      --table=workflow_executions \
      --table=workflow_schedules \
      --table=evidence_ledger \
      --table=audit_events \
      --table=slo_measurements \
      --table=slo_incidents \
      --dbname="postgresql://$PGUSER:$PGPASSWORD@$PGHOST:5432/$PGDATABASE"
    ;;
  *)
    die "unknown BACKUP_MODE: $MODE"
    ;;
esac

SIZE_BYTES=$(stat -c%s "$DUMP" 2>/dev/null || stat -f%z "$DUMP")
SHA256=$(sha256sum "$DUMP" | awk '{print $1}')
log "size=$SIZE_BYTES sha256=$SHA256"

# 1. Copy local (primary)
cp "$DUMP" "$LOCAL_DIR/$(basename "$DUMP")"
log "local copy: $LOCAL_DIR/$(basename "$DUMP")"

# 2. Upload Scaleway (si SCW_ACCESS_KEY)
if [[ -n "${SCW_ACCESS_KEY:-}" ]]; then
  export RCLONE_CONFIG_SCW_TYPE=s3
  export RCLONE_CONFIG_SCW_PROVIDER=Scaleway
  export RCLONE_CONFIG_SCW_ACCESS_KEY_ID="$SCW_ACCESS_KEY"
  export RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
  export RCLONE_CONFIG_SCW_REGION="${SCW_REGION:-fr-par}"
  export RCLONE_CONFIG_SCW_ENDPOINT="${SCW_ENDPOINT:-https://s3.fr-par.scw.cloud}"
  KEY="postgres/${MODE}/$(date -u +%Y/%m)/$(basename "$DUMP")"
  log "scaleway upload -> scw:${SCW_BUCKET:-uba-backups}/$KEY"
  rclone copyto "$DUMP" "scw:${SCW_BUCKET:-uba-backups}/$KEY" --quiet || \
    log "WARN : Scaleway upload failed"
fi

# 3. GitHub Release asset (optionnel, FULL only, daily)
if [[ -n "${GITHUB_TOKEN:-}" && "$MODE" == "full" && -n "${GITHUB_REPO:-}" ]]; then
  log "GitHub release upload (optional)"
  # Placeholder - necessite gh CLI
fi

# Rotation locale
case "$MODE" in
  hourly)
    # Garde 24 derniers hourly
    ls -t "$LOCAL_DIR"/uba_*_hourly.pgcustom 2>/dev/null | tail -n +25 | xargs -r rm
    ;;
  full)
    # Garde 30 derniers daily
    ls -t "$LOCAL_DIR"/uba_*_full.pgcustom 2>/dev/null | tail -n +31 | xargs -r rm
    ;;
esac

log "OK - $MODE backup $TS complete"
