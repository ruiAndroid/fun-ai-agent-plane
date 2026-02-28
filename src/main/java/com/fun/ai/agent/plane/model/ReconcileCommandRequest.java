package com.fun.ai.agent.plane.model;

import jakarta.validation.constraints.NotNull;

import java.util.Map;
import java.util.UUID;

public record ReconcileCommandRequest(
        UUID taskId,
        @NotNull UUID instanceId,
        @NotNull CommandType commandType,
        @NotNull CommandAction action,
        String requestedBy,
        Map<String, Object> payload
) {
}
