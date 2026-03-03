# fun-ai-agent-plane

Runtime plane for queued concurrent execution and SSE event streaming.

## Tech stack

- Python 3.8+
- FastAPI
- asyncio worker queue/pool

## Run locally

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

## Core APIs

- `POST /v1/tasks`
- `GET /v1/tasks/{task_id}`
- `POST /v1/tasks/{task_id}/cancel`
- `GET /v1/tasks/{task_id}/events` (SSE)
- `GET /v1/runtime`

## Create task payload

- `tenant_id`
- `agent_id`
- `workflow_id` (optional)
- `skill_id` (optional, backward compatibility)
- `skill_prompt_override` (optional, backward compatibility)
- `skill_prompt_overrides` (optional, per-skill map)
- `prompt`
- `idempotency_key` (optional)

## Storyboard flow

`dreamworks-storyboard` default workflow is `storyboard-pipeline`, with two serial steps:

1. `storyboard-episode-split`
2. `storyboard-extract-roles`

The second step uses the previous step output as its input.

## Streaming events

Typical events:

- `task_queued`
- `task_running`
- `runtime_resolved`
- `step_started`
- `step_completed`
- `token`
- `task_succeeded` / `task_failed` / `task_canceled`

`token` events stream the final rendered output incrementally.
