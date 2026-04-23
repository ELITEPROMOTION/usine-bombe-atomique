#!/usr/bin/env bash
# restore.sh - restauration Postgres depuis Scaleway.
#
# Usage :
#   restore.sh --list                     # liste backups disponibles
#   restore.sh --latest                   # restaure le plus recent
#   restore.sh --key postgres/2026/04/uba_20260423T020000Z.pgcustom
#
# ATTENTION : ecrase la base active. Arreter workers + backend AVANT.

set -euo pipefail

: "${PGHOST:?PGHOST required}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
: "${PGDATABASE:?PGDATABASE required}"
: "${SCW_ACCESS_KEY:?SCW_ACCESS_KEY required}"
: "${SCW_SECRET_KEY:?SCW_SECRET_KEY required}"
: "${SCW_BUCKET:=uba-backups}"
: "${SCW_ENDPOINT:=https://s3.fr-par.scw.cloud}"
: "${SCW_REGION:=fr-par}"

export RCLONE_CONFIG_SCW_TYPE=s3
export RCLONE_CONFIG_SCW_PROVIDER=Scaleway
export RCLONE_CONFIG_SCW_ACCESS_KEY_ID="$SCW_ACCESS_KEY"
export RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
export RCLONE_CONFIG_SCW_REGION="$SCW_REGION"
export RCLONE_CONFIG_SCW_ENDPOINT="$SCW_ENDPOINT"

log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
err() { printf '[%s] ERROR: %s\n' "$(date -Is)" "$*" >&2; }
die() { err "$*"; exit 1; }

MODE=""; KEY=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --list)   MODE="list"; shift ;;
    --latest) MODE="latest"; shift ;;
    --key)    MODE="key"; KEY="$2"; shift 2 ;;
    -h|--help)
      sed -n '/^# restore/,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -n "$MODE" ]] || die "specify --list / --latest / --key"

if [[ "$MODE" == "list" ]]; then
  rclone lsl "scw:$SCW_BUCKET/postgres/" --include '*.pgcustom' | sort -k2
  exit 0
fi

if [[ "$MODE" == "latest" ]]; then
  KEY=$(rclone ls "scw:$SCW_BUCKET/postgres/" --include '*.pgcustom' \
        | awk '{print $NF}' | sort | tail -1)
  [[ -n "$KEY" ]] || die "no backup found"
  KEY="postgres/$KEY"
fi

[[ -n "$KEY" ]] || die "missing key"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
LOCAL="$TMPDIR/restore.pgcustom"

log "download scw:$SCW_BUCKET/$KEY"
rclone copyto "scw:$SCW_BUCKET/$KEY" "$LOCAL"

# Manifest
MANIFEST_KEY="${KEY%.pgcustom}.manifest.json"
if rclone lsf "scw:$SCW_BUCKET/$MANIFEST_KEY" >/dev/null 2>&1; then
  rclone copyto "scw:$SCW_BUCKET/$MANIFEST_KEY" "$TMPDIR/manifest.json"
  log "manifest: $(cat "$TMPDIR/manifest.json")"
  EXPECTED_SHA=$(grep -oE '"sha256":"[^"]+"' "$TMPDIR/manifest.json" | cut -d: -f2 | tr -d '"')
  ACTUAL_SHA=$(sha256sum "$LOCAL" | awk '{print $1}')
  [[ "$EXPECTED_SHA" == "$ACTUAL_SHA" ]] || die "hash mismatch expected=$EXPECTED_SHA got=$ACTUAL_SHA"
  log "hash verified OK"
fi

# Restore (DROP + RECREATE tables - custom format handles dependencies)
log "!!! Destructive restore into $PGDATABASE - 5s to ctrl-c"
sleep 5

# Terminate active connections
PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -U "$PGUSER" -d postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname='$PGDATABASE' AND pid <> pg_backend_pid();
" || true

# pg_restore with --clean drops existing objects before create
PGPASSWORD="$PGPASSWORD" pg_restore \
  --host="$PGHOST" --username="$PGUSER" --dbname="$PGDATABASE" \
  --clean --if-exists --no-owner --no-privileges \
  --verbose \
  "$LOCAL"

log "OK - restored from $KEY"
log "Next steps:"
log "  1. docker compose -f docker-compose.production.yml restart backend worker worker_automation worker_automation_2"
log "  2. curl -f https://uba.dendani.dz/api/v1/health"
