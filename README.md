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

## LLM gateway

When `PLANE_LLM_EXECUTION_MODE=on`, workflows call the unified gateway using:

- `POST ${GATEWAY_BASE_URL}/messages`
- header `Authorization: Bearer ${GATEWAY_TOKEN}`
- header `anthropic-version: ${GATEWAY_ANTHROPIC_VERSION}` (default `2023-06-01`)

Runtime config is dynamically loaded from `.env.production` by default.
You can override the path with `PLANE_ENV_FILE=/path/to/env-file`.

`workflow.model_profile` is treated as the gateway `model` id. If no local model profile file matches,
the runtime auto-falls back to gateway mode with that model id.

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
