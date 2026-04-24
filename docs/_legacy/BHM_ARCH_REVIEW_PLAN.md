# BHM - Architecture Review Correction Plan

> Scope: correctivos detectados en la revision de arquitectura del 2026-04-21
> Runtime de referencia: Compose-first (docker-compose.dev.yml) + laboratorio kind (k8s/base)
> Conventions: code and file content in English, comments and documentation in Spanish, no emojis

---

## Phases overview

| Phase | Focus | Issues covered | Risk |
|-------|-------|----------------|------|
| 1 | Quick wins — manifests and config | #4, #7, #8, #2 | Low |
| 2 | Security and resilience | #5, #3 | Medium |
| 3 | Data persistence | #6 | Medium |
| 4 | Documentation alignment | #9 | Low |
| 5 | Architectural split | #1 | High |

---

## Phase 1 — Quick wins: manifests and config

**Goal**: Fix low-risk issues that are pure YAML / config edits with no code changes.

---

### Issue 4 — Missing resource limits in control-plane.yaml

**Problem**: `bunkerm-platform` Deployment in `k8s/base/control-plane.yaml` has no
`resources.requests` or `resources.limits`. The Kubernetes scheduler cannot bin-pack
correctly and the pod can starve the node.

#### Checklist

- [x] Add `resources` block to the `platform` container in `k8s/base/control-plane.yaml`
  - requests: cpu 200m, memory 384Mi
  - limits: cpu 1000m, memory 768Mi
- [x] Verify that `bhm-alert-delivery.yaml` already has resource limits (it does — no change needed)
- [x] Check that `postgres.yaml` StatefulSet has resource limits and add if missing
- [x] Check that `mosquitto.yaml` StatefulSet containers (broker, reconciler, observability) have resource limits and add if missing

#### Validation

- [ ] `kubectl describe pod bunkerm-platform-<hash> -n bhm-lab` shows `Requests` and `Limits` populated
- [ ] `kubectl top pod -n bhm-lab` shows realistic CPU/memory consumption vs limits
- [ ] Run smoke: `.\deploy.ps1 -Action smoke -Runtime kind`

---

### Issue 8 — newTag: latest as default in kustomization.yaml

**Problem**: `k8s/base/kustomization.yaml` defaults to `newTag: latest` for both platform
and mosquitto images. In Kubernetes, `latest` with `imagePullPolicy: Never` (kind lab) is
not reproducible and can silently pick up a stale cached image.

#### Checklist

- [x] Change default `newTag` from `latest` to a documented placeholder tag (e.g. `dev`) in `k8s/base/kustomization.yaml`
- [x] Add a comment above the `images` block explaining that the tag must be overridden via `deploy.ps1 -ImageTag <tag>`
- [x] Verify `k8s/scripts/bootstrap-kind.ps1` passes `-ImageTag` and does not rely on the default

#### Validation

- [ ] `kustomize build k8s/base | grep image:` shows the placeholder, not `latest`
- [ ] `.\deploy.ps1 -Action build -Runtime kind -ImageTag review-01` builds correctly
- [ ] `.\deploy.ps1 -Action start -Runtime kind -ImageTag review-01` applies with the explicit tag
- [ ] Smoke: `.\deploy.ps1 -Action smoke -Runtime kind`

---

### Issue 7 — Over-provisioning of secrets in bhm-reconciler (Compose)

**Problem**: In `docker-compose.dev.yml`, `bhm-reconciler` receives `JWT_SECRET`,
`AUTH_SECRET`, and `BROKER_OBSERVABILITY_URL`. The reconciler is a pure broker-facing
daemon. It only needs MQTT credentials, PostgreSQL URLs, and broker filesystem paths.
Principle of least privilege is violated.

#### Checklist

- [x] Remove `JWT_SECRET` from `bhm-reconciler` environment block in `docker-compose.dev.yml`
- [x] Remove `AUTH_SECRET` from `bhm-reconciler` environment block
- [x] Remove `BROKER_OBSERVABILITY_URL` from `bhm-reconciler` environment block
- [x] Remove `FRONTEND_URL`, `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `RATE_LIMIT_PER_MINUTE` (irrelevant to a daemon with no HTTP interface)
- [x] Confirm `broker_reconcile_daemon.py` only uses: `DATABASE_URL`, `CONTROL_PLANE_DATABASE_URL`, `MOSQUITTO_*`, `MQTT_*`, `DYNSEC_PATH`, `LOG_LEVEL`, `TZ`

#### Validation

- [ ] `docker compose -f docker-compose.dev.yml config` shows the slimmed environment for `bhm-reconciler`
- [ ] `docker compose -f docker-compose.dev.yml up bhm-reconciler --no-deps` starts without error
- [ ] Reconciler log shows normal polling cycles: `Broker reconcile cycle applied`
- [ ] Run smoke: `.\deploy.ps1 -Action smoke`

---

### Issue 2 — bhm-reconciler mounts bunkerm-nextjs volume in Compose

**Problem**: `bhm-reconciler` in `docker-compose.dev.yml` mounts `bunkerm-nextjs:/nextjs/data`.
That volume belongs to the platform web service and was originally used for a
`/nextjs/data/reconcile-secrets` handoff that has already been replaced by PostgreSQL.
This is a residual coupling with no operational justification.

#### Checklist

- [x] Remove `- bunkerm-nextjs:/nextjs/data` from `bhm-reconciler.volumes` in `docker-compose.dev.yml`
- [x] Confirm `broker_reconcile_daemon.py` and `broker_reconcile_runner.py` do not read or write `/nextjs/data` at runtime
- [x] Search codebase for `reconcile-secrets` references and confirm all are dead code or already guarded by configuration
- [x] If `broker_reconcile_secret_dir` setting still points to `/nextjs/data/reconcile-secrets`, update its default in `core/config.py` to a path inside `/var/lib/mosquitto` or remove if unused

#### Validation

- [ ] `docker compose -f docker-compose.dev.yml config` shows no `bunkerm-nextjs` mount in `bhm-reconciler`
- [ ] `docker compose -f docker-compose.dev.yml up bhm-reconciler --no-deps` starts without error
- [ ] `docker exec bunkerm-reconciler ls /nextjs` fails (path does not exist inside the container)
- [ ] Run smoke: `.\deploy.ps1 -Action smoke`

---

## Phase 2 — Security and resilience

---

### Issue 5 — ALLOWED_ORIGINS=* and ALLOWED_HOSTS=* in K8s ConfigMap

**Problem**: `k8s/base/kustomization.yaml` ConfigMapGenerator hardcodes
`ALLOWED_ORIGINS=*` and `ALLOWED_HOSTS=*`. These wildcards are acceptable in a
local dev lab but must not reach any cluster exposed beyond localhost.

**Strategy**: introduce a `kind` overlay that keeps wildcards explicitly for the lab,
and replace the base ConfigMap values with restrictive placeholders that force an
intentional override per environment.

#### Checklist

- [x] In `k8s/base/kustomization.yaml`, change base values:
  - `ALLOWED_ORIGINS=REPLACE_WITH_ALLOWED_ORIGIN`
  - `ALLOWED_HOSTS=REPLACE_WITH_ALLOWED_HOST`
- [x] Create `k8s/kind/kustomization.yaml` overlay (or edit if it already exists) that patches
  `ALLOWED_ORIGINS=*` and `ALLOWED_HOSTS=*` back for the lab environment only
- [ ] Verify `FastAPI TrustedHostMiddleware` respects `ALLOWED_HOSTS` at runtime
- [ ] Verify CORS middleware respects `ALLOWED_ORIGINS` at runtime
- [ ] Add a note in `ARCHITECTURE.md` under "Immovable Design Decisions" about CORS/host scope per environment

#### Validation

- [ ] `kustomize build k8s/base | grep ALLOWED_ORIGINS` shows the restrictive placeholder
- [ ] `kustomize build k8s/kind | grep ALLOWED_ORIGINS` shows `*`
- [ ] `.\deploy.ps1 -Action smoke -Runtime kind` still passes (lab still uses wildcard via overlay)
- [ ] Manual: `curl -H "Origin: http://evil.example.com" http://localhost:22000/api/v1/monitor/health` from a non-kind deployment returns CORS rejection

---

### Issue 3 — Fragile liveness/readiness probes using ps -ef | grep

**Problem**: `reconciler` sidecar in `mosquitto.yaml` and `bhm-alert-delivery` in
`alert-delivery.yaml` use `ps -ef | grep <daemon_name> | grep -v grep` as liveness
and readiness probe. This probe:
- returns healthy for a zombie or permanently-blocked process
- has a race window when the process name appears in other contexts
- provides no insight into whether the daemon is actually doing useful work

**Strategy**: add a lightweight heartbeat file mechanism to both daemons. Each daemon
writes a timestamp to a file on a fixed interval. The probe checks that the file exists
and was written within a configurable staleness window using a small Python one-liner.

#### Checklist

**broker_reconcile_daemon.py**
- [x] After each successful reconcile cycle, write current UTC epoch to `/tmp/reconciler.alive`
- [x] After each failed cycle (exception caught), still write the heartbeat so the probe
      does not kill the pod on transient errors — use a separate error counter if needed
- [x] On daemon startup, write the heartbeat immediately before the first cycle

**alert_delivery_daemon.py**
- [x] Apply the same heartbeat write pattern to `/tmp/alert_delivery.alive`

**k8s/base/mosquitto.yaml** — reconciler sidecar
- [x] Replace `ps -ef | grep` readinessProbe command with heartbeat-file Python one-liner (60 s window)
- [x] Replace livenessProbe command with the same check but with a wider window (120 s)
- [x] Adjust `initialDelaySeconds` to allow at least one reconcile cycle before the probe fires

**k8s/base/alert-delivery.yaml**
- [x] Apply equivalent probe replacement using `/tmp/alert_delivery.alive`

#### Validation

- [ ] `.\deploy.ps1 -Action start -Runtime kind -ImageTag review-01`
- [ ] `kubectl get pods -n bhm-lab` shows both `reconciler` and `alert-delivery` as `Running` and `Ready`
- [ ] Simulate probe failure: `kubectl exec -n bhm-lab <mosquitto-pod> -c reconciler -- rm /tmp/reconciler.alive`
      then wait 2x periodSeconds and confirm pod is restarted by Kubernetes
- [ ] Smoke: `.\deploy.ps1 -Action smoke -Runtime kind`

---

## Phase 3 — Data persistence

---

### Issue 6 — smart_anomaly.db on emptyDir in K8s

**Problem**: `core/config.py` sets `smart_anomaly_db_url` pointing to
`/nextjs/data/smart_anomaly.db`. In `k8s/base/control-plane.yaml`, the `nextjs-data`
volume is `emptyDir: {}`, so the trained model state and anomaly history are lost on
every pod restart.

**Decision point**: before implementing, choose one of two paths:

| Path | Description | Effort |
|------|-------------|--------|
| A | Migrate smart-anomaly state to PostgreSQL | High |
| B | Add a PVC for `nextjs-data` in the kind lab | Low |

Path B is the recommended first step: it unblocks the lab with minimal risk and does
not preclude a future migration to PostgreSQL.

#### Checklist (Path B — PVC for nextjs-data)

- [x] In `k8s/base/control-plane.yaml`, replace the `nextjs-data` `emptyDir` volume with a
      `PersistentVolumeClaim` reference
- [x] Add a `PersistentVolumeClaim` manifest for `nextjs-data` with `ReadWriteOnce` and 2Gi storage,
      or add it as a `volumeClaimTemplate` if the Deployment is later converted to StatefulSet
- [x] Since `Deployment` does not support `volumeClaimTemplates`, create a standalone `PVC` manifest
      `k8s/base/nextjs-data-pvc.yaml` and reference it from `control-plane.yaml`
- [x] Add `nextjs-data-pvc.yaml` to the `resources` list in `k8s/base/kustomization.yaml`
- [x] Verify that `bunkerm-nextjs` named volume in Compose continues to work (it already uses a named volume — no change needed there)

#### Validation

- [ ] `kubectl get pvc -n bhm-lab` shows `nextjs-data` as `Bound`
- [ ] `kubectl exec -n bhm-lab <platform-pod> -- ls /nextjs/data` shows existing files after pod restart
- [ ] Restart the platform pod: `kubectl rollout restart deployment/bunkerm-platform -n bhm-lab`
- [ ] Confirm `smart_anomaly.db` persists: `kubectl exec -n bhm-lab <platform-pod> -- ls -la /nextjs/data/smart_anomaly.db`
- [ ] Smoke: `.\deploy.ps1 -Action smoke -Runtime kind`

---

## Phase 4 — Documentation alignment

---

### Issue 9 — ROADMAP.md shows obsolete architecture

**Problem**: The "Architecture diagram" section in `ROADMAP.md` still shows the old
multi-port microservice topology (ports 1000-1008) and SQLite as the primary database.
This contradicts the current unified backend on port 9001 and the PostgreSQL baseline.

#### Checklist

- [x] Update the architecture diagram in `ROADMAP.md` to reflect the current topology:
  - Single nginx on :2000
  - Single uvicorn on :9001 (internal)
  - Separate broker container
  - PostgreSQL as primary persistent store
- [x] Remove or update the technology table row that still shows SQLite as integrated storage
- [x] Confirm `ARCHITECTURE.md` and `BHM_MICROSERVICES_MIGRATION_PLAN.md` are consistent
      with the updated ROADMAP diagram (they already are — cross-check only)

#### Validation

- [ ] Visual review: no port in the 1000-1008 range appears in the updated diagram
- [ ] No reference to SQLite as the primary store in the updated section
- [ ] No functional code change — documentation only, no smoke test required

---

## Phase 5 — Architectural split: bunkerm-platform monolith

**Problem**: `bunkerm-platform` runs nginx + Next.js + FastAPI in a single container via
supervisord. The architecture target defines `bhm-web` (Next.js) and `bhm-api` (FastAPI)
as separate services. This is the most significant remaining structural gap.

**Note**: This phase is high-effort and high-risk. It should not begin until Phases 1-4
are closed and validated. A dedicated ADR (ADR-0010 or similar) should be written before
any code changes begin.

#### Pre-conditions

- [ ] Phases 1 through 4 are fully closed and smoke-tested
- [ ] A new ADR is written and accepted covering:
  - how Next.js will call the FastAPI backend once they are in separate pods
  - whether nginx moves to `bhm-web` or becomes a standalone ingress/gateway
  - secret and ConfigMap distribution between the two new services
  - rollback strategy if the split introduces regressions

#### High-level activities (to be detailed in the ADR)

- [ ] Extract FastAPI backend into standalone image `bhm-api` without nginx or supervisord
- [ ] Extract Next.js frontend into standalone image `bhm-web` served by nginx or a minimal Node server
- [ ] Define new Kubernetes Services and update `control-plane.yaml` or replace it with two manifests
- [ ] Update the Compose service split in `docker-compose.dev.yml`
- [ ] Update `ARCHITECTURE.md` port topology and key files table
- [ ] Migrate all smoke tests and architecture tests to the new topology

#### Validation (to be defined in the ADR)

- [ ] All existing smoke tests pass against the split topology
- [ ] `tests/test_architecture.py` updated to reflect new image boundaries
- [ ] Frontend can reach backend API with no direct database access
- [ ] Reconciler and alert-delivery daemons are unaffected by the split

---

## Cross-cutting rules (applies to all phases)

- All YAML, code, and file content in English
- All inline comments and documentation in Spanish
- No emojis in any file
- Every phase closes with a passing smoke run: `.\deploy.ps1 -Action smoke`
- Every K8s change is validated against the kind lab: `.\deploy.ps1 -Action smoke -Runtime kind`
- No phase modifies production secrets or shared infrastructure without explicit confirmation
- Each issue is treated as an independent commit or PR to allow safe rollback

---

## Status tracking

| Issue | Phase | Status |
|-------|-------|--------|
| #4 — Resource limits control-plane.yaml | 1 | done 2026-04-21 |
| #8 — newTag: latest default | 1 | done 2026-04-21 |
| #7 — Over-provisioning secrets reconciler | 1 | done 2026-04-21 |
| #2 — bhm-reconciler mounts bunkerm-nextjs | 1 | done 2026-04-21 |
| #5 — ALLOWED_ORIGINS=* in K8s ConfigMap | 2 | done 2026-04-21 |
| #3 — Fragile ps-grep probes | 2 | done 2026-04-21 |
| #6 — smart_anomaly.db on emptyDir | 3 | done 2026-04-21 |
| #9 — ROADMAP obsolete architecture diagram | 4 | done 2026-04-21 |
| #1 — bunkerm-platform monolith split | 5 | pending |
