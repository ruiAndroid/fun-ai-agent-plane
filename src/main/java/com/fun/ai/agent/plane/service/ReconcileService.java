package com.fun.ai.agent.plane.service;

import com.fun.ai.agent.plane.model.CommandAction;
import com.fun.ai.agent.plane.model.CommandType;
import com.fun.ai.agent.plane.model.ReconcileCommandRequest;
import com.fun.ai.agent.plane.model.TaskExecutionRecord;
import com.fun.ai.agent.plane.model.TaskExecutionStatus;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class ReconcileService {

    private final DockerRuntimeService dockerRuntimeService;
    private final Map<UUID, TaskExecutionRecord> records = new ConcurrentHashMap<>();

    public ReconcileService(DockerRuntimeService dockerRuntimeService) {
        this.dockerRuntimeService = dockerRuntimeService;
    }

    public TaskExecutionRecord accept(ReconcileCommandRequest request) {
        UUID taskId = Objects.requireNonNullElseGet(request.taskId(), UUID::randomUUID);
        TaskExecutionRecord record;
        try {
            String message = dockerRuntimeService.execute(request.instanceId(), request.action(), request.payload());
            record = new TaskExecutionRecord(
                    taskId,
                    request.instanceId(),
                    request.commandType(),
                    request.action(),
                    TaskExecutionStatus.SUCCEEDED,
                    message,
                    Instant.now()
            );
        } catch (DockerOperationException ex) {
            record = new TaskExecutionRecord(
                    taskId,
                    request.instanceId(),
                    request.commandType(),
                    request.action(),
                    TaskExecutionStatus.FAILED,
                    ex.getMessage(),
                    Instant.now()
            );
        }
        records.put(taskId, record);
        return record;
    }

    public TaskExecutionRecord deleteInstance(UUID instanceId) {
        ReconcileCommandRequest request = new ReconcileCommandRequest(
                UUID.randomUUID(),
                instanceId,
                CommandType.INSTANCE_ACTION,
                CommandAction.DELETE,
                "api",
                Map.of()
        );
        return accept(request);
    }

    public List<TaskExecutionRecord> list() {
        return records.values().stream()
                .sorted(Comparator.comparing(TaskExecutionRecord::executedAt).reversed())
                .toList();
    }
}
