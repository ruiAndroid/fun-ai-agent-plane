# fun-ai-agent-plane

Execution plane service for reconciling lobster instance commands.

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
