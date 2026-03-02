import asyncio
from typing import Dict, List, Optional

from .config import Settings
from .store import TaskRecord, TaskStore


class QueueAtCapacityError(Exception):
    pass


class TaskExecutor:
    def __init__(self, settings: Settings, store: TaskStore) -> None:
        self.settings = settings
        self.store = store
        self.queue: Optional[asyncio.Queue] = None
        self.global_semaphore: Optional[asyncio.Semaphore] = None
        self._tenant_limiters: Dict[str, asyncio.Semaphore] = {}
        self._agent_limiters: Dict[str, asyncio.Semaphore] = {}
        self._tenant_lock: Optional[asyncio.Lock] = None
        self._agent_lock: Optional[asyncio.Lock] = None
        self._workers: List[asyncio.Task] = []

    async def start(self) -> None:
        if self._workers:
            return
        self.queue = asyncio.Queue(maxsize=self.settings.queue_max_size)
        self.global_semaphore = asyncio.Semaphore(self.settings.max_global_concurrency)
        self._tenant_lock = asyncio.Lock()
        self._agent_lock = asyncio.Lock()
        self._tenant_limiters.clear()
        self._agent_limiters.clear()
        for index in range(self.settings.worker_count):
            self._workers.append(asyncio.create_task(self._worker_loop(index)))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, task_id: str) -> int:
        if self.queue is None:
            raise RuntimeError("Executor queue not initialized.")
        try:
            self.queue.put_nowait(task_id)
            return self.queue.qsize()
        except asyncio.QueueFull as exc:
            raise QueueAtCapacityError("Task queue is full") from exc

    def queue_size(self) -> int:
        if self.queue is None:
            return 0
        return self.queue.qsize()

    async def _get_tenant_limiter(self, tenant_id: str) -> asyncio.Semaphore:
        if self._tenant_lock is None:
            raise RuntimeError("Tenant limiter lock not initialized.")
        async with self._tenant_lock:
            limiter = self._tenant_limiters.get(tenant_id)
            if limiter is None:
                limiter = asyncio.Semaphore(self.settings.max_tenant_concurrency)
                self._tenant_limiters[tenant_id] = limiter
            return limiter

    async def _get_agent_limiter(self, agent_id: str) -> asyncio.Semaphore:
        if self._agent_lock is None:
            raise RuntimeError("Agent limiter lock not initialized.")
        async with self._agent_lock:
            limiter = self._agent_limiters.get(agent_id)
            if limiter is None:
                limiter = asyncio.Semaphore(self.settings.max_agent_concurrency)
                self._agent_limiters[agent_id] = limiter
            return limiter

    async def _worker_loop(self, worker_index: int) -> None:
        if self.queue is None:
            raise RuntimeError("Executor queue not initialized.")
        while True:
            task_id = await self.queue.get()
            try:
                await self._run_task(task_id, worker_index)
            except Exception as exc:
                await self.store.set_failed(task_id, str(exc))
                failed = await self.store.get_task(task_id)
                if failed:
                    await self.store.publish(task_id, "task_failed", failed.to_view().to_dict())
            finally:
                self.queue.task_done()

    async def _run_task(self, task_id: str, worker_index: int) -> None:
        task_record = await self.store.get_task(task_id)
        if task_record is None:
            return

        tenant_limiter = await self._get_tenant_limiter(task_record.tenant_id)
        agent_limiter = await self._get_agent_limiter(task_record.agent_id)
        if self.global_semaphore is None:
            raise RuntimeError("Global semaphore not initialized.")

        async with self.global_semaphore:
            async with tenant_limiter:
                async with agent_limiter:
                    await self._execute_task(task_record, worker_index)

    async def _execute_task(self, task_record: TaskRecord, worker_index: int) -> None:
        running = await self.store.set_running(task_record.task_id)
        if running is None:
            return
        await self.store.publish(running.task_id, "task_running", running.to_view().to_dict())

        chunks = self._build_chunks(running)
        for chunk in chunks:
            if await self.store.is_cancel_requested(running.task_id):
                canceled = await self.store.set_canceled(running.task_id)
                if canceled:
                    await self.store.publish(
                        canceled.task_id, "task_canceled", canceled.to_view().to_dict()
                    )
                return

            await asyncio.sleep(self.settings.token_delay_ms / 1000.0)
            updated = await self.store.append_chunk(running.task_id, chunk)
            if updated is None:
                return
            await self.store.publish(
                updated.task_id,
                "token",
                {"task_id": updated.task_id, "chunk": chunk, "worker": worker_index},
            )

        succeeded = await self.store.set_succeeded(running.task_id)
        if succeeded:
            await self.store.publish(
                succeeded.task_id, "task_succeeded", succeeded.to_view().to_dict()
            )

    def _build_chunks(self, task_record: TaskRecord) -> List[str]:
        reversed_words = list(reversed(task_record.prompt.split()))
        if not reversed_words:
            reversed_words = ["(empty)"]

        output = [
            "[",
            task_record.agent_id,
            "] ",
            "processed prompt: ",
            " ".join(reversed_words),
            ". ",
            "concurrency-safe run completed.",
        ]
        text = "".join(output)
        return [char for char in text]
