package com.fun.ai.agent.plane.model;

import java.time.Instant;
import java.util.UUID;

public record TaskExecutionRecord(
        UUID taskId,
        UUID instanceId,
        CommandType commandType,
        CommandAction action,
        TaskExecutionStatus status,
        String message,
        Instant executedAt
) {
}
