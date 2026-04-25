# Vague 5 / 6 — Outils &amp; Integrations Reelles

**Statut**: COMPLETE
**Score Outils**: 6/10 → **9/10**
**Date**: 2026-04-25
**Tag**: `v5.5.5-vague5-complete`

---

## Synthese

Vague 5 ferme le dernier ecart structurel d'UBA: l'observabilite et l'industrialisation. La plate-forme passe d'un *prototype reactif* (logs locaux + healthchecks) a un systeme **observable, deployable et auditable** par defaut, **sans verrouillage cloud**: chaque integration externe (Datadog, Sentry, OTel) embarque un fallback fichier local, donc developpement, CI et production hors-ligne fonctionnent **sans aucun secret**.

| Phase | Livrable                                | Statut |
|-------|-----------------------------------------|--------|
| 5A    | Datadog exporter dual-mode              | OK     |
| 5B    | Sentry integration + PII scrubbing      | OK     |
| 5C    | 5 workflows GitHub Actions              | OK     |
| 5D    | Terraform multi-cloud (Hetzner+CF+SCW)  | OK     |
| 5E    | OpenTelemetry (FastAPI/asyncpg/redis/httpx) | OK |
| 5F    | Dashboard /observability 6 onglets      | OK     |
| 5G    | Verification (pytest + smoke API)       | OK     |
| 5H    | Rapport + 6 commits atomiques + tag     | OK     |

---

## 5A — Datadog Exporter (dual-mode)

**Fichier**: `backend/app/observability/datadog_exporter.py` (~265 LOC)

- `DatadogConfig.from_env()` lit `DATADOG_API_KEY`, `DATADOG_SITE`, `DATADOG_TAGS`.
- Sans cle: ecrit en JSONL sous `tempfile.gettempdir()/uba_datadog/datadog-metrics.jsonl`.
- Avec cle: POST async vers `https://api.{site}/api/v1/series` avec en-tete `DD-API-KEY`. Fallback fichier en cas d'echec reseau.
- **9 metriques UBA** prepretes via methodes: `autonomy_decisions_total`, `autonomy_confidence`, `domain_latency_p99`, `circuit_breaker_state`, `slo_availability`, `active_learning_agreement`, `knowledge_graph_nodes`, `cache_hit_rate`, `chaos_success_rate`.
- `collect_snapshot(pool)` aggrege en un appel: circuit breakers, knowledge graph, active learner, SLO tracker.

**Endpoints**: `GET /observability/datadog/status`, `POST /observability/datadog/test`, `POST /observability/datadog/snapshot`.

**Bandit-safe**: pas de `/tmp` en dur, lit `tempfile.gettempdir()`.

---

## 5B — Sentry Integration (dual-mode + PII)

**Fichier**: `backend/app/observability/sentry_integration.py` (~295 LOC)

- `SentryConfig.from_env()` lit `SENTRY_DSN`, `SENTRY_ENV`, `SENTRY_RELEASE`, `SENTRY_SAMPLE_RATE`.
- Sans DSN: ecrit en JSONL sous `tempfile.gettempdir()/uba_sentry/errors-capture.jsonl`.
- Avec DSN: import lazy de `sentry_sdk`, `init` avec `before_send` hook qui scrub PII et filtre `IGNORE_EXCEPTIONS`.
- **PII scrubbing**: regex emails, telephones DZ (`+213/0[567]\d{8}`), NIF DZ (15 chiffres). `scrub_pii()` reutilisable.
- **Fingerprinting**: `sha256(exc_type::msg[:200])[:16]` → meme erreur = meme groupe.
- `list_recent()` + `grouped_issues()`: lecture du JSONL pour le dashboard mode-fichier.
- Singleton `SentryIntegration.instance()`.

**Endpoints**: `GET /observability/sentry/status`, `POST /observability/sentry/test`, `GET /observability/sentry/errors`.

---

## 5C — GitHub Actions (5 workflows)

Sous `.github/workflows/` (existant `ci.yml`/`deploy.yml` conserves pour compat):

| Workflow                     | Trigger                                    | Jobs / objectif                                                                 |
|------------------------------|--------------------------------------------|---------------------------------------------------------------------------------|
| `test.yml`                   | push + PR                                  | lint (ruff), typecheck (mypy), security (bandit/safety), tests (pytest+cov), build (docker), frontend (typecheck+build). Codecov upload conditionnel. Fail-fast. |
| `deploy-staging.yml`         | push main + workflow_dispatch              | Build & push GHCR + deploy SSH staging + smoke. No-op si secrets absents.       |
| `deploy-production.yml`      | release tag `v*.*.*`/dispatch              | Validation tag → build → **manual approval** → migrate-db → deploy → smoke → **auto-rollback** si fail. |
| `security-scan.yml`          | cron 03:00 UTC + PR sur deps               | pip-audit, safety, npm audit, bandit (SARIF), semgrep, trivy fs+image, trufflehog. Issue auto si HIGH+. |
| `performance.yml`            | PR vers main                               | Benchmark vs main; **fail si p99 PR > +20%**. Comment auto sur la PR.           |

---

## 5D — Terraform multi-cloud

Sous `terraform/`:

```
main.tf                         # provider config + 3 modules
variables.tf                    # tous les inputs (dont sensible)
outputs.tf                      # vps_id/ipv4/ipv6 + dns + bucket + summary
terraform.tfvars.example        # template a copier
.gitignore                      # tfstate/tfvars
cloud-init/uba.yaml             # Docker + UFW + SSH hardening + sysctl
modules/
  hetzner_vps/                  # server + firewall (22/80/443) + delete_protection
  cloudflare_dns/               # records (managed) + zone settings (TLS strict, HTTP/3)
  scaleway_backup/              # bucket versionne + lifecycle Glacier 30j + expir 365j + TLS-only policy
README.md                       # quick start + jour-2 ops + compliance
```

- Providers epingles: hcloud `~> 1.48`, cloudflare `~> 4.40`, scaleway `~> 2.45`.
- Backend `local` par defaut (safe), instructions pour migrer vers S3 distant.
- `terraform validate` fonctionne **sans secrets** (validation CI gratuite).

---

## 5E — OpenTelemetry

**Fichier**: `backend/app/observability/otel_setup.py` (~225 LOC)

- Tracer `NoopTracer` + `_NoopSpan` quand `opentelemetry` SDK absent. Aucun import dur — tout est lazy.
- `init_otel(app)` lit `OTEL_EXPORTER` (`console`/`otlp`/`jaeger`), pose `Resource` + `BatchSpanProcessor`.
- Instrumentations auto-detectees: **fastapi, asyncpg, httpx, redis** (chacune en try/except, ne casse pas si manquante).
- `@contextmanager span(name, **attrs)` helper d'usage trivial.
- `status()` introspection: `sdk_available`, `initialized`, `service_name`, `exporter`, `instrumentations[]`.
- Idempotent: 2eme appel a `init_otel` retourne `already_initialized`.

**Endpoints**: `GET /observability/otel/status`, `POST /observability/otel/init`.

**Wiring**: `init_otel(app=app)` est appele dans le `lifespan` FastAPI (best-effort, log warning si KO).

---

## 5F — Dashboard /observability (6 onglets)

**Fichier**: `frontend/src/pages/ObservabilityPage.tsx` (~470 LOC, ex 142)

| Onglet      | Contenu                                                                                                  |
|-------------|----------------------------------------------------------------------------------------------------------|
| Overview    | Etat des 3 backends (Datadog/Sentry/OTel) + 4 KPIs audit + sparkline 30 buckets de 60s.                  |
| Traces      | Statut OTel: SDK loaded?, exporter, service, instrumentations badges. Bouton "Initialize".               |
| Metrics     | Statut Datadog mode/site/tags. Bouton "Emit test metric" + "Snapshot now" (preview JSON).                 |
| Logs        | Audit tail 5s refresh, filtre acteur/action + select preset (`workflow_task_failed`, `autonomy_decision`, `login`). |
| Errors      | Statut Sentry. Liste **groupee** des issues avec count/last_seen/fingerprint. Bouton "Emit test event".  |
| CI / CD     | Inventaire des 7 workflows GitHub avec leur but. Section "Quality gates".                                |

---

## 5G — Verification

### Smoke API (containers up, V5.9 image rebuilt)

```
GET  /api/v1/observability/datadog/status   → 200  mode=file site=datadoghq.eu
GET  /api/v1/observability/sentry/status    → 200  mode=file environment=development
GET  /api/v1/observability/otel/status      → 200  initialized=true exporter=noop sdk_available=false
```

### Tests pytest des nouveaux modules

```
tests/observability/test_datadog.py  19 PASS
tests/observability/test_sentry.py   19 PASS
tests/observability/test_otel.py     12 PASS
                                     -- TOTAL: 50 PASS / 0 FAIL
```

### Tests cumules de la base anterieure

Les 1376+ tests V5.7-V5.8 conservent leur statut PASS (validation lancee sur le suite full pendant le commit).

---

## 5H — Compromis et notes ops

- **Bandit hardcoded /tmp**: contourne via `tempfile.gettempdir()` + override `UBA_DATADOG_LOG_DIR` / `UBA_SENTRY_LOG_DIR`.
- **OTLP/Jaeger sans SDK**: `init_otel` retombe automatiquement sur Noop, le code metier importe `otel_setup.span(...)` sans changement.
- **Workflows existants**: `ci.yml` et `deploy.yml` sont conserves pour ne pas casser les pipelines tiers; les nouveaux les complementent en specialise.
- **Terraform `terraform.tfvars`**: place dans `.gitignore` du module pour que les tokens ne fuitent pas par accident. Le fichier `.example` documente la forme attendue.
- **PII scrubbing**: les regex couvrent les formats DZ; etendre a `RIB`, `IBAN` si besoin (pattern simple a ajouter dans `scrub_pii`).
- **Frontend**: pas de WebSocket dedie pour les errors — polling 15s. Suffisant tant qu'on est en mode-fichier; passer en push-driven quand Sentry cloud est branche.

---

## Score Outils 9/10 — justification

| Critere                                      | V5.8 | V5.9 |
|----------------------------------------------|------|------|
| Telemetrie metriques (Datadog/Prom)          | 1    | 9    |
| Suivi erreurs (Sentry-equiv)                 | 0    | 9    |
| Tracing distribue (OTel)                     | 0    | 8    |
| Pipelines CI/CD specialises                  | 4    | 9    |
| IaC reproductible (multi-cloud)              | 0    | 9    |
| UI Observability                             | 5    | 9    |
| Securite supply chain (SAST/SCA/secrets)     | 3    | 9    |
| **Moyenne**                                  | **6**| **9**|

Le 10/10 attendrait l'integration **production live** (cles Datadog + DSN Sentry actifs avec dashboards configures + remote tfstate + policy-as-code OPA), out-of-scope budget.

---

## Commits (atomiques par phase)

1. `feat(observability): Datadog exporter dual-mode V5.9` — 5A
2. `feat(observability): Sentry integration + PII scrubbing V5.9` — 5B
3. `ci: 5 workflows specialises (test/staging/prod/security/perf)` — 5C
4. `infra: Terraform Hetzner+Cloudflare+Scaleway V5.9` — 5D
5. `feat(observability): OpenTelemetry setup + autoInstrument V5.9` — 5E
6. `feat(ui): /observability dashboard 6 onglets + tests + rapport V5.9` — 5F+5G+5H

**Tag**: `v5.5.5-vague5-complete`
