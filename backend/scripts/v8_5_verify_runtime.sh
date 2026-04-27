#!/usr/bin/env bash
# V8.5F : verifie que le runtime actif (containers Docker) charge bien les
# nouveaux modules V8.5 et expose l'endpoint /quality_gates.
set -euo pipefail

echo "==> 1. QualityGatesEngine importable in backend container :"
docker compose exec -T backend python -c "
from app.orchestration.quality_gates import (
    QualityGatesEngine, validate_deliverable, GATE_ORDER, persist_results,
)
from app.orchestration.validation_score_v2 import (
    compute_breakdown, decision_for, ACCEPTED_MIN, MAX_TOTAL,
)
print('QualityGatesEngine class methods:',
      [m for m in dir(QualityGatesEngine) if not m.startswith('_')])
print('GATE_ORDER:', GATE_ORDER)
print('ACCEPTED_MIN:', ACCEPTED_MIN, 'MAX_TOTAL:', MAX_TOTAL)
print('OK')
"

echo
echo "==> 2. Worker container (worker_automation_2) imports :"
docker compose exec -T worker_automation_2 python -c "
from app.worker import _run_quality_gates_v8_5, _maybe_reenqueue_for_regen
print('worker hooks importable: OK')
"

echo
echo "==> 3. Endpoint /quality_gates exposed in OpenAPI :"
HOST=${BACKEND_HOST:-http://localhost:8000}
curl -fsS "${HOST}/openapi.json" | python -c "
import json, sys
spec = json.load(sys.stdin)
paths = list(spec.get('paths', {}).keys())
v85 = [p for p in paths if 'quality_gates' in p or '/validation' in p]
print('V8.5F paths exposed:')
for p in sorted(v85):
    print(f'  {p}')
assert any('/quality_gates' in p for p in v85), 'quality_gates endpoint missing'
print('OK')
"

echo
echo "==> 4. DB tables + columns present :"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-uba}" -d "${POSTGRES_DB:-uba}" -t -c "
SELECT (
   (SELECT COUNT(*) FROM pg_tables
     WHERE tablename IN ('delivery_quality_gates','quality_gate_failures'))
 = 2
)::text AS tables_present,
(
   (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_name = 'tasks'
       AND column_name IN ('validation_breakdown_json','validation_attempts',
                           'validation_decision','quality_gates_history_json'))
 = 4
)::text AS tasks_cols_present;
"

echo
echo "DONE — V8.5F runtime verified."
