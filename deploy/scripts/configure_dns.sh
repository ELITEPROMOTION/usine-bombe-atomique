#!/usr/bin/env bash
#
# Configure Cloudflare DNS A records via API. Idempotent.
#
# Usage: configure_dns.sh DOMAIN VPS_IP
# Requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID in env (or wizard).
#
set -euo pipefail
IFS=$'\n\t'

DOMAIN="${1:?domain required}"
VPS_IP="${2:?vps_ip required}"

: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ZONE_ID:?Set CLOUDFLARE_ZONE_ID}"

API="https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records"
AUTH=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json")

upsert() {
  local name="$1" type="$2" content="$3" proxied="${4:-true}"
  local existing
  existing=$(curl -s "${AUTH[@]}" "${API}?type=${type}&name=${name}" \
    | python3 -c 'import sys,json;d=json.load(sys.stdin)["result"];print(d[0]["id"]) if d else print("")' )
  local body
  body=$(python3 -c "import json;print(json.dumps({'type':'${type}','name':'${name}','content':'${content}','ttl':1,'proxied':${proxied}}))")
  if [ -z "$existing" ]; then
    echo "[+] create ${type} ${name} -> ${content}"
    curl -sf "${AUTH[@]}" -X POST -d "$body" "${API}" >/dev/null
  else
    echo "[~] update ${type} ${name} -> ${content}"
    curl -sf "${AUTH[@]}" -X PUT -d "$body" "${API}/${existing}" >/dev/null
  fi
}

upsert "${DOMAIN}"     A     "${VPS_IP}" true
upsert "www.${DOMAIN}" CNAME "${DOMAIN}" true
upsert "api.${DOMAIN}" A     "${VPS_IP}" true

echo "[ok] DNS configured for ${DOMAIN}"
