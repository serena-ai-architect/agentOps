# AgentOps — Production Roadmap

> From working MVP to production-grade enterprise platform.
> Each phase is independently valuable — you don't need to finish all phases to ship.

---

## Where We Are Now (Phase 1 — Complete)

**Status: Code complete, 62 tests passing, Docker-ready.**

| Capability | Status |
|-----------|--------|
| 3 automated workflows (resource provisioning, CI/CD pipeline, domain management) | ✅ Complete |
| Multi-cloud support (Alibaba, Huawei, Tencent) | ✅ Complete |
| Lark approval-driven trigger | ✅ Complete |
| Audit logging (operation_log + resource_record) | ✅ Complete |
| Idempotency engine (webhook dedup via task_records) | ✅ Complete |
| Task state machine (pending → running → success/failed) | ✅ Complete |
| Task status API (GET /api/tasks) | ✅ Complete |
| Scheduled tasks (expiry alerts, cost reports) | ✅ Complete |
| Automated tests (62 tests, 8 test modules) | ✅ Complete |

**What's missing for production:**

| Gap | Risk if not addressed | Phase |
|-----|----------------------|-------|
| No persistent task queue (crash = lost in-flight task) | Task silently lost, no retry | 2 |
| SQLite (no concurrent writes, no row-level locking) | Corruption under concurrent approvals | 2 |
| Credentials in plaintext env vars | Security audit failure | 3 |
| No resource locking (two approvals for same resource = duplicates) | Wasted cloud spend | 2 |
| No rate limiting on cloud APIs | 429 errors cascade into failures | 2 |
| Passwords in DB unencrypted | Data breach liability | 3 |
| No cloud abstraction layer | Every new resource type = modify 3 if-elif branches | 4 |

---

## Phase 2 — Production Reliability (est. 1–2 weeks)

> **Goal:** Tasks survive crashes, concurrent requests don't corrupt data.

### 2.1 PostgreSQL Migration

**Why:** SQLite can't do concurrent writes or row-level locking. Two approvals hitting the API at the same time will corrupt the database.

**What:**
- Change `database_url` in config to PostgreSQL
- Add `asyncpg` dependency
- Run Alembic migration (or auto-create)
- No code changes needed — SQLAlchemy abstracts the dialect

**Effort:** 2 hours (config + dependency + deploy)

### 2.2 Persistent Task Worker

**Why:** Currently `background_tasks.add_task()` runs inline in the FastAPI process. If the process restarts mid-task, the task is lost forever.

**What:**
- `engine/worker.py` — `TaskWorker` that polls `task_records` for pending tasks
- Uses `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL) to atomically claim tasks
- Runs as a background loop inside the FastAPI lifespan (or as a separate process)
- Failed tasks auto-retry up to `max_retries`

**Effort:** 1 day

### 2.3 Resource Locking

**Why:** If two people submit approvals for "order-service Redis" simultaneously, two Redis instances get created.

**What:**
- `engine/lock.py` — PostgreSQL advisory lock keyed on `project + resource_type`
- Acquire lock before cloud API call, release after
- Conflicting requests get a clear error: "order-service Redis 正在创建中"

**Effort:** Half day

### 2.4 Cloud API Rate Limiting

**Why:** Alibaba Cloud APIs are typically limited to 20–50 QPS. Burst traffic → 429 → cascading failures.

**What:**
- `cloud/rate_limiter.py` — Token bucket limiter, per cloud provider
- Sits between task execution and cloud API calls

**Effort:** Half day

### Phase 2 Deliverable

After Phase 2, the system can handle:
- Process crash/restart → tasks resume from last known state
- Concurrent approvals → properly serialized, no duplicates
- Burst traffic → rate-limited, no 429 cascades
- Any failure → auto-retry with backoff

**This is the threshold for "can run in production without someone watching it."**

---

## Phase 3 — Security Hardening (est. 1 week)

> **Goal:** Pass a security review.

### 3.1 Credential Management

| Current | Target |
|---------|--------|
| Cloud API keys in `.env` plaintext | HashiCorp Vault or cloud KMS |
| Passwords sent via Lark in plaintext | Passwords encrypted at rest, sent via Lark DM only |
| Single set of credentials (full admin access) | Per-workflow RAM/IAM roles (least privilege) |

### 3.2 Operation Security

| Current | Target |
|---------|--------|
| Any approved request executes immediately | High-risk operations (production, GPU) require secondary approval |
| No change windows | Production changes restricted to maintenance windows |
| No operation limits | Daily/monthly spend caps with auto-halt |

### 3.3 Audit Enhancement

| Current | Target |
|---------|--------|
| operation_log table | Append-only audit log (immutable, tamper-evident) |
| No access logging | Log every API call with caller identity |

---

## Phase 4 — Cloud Abstraction Layer (est. 2 weeks)

> **Goal:** Add a new cloud provider or resource type without touching existing code.

### What

Replace the `if provider == "alibaba" / elif "huawei" / elif "tencent"` pattern with a `CloudProviderInterface` + `CloudRegistry`:

```
CloudProviderInterface (abstract)
├── AlibabaProvider
├── HuaweiProvider
└── TencentProvider

CloudRegistry
├── register(provider, implementation)
├── get(provider) → CloudProviderInterface
└── select_best_provider(resource_type) → CloudProvider
```

### Why it matters

- Adding "AWS" = implement one class + register. Zero changes to existing code.
- AI agent integration (Phase 2 roadmap — conversational ops): the AI asks the registry "can Huawei do Redis?" instead of hardcoding knowledge.
- Health-based routing: if Alibaba API is down, auto-route to Huawei.

---

## Phase 5 — AI Conversational Operations (from phase2-plan.md)

> **Goal:** Replace "fill a 7-field approval form" with "@AgentOps 帮我开一个 4G Redis".

This is documented in detail in `docs/phase2-plan.md`. Prerequisites: Phase 2 (reliability) + Phase 4 (cloud abstraction).

---

## Decision Log

| Decision | Choice | Why |
|----------|--------|-----|
| Task queue | Database queue, not Celery/Redis | Volume is 10–100 tasks/day, not 10K/sec. DB queue = zero extra infra + native persistence |
| Distributed lock | PostgreSQL advisory lock | Already have PostgreSQL from Phase 2. No need for Redis/etcd |
| Rate limiter | In-process token bucket | Single-process deployment. If we scale to multi-process, move to Redis-backed limiter |
| Cloud abstraction timing | Phase 4, not Phase 1 | Premature abstraction. Current 3-provider if-elif works fine with <10 resource types. Abstract when it hurts |

---

## Summary: What Each Phase Enables

```
Phase 1 (Done)     → "It works" — automated cloud ops with audit trail
Phase 2 (Next)     → "It's reliable" — crash-safe, concurrent, rate-limited
Phase 3            → "It's secure" — passes security review, least-privilege
Phase 4            → "It's extensible" — new providers/resources = one class
Phase 5            → "It's intelligent" — natural language cloud operations
```

**For interview context:** Phases 1 is shipped. Phase 2 design is in `docs/architecture-concurrency-cloud.md` with full code-level design (task worker, advisory locks, token bucket, state machines). This demonstrates that the system was designed with production in mind from the start — the MVP was a deliberate first step, not a shortcut.
