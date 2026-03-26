# AgentOps — Enterprise Multi-Cloud Automation Engine

> Lark-approval-driven cloud operations across Alibaba, Huawei, and Tencent Cloud — designed for regulated enterprise environments

## What It Does

Traditional ops flow: someone requests resources → ops engineer manually logs into cloud consoles → manually creates pipelines, provisions resources, configures DNS → replies verbally.

**Pain point**: ops engineers are the bottleneck — slow response, error-prone, no audit trail.

**AgentOps**: turns manual cloud operations into API-driven workflows, triggered by Lark approval forms, with full audit logging.

## Three Core Workflows

### 1. Cloud Resource Provisioning

```
Requester submits approval → Manager approves → Auto-provisions via cloud API → Notification with connection info
```

Supported: Alibaba Cloud (RDS / Redis / ECS / OSS / SLB / SAE), Huawei Cloud (Ascend GPU), Tencent Cloud (CVM)

### 2. CI/CD Pipeline Creation

```
Developer submits approval → Manager approves → Auto-creates CI/CD pipeline + assigns domain → Notification
```

After setup, every git push triggers automatic build and deploy.

### 3. Domain Management

```
Requester submits approval → Manager approves → Validates compliance → Auto-updates DNS + SSL → Notification
```

## Scheduled Tasks

- **Daily 09:00** — Scan expiring cloud resources, notify stakeholders
- **Monthly 1st 10:00** — Aggregate last month's cloud costs, push report

## Quick Start

### 1. Install

```bash
cd agentOps
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials. See [.env.example](.env.example) for all configuration options.

### 3. Run

```bash
# Development (auto-reload)
python main.py

# Production
uvicorn main:app --host 0.0.0.0 --port 8000

# Docker
docker build -t agentops .
docker run -p 8000:8000 --env-file .env agentops
```

### 4. Run Tests

```bash
pip install -e ".[dev]"
pytest
# 52 passed — covers form parsing, workflow routing, resource provisioning,
# pipeline setup, domain change, scheduled tasks, and API endpoints
```

### 5. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## Architecture

```
Approval Event → POST /api/lark/events → Workflow Router → Cloud API Calls → Notification
                                                              ↓
                                                        SQLite Audit Log
```

| Component | Tech |
|-----------|------|
| Backend | Python 3.12 + FastAPI |
| Database | SQLite (can switch to PostgreSQL) |
| Messaging | Lark (Feishu) SDK |
| Alibaba Cloud | alibabacloud-devops / alidns / rds / ecs etc. |
| Huawei Cloud | huaweicloudsdkecs |
| Tencent Cloud | tencentcloud-sdk-python |
| Scheduler | APScheduler |

## Project Structure

```
agentOps/
├── main.py                     # FastAPI entry point
├── config.py                   # Configuration (Pydantic Settings)
├── scheduler.py                # Scheduled tasks (expiry alerts + cost reports)
├── api/
│   └── lark_events.py          # Lark webhook receiver (system entry point)
├── workflows/
│   ├── pipeline_setup.py       # Workflow 1: CI/CD pipeline creation
│   ├── resource_provision.py   # Workflow 2: Multi-cloud resource provisioning
│   └── domain_change.py        # Workflow 3: Domain management
├── cloud/
│   ├── alibaba/                # Alibaba Cloud API (10 modules)
│   ├── huawei/                 # Huawei Cloud API (GPU)
│   └── tencent/                # Tencent Cloud API
├── lark/
│   ├── client.py               # Lark API client
│   ├── approval_templates.py   # Approval form field definitions
│   └── notifier.py             # Lark notifications
├── models/
│   ├── pipeline_record.py      # Pipeline records
│   ├── resource_record.py      # Resource ledger
│   └── operation_log.py        # Operation audit log
├── tests/
│   ├── test_api.py             # API endpoint tests
│   ├── test_form_parsing.py    # Lark form field extraction
│   ├── test_workflow_routing.py # Approval code → workflow dispatch
│   ├── test_resource_provision.py # Multi-cloud resource provisioning
│   ├── test_pipeline_setup.py  # CI/CD pipeline creation
│   ├── test_domain_change.py   # Domain replacement workflow
│   └── test_scheduler.py       # Expiry alerts + cost reports
└── docs/
    └── workflow-diagrams.md    # Mermaid flow diagrams
```
