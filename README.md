# fun-ai-agent-plane

Agent runtime plane for task execution, streaming output, and concurrency control.

## Tech stack

- Python 3.8+
- FastAPI
- asyncio worker pool + queue

## Run locally

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

## Core APIs

- `POST /v1/tasks`: create task and enqueue.
- `GET /v1/tasks/{task_id}`: get task status/result.
- `POST /v1/tasks/{task_id}/cancel`: request cancellation.
- `GET /v1/tasks/{task_id}/events`: stream events with SSE.
- `GET /v1/runtime`: show loaded agent/skills/mcp IDs.

## Concurrency controls

- Global concurrency limit: `PLANE_MAX_GLOBAL_CONCURRENCY`
- Per-tenant limit: `PLANE_MAX_TENANT_CONCURRENCY`
- Per-agent limit: `PLANE_MAX_AGENT_CONCURRENCY`
- Queue cap and backpressure: `PLANE_QUEUE_MAX_SIZE` with HTTP `429`.

## Runtime config structure

- `agents/*.json`: agent definitions (agent ID, bound skills, bound mcp servers)
- `skills/*.json`: skill definitions
- `mcp/*.json`: mcp server definitions

Related env vars:

- `PLANE_AGENT_DIR` (default `./agents`)
- `PLANE_SKILLS_DIR` (default `./skills`)
- `PLANE_MCP_DIR` (default `./mcp`)
- `PLANE_ENFORCE_AGENT_REGISTRY` (default `false`)
