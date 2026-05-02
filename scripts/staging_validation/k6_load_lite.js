// k6 load test lite — V9 staging
//
// Usage :
//   API_BASE=https://uba-staging-api.onrender.com k6 run scripts/staging_validation/k6_load_lite.js
//
// Profil :
//   - 0 -> 10 users en 30s (ramp-up)
//   - 10 users pendant 1min (steady)
//   - 10 -> 0 users en 30s (ramp-down)
//   - Total : 2min
//   - Endpoints non-auth seulement (health + docs + cors)
//
// Thresholds :
//   - p95 < 1500ms (free tier cold-start tolerance)
//   - error_rate < 5%

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate } from 'k6/metrics';

const API = __ENV.API_BASE || 'https://uba-staging-api.onrender.com';
const errorRate = new Rate('errors');
const requests = new Counter('requests_total');

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // ramp-up
    { duration: '60s', target: 10 },   // steady
    { duration: '30s', target: 0 },    // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    errors: ['rate<0.05'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  group('health', function () {
    const r = http.get(`${API}/api/v1/health`);
    requests.add(1);
    const ok = check(r, {
      'health status 200': (r) => r.status === 200,
      'health duration < 2s': (r) => r.timings.duration < 2000,
    });
    errorRate.add(!ok);
  });

  group('docs', function () {
    const r = http.get(`${API}/docs`);
    requests.add(1);
    check(r, {
      'docs status 200': (r) => r.status === 200,
    });
  });

  group('client unauthenticated 401', function () {
    const r = http.get(`${API}/api/v1/client/project`);
    requests.add(1);
    check(r, {
      'client unauth status 401 or 503': (r) =>
        r.status === 401 || r.status === 503,
    });
  });

  sleep(1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data),
    'k6_summary.json': JSON.stringify(data, null, 2),
  };
}

function textSummary(data) {
  const m = data.metrics;
  return `
=== k6 Load Test Lite — V9 Staging ===
Total requests : ${m.http_reqs.values.count}
Failed         : ${(m.http_req_failed.values.rate * 100).toFixed(2)}%
Duration p50   : ${m.http_req_duration.values['p(50)'].toFixed(0)}ms
Duration p95   : ${m.http_req_duration.values['p(95)'].toFixed(0)}ms
Duration max   : ${m.http_req_duration.values.max.toFixed(0)}ms

Verdict :
  p95 < 1500ms ? ${m.http_req_duration.values['p(95)'] < 1500 ? 'PASS' : 'FAIL'}
  err < 5%     ? ${m.http_req_failed.values.rate < 0.05 ? 'PASS' : 'FAIL'}
`;
}
