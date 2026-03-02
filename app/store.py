import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .models import TaskEvent, TaskStatus, TaskView, new_task_id, utc_now_iso


@dataclass
class TaskRecord:
    task_id: str
    tenant_id: str
    agent_id: str
    prompt: str
    status: TaskStatus
    output_chunks: List[str] = field(default_factory=list)
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
    cancel_requested: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_view(self, queue_position: Optional[int] = None) -> TaskView:
        return TaskView(
            task_id=self.task_id,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            status=self.status,
            output="".join(self.output_chunks),
            error=self.error,
            queue_position=queue_position,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class TaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}
        self._idempotency_index: Dict[str, str] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def create_or_get_task(
        self,
        tenant_id: str,
        agent_id: str,
        prompt: str,
        idempotency_key: Optional[str],
    ) -> Tuple[TaskRecord, bool]:
        async with self._lock:
            if idempotency_key:
                existing_task_id = self._idempotency_index.get(idempotency_key)
                if existing_task_id:
                    existing = self._tasks.get(existing_task_id)
                    if existing:
                        return existing, False

            task_id = new_task_id()
            created = TaskRecord(
                task_id=task_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                prompt=prompt,
                status=TaskStatus.QUEUED,
                idempotency_key=idempotency_key,
            )
            self._tasks[task_id] = created
            if idempotency_key:
                self._idempotency_index[idempotency_key] = task_id
            return created, True

    async def delete_task(self, task_id: str) -> None:
        async with self._lock:
            task = self._tasks.pop(task_id, None)
            self._subscribers.pop(task_id, None)
            if task and task.idempotency_key:
                self._idempotency_index.pop(task.idempotency_key, None)

    async def get_task(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def set_running(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = TaskStatus.RUNNING
            task.updated_at = utc_now_iso()
            return task

    async def append_chunk(self, task_id: str, chunk: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.output_chunks.append(chunk)
            task.updated_at = utc_now_iso()
            return task

    async def set_succeeded(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = TaskStatus.SUCCEEDED
            task.error = None
            task.updated_at = utc_now_iso()
            return task

    async def set_failed(self, task_id: str, error: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = TaskStatus.FAILED
            task.error = error
            task.updated_at = utc_now_iso()
            return task

    async def set_canceled(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = TaskStatus.CANCELED
            task.error = "Task canceled by client."
            task.updated_at = utc_now_iso()
            return task

    async def request_cancel(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.cancel_requested = True
            task.updated_at = utc_now_iso()
            return task

    async def is_cancel_requested(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and task.cancel_requested)

    async def subscribe(self, task_id: str) -> Optional[asyncio.Queue]:
        queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            if task_id not in self._tasks:
                return None
            self._subscribers.setdefault(task_id, set()).add(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            task_subscribers = self._subscribers.get(task_id)
            if not task_subscribers:
                return
            task_subscribers.discard(queue)
            if not task_subscribers:
                self._subscribers.pop(task_id, None)

    async def publish(self, task_id: str, event_type: str, payload: Dict) -> None:
        message = TaskEvent(event_type=event_type, payload=payload).to_json()
        async with self._lock:
            subscribers = list(self._subscribers.get(task_id, set()))

        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue

