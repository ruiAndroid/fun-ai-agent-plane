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
- `DELETE /internal/v1/instances/{instanceId}`
- `GET /internal/v1/tasks`

Current implementation executes real Docker commands on host for:

- `START`: create (if absent) + start container
- `STOP`: stop container
- `RESTART`/`ROLLBACK`: restart container (or create+start if absent)
- `DELETE`: stop container gracefully, then remove container

Container name pattern: `${DOCKER_CONTAINER_PREFIX}-${instanceId}` (default prefix: `funclaw`).

Required: plane process user must be allowed to run Docker CLI.

Docker-related environment variables:

- `DOCKER_RUNTIME_ENABLED` (default: `true`)
- `DOCKER_CMD` (default: `docker`)
- `DOCKER_CONTAINER_PREFIX` (default: `funclaw`)
- `DOCKER_RESTART_POLICY` (default: `unless-stopped`)
- `DOCKER_GATEWAY_HOST_PORT` (default: `42617`)
- `DOCKER_GATEWAY_CONTAINER_PORT` (default: `42617`)
- `DOCKER_GATEWAY_HOST` (default: `0.0.0.0`)
- `DOCKER_ALLOW_PUBLIC_BIND` (default: `true`)
- `ZEROCLAW_API_KEY` (default: empty)
- `DOCKER_STOP_TIMEOUT_SECONDS` (default: `20`)
- `DOCKER_COMMAND_TIMEOUT_SECONDS` (default: `120`)

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
- `MVN_CMD` (default: `mvn`, Maven >= `3.6.3`)
