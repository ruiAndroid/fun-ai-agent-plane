# fun-ai-agent-plane

Execution plane service for reconciling claw instance commands.

## Tech Stack

- Java 17+
- Spring Boot 4.0.3
- Spring WebMVC + Validation + Actuator

## Run

```bash
mvn spring-boot:run
```

Default port: `8090`

## Current Scope

- `GET /internal/v1/health`
- `POST /internal/v1/reconcile`
- `GET /internal/v1/tasks`

Current implementation is an in-memory executor skeleton for bootstrap.

## Update Script

Use `update-agent-plane.sh` for one-command update on server:

```bash
chmod +x /opt/fun-ai-agent-plane/update-agent-plane.sh
/opt/fun-ai-agent-plane/update-agent-plane.sh
```

Optional environment variables:

- `APP_DIR` (default: `/opt/fun-ai-agent-plane`)
- `SERVICE_NAME` (default: `fun-ai-agent-plane`)
- `GIT_REMOTE` (default: `origin`)
- `GIT_BRANCH` (default: `main`)
- `HEALTH_URL` (default: `http://127.0.0.1:8090/internal/v1/health`)
