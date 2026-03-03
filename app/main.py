import asyncio
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse

from .config import settings
from .executor import QueueAtCapacityError, TaskExecutor
from .llm import LLMService
from .models import CreateTaskRequest, TaskStatus
from .runtime import AgentRuntimeRegistry
from .store import TaskStore

app = FastAPI(
    title="fun-ai-agent-plane",
    version="0.1.0",
    description="Concurrent agent runtime plane with queue, worker pool, and SSE.",
)
store = TaskStore()
runtime_registry = AgentRuntimeRegistry(
    agent_dir=settings.agent_dir,
    skills_dir=settings.skills_dir,
    mcp_dir=settings.mcp_dir,
    model_dir=settings.model_dir,
    enforce_agent_registry=settings.enforce_agent_registry,
)
llm_service = LLMService(
    execution_mode=settings.llm_execution_mode,
    gateway_base_url=settings.gateway_base_url,
    gateway_token=settings.gateway_token,
    gateway_anthropic_version=settings.gateway_anthropic_version,
)
executor = TaskExecutor(
    settings=settings,
    store=store,
    runtime_registry=runtime_registry,
    llm_service=llm_service,
)


def _sse_message(data: str) -> str:
    return f"data: {data}\n\n"


@app.on_event("startup")
async def startup() -> None:
    runtime_registry.reload()
    await executor.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await executor.stop()


@app.get("/health")
async def health() -> dict:
    snapshot = runtime_registry.snapshot()
    return {
        "status": "ok",
        "queue_size": executor.queue_size(),
        "workers": settings.worker_count,
        "global_limit": settings.max_global_concurrency,
        "runtime": {
            "agents": len(snapshot.agents),
            "skills": len(snapshot.skills),
            "mcp_servers": len(snapshot.mcp_servers),
            "model_profiles": len(snapshot.model_profiles),
        },
    }


@app.get("/v1/runtime")
async def get_runtime_snapshot() -> dict:
    snapshot = runtime_registry.snapshot()
    return {
        "agents": {
            agent_id: {
                "display_name": agent.display_name,
                "default_workflow_id": agent.default_workflow_id,
                "workflows": {
                    workflow_id: {
                        "name": workflow.name,
                        "steps": [
                            {
                                "step_id": step.step_id,
                                "name": step.name,
                                "skill_id": step.skill_id,
                                "description": step.description,
                                "config": step.config,
                            }
                            for step in workflow.steps
                        ],
                        "model_profile": workflow.model_profile,
                        "description": workflow.description,
                        "config": workflow.config,
                    }
                    for workflow_id, workflow in sorted(agent.workflows.items())
                },
            }
            for agent_id, agent in sorted(snapshot.agents.items())
        },
        "skills": sorted(snapshot.skills.keys()),
        "mcp_servers": sorted(snapshot.mcp_servers.keys()),
        "model_profiles": sorted(snapshot.model_profiles.keys()),
        "enforce_agent_registry": settings.enforce_agent_registry,
        "llm_execution_mode": settings.llm_execution_mode,
    }


@app.post("/v1/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_task(request: CreateTaskRequest) -> dict:
    task_record, created = await store.create_or_get_task(
        tenant_id=request.tenant_id,
        agent_id=request.agent_id,
        workflow_id=request.workflow_id,
        skill_id=request.skill_id,
        input_payload=request.input_payload,
        prompt=request.prompt,
        skill_prompt_override=request.skill_prompt_override,
        skill_prompt_overrides=request.skill_prompt_overrides,
        idempotency_key=request.idempotency_key,
    )
    if not created:
        return task_record.to_view().to_dict()

    try:
        position = await executor.enqueue(task_record.task_id)
    except QueueAtCapacityError:
        await store.delete_task(task_record.task_id)
        raise HTTPException(status_code=429, detail="Runtime queue is full. Retry later.")

    await store.publish(task_record.task_id, "task_queued", task_record.to_view(position).to_dict())
    return task_record.to_view(position).to_dict()


@app.get("/v1/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    task_record = await store.get_task(task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task_record.to_view().to_dict()


@app.post("/v1/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    task_record = await store.request_cancel(task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found.")
    await store.publish(
        task_record.task_id, "task_cancel_requested", task_record.to_view().to_dict()
    )
    return task_record.to_view().to_dict()


@app.get("/v1/tasks/{task_id}/events")
async def stream_task_events(task_id: str) -> StreamingResponse:
    task_record = await store.get_task(task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found.")

    subscriber = await store.subscribe(task_id)
    if subscriber is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    async def event_generator() -> AsyncIterator[str]:
        try:
            snapshot = await store.get_task(task_id)
            if snapshot:
                yield _sse_message(
                    '{"event_type":"snapshot","payload":'
                    + snapshot.to_view().to_json()
                    + "}"
                )

            while True:
                try:
                    payload = await asyncio.wait_for(
                        subscriber.get(), timeout=settings.heartbeat_seconds
                    )
                    yield _sse_message(payload)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

                current = await store.get_task(task_id)
                if current and current.status in (
                    TaskStatus.SUCCEEDED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELED,
                ):
                    # Drain any pending events so client receives terminal state before close.
                    while not subscriber.empty():
                        yield _sse_message(subscriber.get_nowait())
                    break
        finally:
            await store.unsubscribe(task_id, subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
