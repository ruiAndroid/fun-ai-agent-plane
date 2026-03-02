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

## Architecture layers

- Structure layer: `Agent -> Workflows -> Skills`
- Config layer: workflow-level parameters (currently `model_profile` only)
- Capability layer: skill definitions and `prompt_template`

## Core APIs

- `POST /v1/tasks`: create task and enqueue.
- `GET /v1/tasks/{task_id}`: get task status/result.
- `POST /v1/tasks/{task_id}/cancel`: request cancellation.
- `GET /v1/tasks/{task_id}/events`: stream events with SSE.
- `GET /v1/runtime`: show loaded runtime snapshot (agents/workflows/skills/mcp/models).

`POST /v1/tasks` request fields:

- `tenant_id`
- `agent_id`
- `workflow_id` (optional, uses agent default workflow if omitted)
- `prompt`
- `skill_prompt_override` (optional, runtime override for selected skill prompt template)
- `idempotency_key` (optional)

## Concurrency controls

- Global concurrency limit: `PLANE_MAX_GLOBAL_CONCURRENCY`
- Per-tenant limit: `PLANE_MAX_TENANT_CONCURRENCY`
- Per-agent limit: `PLANE_MAX_AGENT_CONCURRENCY`
- Queue cap and backpressure: `PLANE_QUEUE_MAX_SIZE` with HTTP `429`.

## Runtime config structure

- `agents/*.json`: agent + workflows config
- `skills/*.json`: skill config (`prompt_template` supported)
- `mcp/*.json`: mcp server config
- `models/*.json`: shared model profiles

Related env vars:

- `PLANE_AGENT_DIR` (default `./agents`)
- `PLANE_SKILLS_DIR` (default `./skills`)
- `PLANE_MCP_DIR` (default `./mcp`)
- `PLANE_MODEL_DIR` (default `./models`)
- `PLANE_ENFORCE_AGENT_REGISTRY` (default `false`)
- `PLANE_LLM_EXECUTION_MODE` (`off`/`mock`, otherwise use profile provider, default `off`)

Notes:

- Agent-level `prompt` is intentionally forbidden in config.
- Skill-level `prompt_template` is allowed.
- Supported model providers: `mock`, `openai-compatible`.

## Minimal config example

`agents/demo.json`

```json
{
  "agent_id": "demo-agent",
  "display_name": "Demo Agent",
  "default_workflow_id": "summarize",
  "workflows": [
    {
      "workflow_id": "summarize",
      "name": "Summarize",
      "skill_id": "summarize-text",
      "model_profile": "mock-default"
    }
  ],
  "mcp_servers": [],
  "metadata": {
    "owner": "dev"
  }
}
```

`skills/summarize-text.json`

```json
{
  "skill_id": "summarize-text",
  "description": "Basic summarization capability.",
  "prompt_template": "You summarize user input into concise bullet points with clear structure.",
  "version": "1.0.0"
}
```
