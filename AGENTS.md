# AGENTS.md — AgentOps

## Quick Reference
- Architecture: FastAPI + SQLAlchemy, approval-driven autonomous workflows
- Stack: Python 3.12, FastAPI, SQLAlchemy (async), APScheduler
- Multi-cloud: Alibaba Cloud (primary), Huawei Cloud (GPU), Tencent Cloud
- Entry point: Lark approval webhooks → POST /api/lark/events
- Vision: AI-native DevOps platform — replacing manual ops with autonomous agents

## Documentation Index
→ docs/architecture-concurrency-cloud.md — 9-pillar architecture (concurrency, cloud, monitoring, security, cost, backup, migration, network, upgrades)
→ docs/phase2-plan.md — Phase 2: AI chat-driven ops + LLM vibe coding
→ docs/workflow-diagrams.md — Mermaid diagrams (10 figures)
→ README.md — Setup guide, Lark configuration, approval form templates

## Project Structure
→ api/lark_events.py — Lark webhook receiver (system entry point)
→ workflows/ — 3 core workflows (resource_provision, pipeline_setup, domain_change)
→ cloud/alibaba/ — 10 Alibaba Cloud API modules (rds, redis, ecs, oss, slb, sae, dns, ssl, bss, yunxiao)
→ cloud/huawei/ — Huawei Cloud (ECS/GPU)
→ cloud/tencent/ — Tencent Cloud (CVM)
→ lark/ — Lark SDK client, notifier, approval templates
→ models/ — SQLAlchemy models (resource_record, pipeline_record, operation_log)
→ scheduler.py — Scheduled tasks (expiry alerts, cost reports)
→ config.py — Pydantic settings (all cloud credentials, Lark config)

## Architectural Boundaries (enforced)
- All cloud operations go through workflows/ (never call cloud/ directly from api/)
- All notifications go through lark/notifier.py (single notification channel)
- All DB writes include operation_log entries (audit trail)
- Approval form field names defined in lark/approval_templates.py (single source of truth)

## Build & Run Commands
- `pip install -e .` — Install dependencies
- `python main.py` — Dev server (auto-reload)
- `uvicorn main:app --host 0.0.0.0 --port 8000` — Production
- `pytest` — Run tests
- `ruff check .` — Lint

## Implementation Roadmap (Phase 0-8)
See docs/architecture-concurrency-cloud.md for details:
- Phase 0: Task Engine + PostgreSQL (foundation)
- Phase 1: Cloud Abstraction Layer (unified interface)
- Phase 2: Monitoring + Auto-Scaling (highest architect-replacement value)
- Phase 3: Security Hardening
- Phase 4: Performance Tuning + Cost Optimization
- Phase 5: Backup + Disaster Recovery
- Phase 6: Cloud Migration
- Phase 7: Network Topology
- Phase 8: Upgrade + Patching

## When the Agent Struggles
If a task fails, do NOT retry with a different prompt. Instead:
1. Check if required context is discoverable from this file
2. Check lark/approval_templates.py for form field names
3. Check config.py for required environment variables
4. Check cloud/{provider}/ for SDK patterns
5. Add the fix to the repo, then retry
