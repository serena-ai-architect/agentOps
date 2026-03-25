# CLAUDE.md — AgentOps

## Project Context
AgentOps is an AI-native DevOps platform that replaces manual operations with autonomous agents.
Core idea: approval-driven workflows trigger multi-cloud resource provisioning, CI/CD pipeline creation, and DNS/SSL management — zero human intervention after approval.

## Key Commands
- `pip install -e .` — Install dependencies
- `python main.py` — Start dev server (auto-reload)
- `uvicorn main:app --host 0.0.0.0 --port 8000` — Production
- `pytest` — Run tests
- `ruff check .` — Lint
- `docker build -t agentops . && docker run -p 8000:8000 --env-file .env agentops` — Docker

## Conventions
- Python 3.12+, type hints everywhere
- Async-first (FastAPI + SQLAlchemy async)
- English for code/comments/logs, Chinese for user-facing notifications (Lark)
- All cloud API wrappers in cloud/{provider}/ directory
- All workflows in workflows/ directory
- Pydantic settings with `AGENTOPS_` env prefix (see config.py)

## Session Management

### Start of Session
1. Read `claude-progress.txt` before doing anything else.
2. Read `AGENTS.md` to understand project structure and boundaries.
3. Confirm understanding of current state before proceeding with any task.

### End of Session
Before the session ends, update `claude-progress.txt` with:
- **Last Updated**: current date and time
- **Current State**: brief summary of where the project stands
- **What Was Completed**: concrete changes made in this session
- **What Is Blocked**: issues or decisions needing human input
- **Next Steps**: prioritized list for next session

### Rules
- Keep `claude-progress.txt` concise — under 50 lines.
- If a major architectural decision was made, also update `AGENTS.md`.
- Never delete progress info without writing the replacement first.
