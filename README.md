# fun-ai-agent-plane

智能体运行平面（plane），负责任务排队、并发执行与事件流输出。

## 技术栈

- Python 3.8+
- FastAPI
- asyncio worker pool + queue

## 本地运行

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

## 三层架构

- 结构层：`智能体 -> 工作流 -> 技能`
- 可配层：工作流级参数（当前主要是 `model_profile`）
- 能力层：技能定义与 `prompt_template`

## 核心接口

- `POST /v1/tasks`：创建任务并入队
- `GET /v1/tasks/{task_id}`：查询任务状态/结果
- `POST /v1/tasks/{task_id}/cancel`：取消任务
- `GET /v1/tasks/{task_id}/events`：SSE 事件流
- `GET /v1/runtime`：查看当前加载的智能体/工作流/技能/mcp/模型配置快照

`POST /v1/tasks` 请求字段：

- `tenant_id`
- `agent_id`
- `workflow_id`（可选，不传则使用智能体默认工作流）
- `prompt`
- `skill_prompt_override`（可选，覆盖当前技能默认提示词）
- `idempotency_key`（可选）

## 并发控制

- 全局并发上限：`PLANE_MAX_GLOBAL_CONCURRENCY`
- 租户并发上限：`PLANE_MAX_TENANT_CONCURRENCY`
- 智能体并发上限：`PLANE_MAX_AGENT_CONCURRENCY`
- 队列上限与背压：`PLANE_QUEUE_MAX_SIZE`（满载时返回 `429`）

## 运行时配置结构

- `agents/*.json`：智能体与工作流配置
- `skills/*.json`：技能配置（支持 `prompt_template`）
- `mcp/*.json`：MCP 服务配置
- `models/*.json`：共享模型配置

相关环境变量：

- `PLANE_AGENT_DIR`（默认 `./agents`）
- `PLANE_SKILLS_DIR`（默认 `./skills`）
- `PLANE_MCP_DIR`（默认 `./mcp`）
- `PLANE_MODEL_DIR`（默认 `./models`）
- `PLANE_ENFORCE_AGENT_REGISTRY`（默认 `false`）
- `PLANE_LLM_EXECUTION_MODE`（`off`/`mock`，其他值按模型配置 provider 执行）

说明：

- 智能体级 `prompt` 配置被禁止（开发阶段约束）
- 技能级 `prompt_template` 允许配置
- 当前支持模型提供商：`mock`、`openai-compatible`

## 最小配置示例

`agents/demo.json`

```json
{
  "agent_id": "demo-agent",
  "display_name": "示例智能体",
  "default_workflow_id": "summarize",
  "workflows": [
    {
      "workflow_id": "summarize",
      "name": "文本摘要",
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
  "description": "基础文本摘要能力",
  "prompt_template": "请将输入内容整理为结构化摘要。",
  "version": "1.0.0"
}
```
