from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return "task_" + uuid4().hex


class ModelCompat(BaseModel):
    def to_dict(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def to_json(self) -> str:
        if hasattr(self, "model_dump_json"):
            return self.model_dump_json()
        return self.json()


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class CreateTaskRequest(ModelCompat):
    tenant_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    workflow_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    skill_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    skill_prompt_override: Optional[str] = Field(default=None, max_length=12000)
    skill_prompt_overrides: Optional[Dict[str, str]] = None
    input_payload: Optional[Dict[str, Any]] = None
    prompt: str = Field(min_length=1, max_length=6000)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class TaskView(ModelCompat):
    task_id: str
    tenant_id: str
    agent_id: str
    workflow_id: Optional[str]
    skill_id: Optional[str]
    status: TaskStatus
    output: str
    error: Optional[str]
    queue_position: Optional[int]
    created_at: str
    updated_at: str


class TaskEvent(ModelCompat):
    event_type: str
    payload: Dict[str, Any]
    timestamp: str = Field(default_factory=utc_now_iso)
