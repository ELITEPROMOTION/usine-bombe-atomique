#!/usr/bin/env bash
#
# UBA full rollback V5.9 — restore previous git tag and redeploy.
#
# Usage:
#   ./deploy/scripts/rollback_full.sh                # rollback to previous tag
#   ./deploy/scripts/rollback_full.sh v5.5.5         # rollback to specific tag
#
set -euo pipefail
IFS=$'\n\t'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VPS_IP="${VPS_IP:?VPS_IP must be set}"

if [ "$#" -ge 1 ]; then
  TARGET="$1"
else
  TARGET="$(git -C "$REPO_ROOT" describe --tags --abbrev=0 'HEAD^')"
fi

echo "[rollback] target=$TARGET vps=$VPS_IP"
echo "[rollback] previous deploy archived under /opt/uba.previous on the VPS."

ssh -o StrictHostKeyChecking=accept-new "root@$VPS_IP" bash <<EOF
set -euo pipefail
cd /opt/uba

if [ -d /opt/uba.previous ]; then
  rm -rf /opt/uba.previous
fi
cp -a /opt/uba /opt/uba.previous

git fetch --tags --prune
git checkout "$TARGET"
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d --force-recreate --remove-orphans

# Verify backend health
for i in 1 2 3 4 5; do
  if curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null; then
    echo "[rollback] backend healthy after rollback"
    exit 0
  fi
  sleep 5
done

echo "[rollback] backend NOT healthy after rollback to $TARGET" >&2
exit 1
EOF

echo ""
echo "============================================================"
echo "  ROLLBACK COMPLETE  -- now serving $TARGET"
echo "============================================================"
