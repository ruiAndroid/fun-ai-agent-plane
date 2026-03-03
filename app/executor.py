import asyncio
import json
import re
from typing import Dict, List, Optional, Tuple

from .config import Settings
from .llm import LLMService
from .runtime import AgentRuntimeRegistry, RuntimeBundle, RuntimeStepBundle
from .store import TaskRecord, TaskStore


class QueueAtCapacityError(Exception):
    pass


class TaskCanceledError(Exception):
    pass


class TaskExecutor:
    def __init__(
        self,
        settings: Settings,
        store: TaskStore,
        runtime_registry: AgentRuntimeRegistry,
        llm_service: LLMService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runtime_registry = runtime_registry
        self.llm_service = llm_service
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
            raise RuntimeError("Executor queue is not initialized.")
        try:
            self.queue.put_nowait(task_id)
            return self.queue.qsize()
        except asyncio.QueueFull as exc:
            raise QueueAtCapacityError("Task queue is full.") from exc

    def queue_size(self) -> int:
        if self.queue is None:
            return 0
        return self.queue.qsize()

    async def _get_tenant_limiter(self, tenant_id: str) -> asyncio.Semaphore:
        if self._tenant_lock is None:
            raise RuntimeError("Tenant limiter lock is not initialized.")
        async with self._tenant_lock:
            limiter = self._tenant_limiters.get(tenant_id)
            if limiter is None:
                limiter = asyncio.Semaphore(self.settings.max_tenant_concurrency)
                self._tenant_limiters[tenant_id] = limiter
            return limiter

    async def _get_agent_limiter(self, agent_id: str) -> asyncio.Semaphore:
        if self._agent_lock is None:
            raise RuntimeError("Agent limiter lock is not initialized.")
        async with self._agent_lock:
            limiter = self._agent_limiters.get(agent_id)
            if limiter is None:
                limiter = asyncio.Semaphore(self.settings.max_agent_concurrency)
                self._agent_limiters[agent_id] = limiter
            return limiter

    async def _worker_loop(self, worker_index: int) -> None:
        if self.queue is None:
            raise RuntimeError("Executor queue is not initialized.")
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
            raise RuntimeError("Global semaphore is not initialized.")

        async with self.global_semaphore:
            async with tenant_limiter:
                async with agent_limiter:
                    await self._execute_task(task_record, worker_index)

    async def _execute_task(self, task_record: TaskRecord, worker_index: int) -> None:
        running = await self.store.set_running(task_record.task_id)
        if running is None:
            return
        await self.store.publish(running.task_id, "task_running", running.to_view().to_dict())

        runtime = self.runtime_registry.resolve(running.agent_id, running.workflow_id)
        await self.store.publish(
            running.task_id,
            "runtime_resolved",
            {
                "task_id": running.task_id,
                "agent_id": runtime.agent.agent_id,
                "workflow_id": runtime.workflow.workflow_id,
                "steps": [
                    {
                        "step_id": item.step.step_id,
                        "step_name": item.step.name,
                        "skill_id": item.step.skill_id,
                    }
                    for item in runtime.steps
                ],
                "mcp_servers": [server.server_id for server in runtime.mcp_servers],
                "primary_model": runtime.primary_model.model_id if runtime.primary_model else None,
                "worker": worker_index,
            },
        )

        try:
            full_text = await self._run_workflow(running, runtime)
        except TaskCanceledError:
            canceled = await self.store.set_canceled(running.task_id)
            if canceled:
                await self.store.publish(
                    canceled.task_id, "task_canceled", canceled.to_view().to_dict()
                )
            return

        for chunk in full_text:
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

    async def _run_workflow(self, task_record: TaskRecord, runtime: RuntimeBundle) -> str:
        step_input = self._initial_step_input(task_record)
        step_outputs: List[Tuple[RuntimeStepBundle, str]] = []
        total_steps = len(runtime.steps)

        for index, runtime_step in enumerate(runtime.steps, start=1):
            if await self.store.is_cancel_requested(task_record.task_id):
                raise TaskCanceledError("Task canceled before workflow completion.")

            await self.store.publish(
                task_record.task_id,
                "step_started",
                {
                    "task_id": task_record.task_id,
                    "step_index": index,
                    "step_total": total_steps,
                    "step_id": runtime_step.step.step_id,
                    "step_name": runtime_step.step.name,
                    "skill_id": runtime_step.skill.skill_id,
                    "input_chars": len(step_input),
                    "input_preview": self._preview(step_input),
                },
            )

            step_output = (
                await self._run_step(task_record, runtime, runtime_step, step_input)
            ).strip()
            step_outputs.append((runtime_step, step_output))
            step_input = step_output

            await self.store.publish(
                task_record.task_id,
                "step_completed",
                {
                    "task_id": task_record.task_id,
                    "step_index": index,
                    "step_total": total_steps,
                    "step_id": runtime_step.step.step_id,
                    "step_name": runtime_step.step.name,
                    "skill_id": runtime_step.skill.skill_id,
                    "output_chars": len(step_output),
                    "output": step_output,
                    "output_preview": self._preview(step_output),
                },
            )

        return self._format_workflow_output(runtime, step_outputs)

    def _format_workflow_output(
        self, runtime: RuntimeBundle, step_outputs: List[Tuple[RuntimeStepBundle, str]]
    ) -> str:
        if not step_outputs:
            return f"[{runtime.agent.display_name}] Workflow produced empty output."

        lines: List[str] = []
        lines.append(f"[{runtime.agent.display_name}] Storyboard Pipeline Result")
        lines.append(f"Workflow: {runtime.workflow.workflow_id}")
        lines.append(f"Steps: {len(step_outputs)}")
        lines.append("")
        lines.append("Execution Trace:")
        for index, (runtime_step, output) in enumerate(step_outputs, start=1):
            lines.append(
                f"{index}. {runtime_step.step.step_id} ({runtime_step.skill.skill_id}) "
                f"output_chars={len(output)}"
            )

        lines.append("")
        for index, (runtime_step, output) in enumerate(step_outputs, start=1):
            lines.append(
                f"Step {index}: {runtime_step.step.name} [{runtime_step.skill.skill_id}]"
            )
            lines.append(output or "(empty output)")
            lines.append("")

        return "\n".join(lines).strip()

    async def _run_step(
        self,
        task_record: TaskRecord,
        runtime: RuntimeBundle,
        runtime_step: RuntimeStepBundle,
        step_input: str,
    ) -> str:
        skill_id = runtime_step.skill.skill_id
        if skill_id == "novel-intake-parse":
            return self._build_novel_intake_summary(task_record, step_input, runtime.agent.display_name)
        if skill_id == "storyboard-episode-split":
            return self._build_storyboard_episode_plan(step_input, runtime.agent.display_name)
        if skill_id == "storyboard-extract-roles":
            return self._build_storyboard_role_extract(step_input, runtime.agent.display_name)

        llm_text = await self._try_generate_by_model(
            task_record=task_record,
            runtime=runtime,
            runtime_step=runtime_step,
            step_input=step_input,
        )
        if llm_text is not None:
            return llm_text

        reversed_words = list(reversed(step_input.split()))
        if not reversed_words:
            reversed_words = ["(empty input)"]
        return (
            f"[{runtime.agent.display_name}] "
            f"step={runtime_step.step.step_id}, skill={runtime_step.skill.skill_id}, "
            f"fallback={' '.join(reversed_words)}"
        )

    async def _try_generate_by_model(
        self,
        task_record: TaskRecord,
        runtime: RuntimeBundle,
        runtime_step: RuntimeStepBundle,
        step_input: str,
    ) -> Optional[str]:
        if runtime.primary_model is None:
            return None

        skill_prompt = self._resolve_skill_prompt(
            task_record=task_record,
            skill_id=runtime_step.skill.skill_id,
            default_prompt=runtime_step.skill.prompt_template,
        )
        response = await self.llm_service.complete(
            runtime=runtime,
            prompt=step_input,
            skill_prompt=skill_prompt,
        )
        return (
            f"[{runtime.agent.display_name}] step={runtime_step.step.step_id} "
            f"skill={runtime_step.skill.skill_id}\n{response.text}"
        )

    def _resolve_skill_prompt(
        self, task_record: TaskRecord, skill_id: str, default_prompt: str
    ) -> str:
        if task_record.skill_prompt_overrides:
            override = task_record.skill_prompt_overrides.get(skill_id)
            if override and override.strip():
                return override.strip()

        # Backward compatibility: one global override, optionally scoped by skill_id.
        if task_record.skill_prompt_override and task_record.skill_prompt_override.strip():
            if task_record.skill_id is None or task_record.skill_id == skill_id:
                return task_record.skill_prompt_override.strip()

        return default_prompt

    def _preview(self, text: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: max(0, limit - 3)].rstrip() + "..."

    def _initial_step_input(self, task_record: TaskRecord) -> str:
        if task_record.input_payload:
            return json.dumps(task_record.input_payload, ensure_ascii=False, indent=2)
        return task_record.prompt

    def _build_novel_intake_summary(
        self, task_record: TaskRecord, step_input: str, display_name: str
    ) -> str:
        payload = task_record.input_payload or {}
        novel_content = str(payload.get("novel_content", "")).strip()
        target_audience = str(payload.get("target_audience", "")).strip()
        expected_episode_count = payload.get("expected_episode_count")

        if not novel_content:
            novel_content = step_input.strip()
        if not target_audience:
            target_audience = "未指定"

        episode_count_text = "未指定"
        if isinstance(expected_episode_count, int):
            episode_count_text = str(expected_episode_count)
        else:
            raw_episode = str(expected_episode_count or "").strip()
            if raw_episode:
                episode_count_text = raw_episode

        synopsis = self._unit_summary(novel_content, limit=240) if novel_content else "未提供小说内容"

        lines = [
            f"[{display_name}] Novel Intake",
            f"受众={target_audience}",
            f"期望集数={episode_count_text}",
            f"小说内容长度={len(novel_content)}",
            "",
            "标准化输入摘要:",
            synopsis,
            "",
            "下一步建议:",
            "1. 角色抽取与关系网",
            "2. 主线/支线冲突拆解",
            "3. 按期望集数做分集大纲",
        ]
        return "\n".join(lines).strip()

    def _build_storyboard_role_extract(self, prompt: str, display_name: str) -> str:
        normalized = re.sub(r"[，。！？、；：,.!?;:()\[\]{}<>\"'`~@#$%^&*_+=/\\|-]+", " ", prompt)
        tokens = [token.strip() for token in normalized.split() if token.strip()]
        candidate_counts: Dict[str, int] = {}
        for token in tokens:
            if len(token) < 2 or len(token) > 20:
                continue
            if token.lower() in {"int", "ext", "scene", "act", "ep", "step", "workflow"}:
                continue
            candidate_counts[token] = candidate_counts.get(token, 0) + 1
        ranked = sorted(candidate_counts.items(), key=lambda item: (-item[1], item[0]))
        top_roles = [name for name, _ in ranked[:12]]

        if not top_roles:
            return (
                f"[{display_name}] Role Extraction\n"
                "No obvious role names were identified. Please provide richer script text."
            )

        lines = [f"[{display_name}] Role Extraction", f"Role count={len(top_roles)}", ""]
        for idx, role_name in enumerate(top_roles, start=1):
            lines.append(f"{idx}. {role_name}")
        return "\n".join(lines).strip()

    def _build_storyboard_episode_plan(self, prompt: str, display_name: str) -> str:
        units = self._split_script_units(prompt)
        if not units:
            return (
                f"[{display_name}] Episode Split\n"
                "No valid script units found. Please provide a script with scenes/paragraphs."
            )

        episode_count = self._suggest_episode_count(len(units))
        episodes = self._allocate_units_to_episodes(units, episode_count)

        lines: List[str] = []
        lines.append(f"[{display_name}] Episode Split")
        lines.append(f"Script units={len(units)}")
        lines.append(f"Suggested episodes={len(episodes)}")
        lines.append("")

        for index, episode_units in enumerate(episodes, start=1):
            lines.append(f"Episode {index:02d}")
            lines.append(f"- Scene count: {len(episode_units)}")
            lines.append(f"- Hook: {self._unit_summary(episode_units[0])}")
            lines.append(
                f"- Core conflict: {self._unit_summary(episode_units[len(episode_units) // 2])}"
            )
            lines.append(f"- Cliffhanger: {self._unit_summary(episode_units[-1])}")
            lines.append("- Scene breakdown:")
            for scene_idx, scene in enumerate(episode_units, start=1):
                lines.append(f"  {scene_idx}. {self._unit_summary(scene, limit=90)}")
            lines.append("")

        lines.append("Split strategy: scene header detection + balanced allocation")
        return "\n".join(lines).strip()

    def _split_script_units(self, prompt: str) -> List[str]:
        lines = [line.strip() for line in prompt.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return []

        header_pattern = re.compile(
            r"^(INT\.|EXT\.|SCENE\s+\d+|ACT\s+\d+|EP\s*\d+|第[0-9一二三四五六七八九十百零]+[集幕场])",
            re.IGNORECASE,
        )

        units: List[str] = []
        current: List[str] = []
        for line in lines:
            if header_pattern.match(line) and current:
                units.append(" ".join(current).strip())
                current = [line]
            else:
                current.append(line)

        if current:
            units.append(" ".join(current).strip())

        if len(units) <= 1:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", prompt) if part.strip()]
            if len(paragraphs) > 1:
                return paragraphs

        return units

    def _suggest_episode_count(self, unit_count: int) -> int:
        if unit_count <= 4:
            return 1
        if unit_count <= 10:
            return 2
        if unit_count <= 18:
            return 3
        if unit_count <= 28:
            return 4
        return min(8, max(5, unit_count // 6))

    def _allocate_units_to_episodes(self, units: List[str], episode_count: int) -> List[List[str]]:
        episode_count = max(1, min(episode_count, len(units)))
        base_size = len(units) // episode_count
        remainder = len(units) % episode_count

        episodes: List[List[str]] = []
        cursor = 0
        for idx in range(episode_count):
            take = base_size + (1 if idx < remainder else 0)
            episodes.append(units[cursor : cursor + take])
            cursor += take
        return episodes

    def _unit_summary(self, text: str, limit: int = 64) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: max(0, limit - 3)].rstrip() + "..."
