#!/usr/bin/env bash
# TLS audit V9 staging via testssl.sh
#
# Usage : ./testssl_audit.sh https://uba-staging-api.onrender.com
#
# Prerequis : testssl.sh installe (curl, openssl, dig requis)
#   wget https://testssl.sh/testssl.sh && chmod +x testssl.sh
#   ou : brew install testssl  /  apt install testssl.sh

set -u
URL="${1:-}"
if [ -z "$URL" ]; then
  echo "Usage: $0 <URL>"
  exit 1
fi

HOST=$(echo "$URL" | sed -e 's|^https\?://||' -e 's|/.*$||')

if ! command -v testssl.sh >/dev/null 2>&1 && ! [ -x "./testssl.sh" ]; then
  echo "testssl.sh not found."
  echo "Install: wget https://testssl.sh/testssl.sh && chmod +x testssl.sh"
  echo "Then run: ./testssl.sh $URL"
  exit 2
fi

TESTSSL=$(command -v testssl.sh || echo "./testssl.sh")
OUT="testssl_$(date +%Y%m%d_%H%M%S).log"

echo "Running testssl on $HOST -> $OUT"
"$TESTSSL" \
  --quiet \
  --color 0 \
  --severity LOW \
  --jsonfile "${OUT%.log}.json" \
  "$HOST" | tee "$OUT"

echo ""
echo "===== SUMMARY ====="
grep -E "^ ?(Overall|Rating|Severity)" "$OUT" || true
echo ""
echo "Full report : $OUT"
echo "JSON        : ${OUT%.log}.json"
