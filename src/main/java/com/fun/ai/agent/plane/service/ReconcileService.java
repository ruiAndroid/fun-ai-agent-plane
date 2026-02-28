package com.fun.ai.agent.plane.service;

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

    private final Map<UUID, TaskExecutionRecord> records = new ConcurrentHashMap<>();

    public TaskExecutionRecord accept(ReconcileCommandRequest request) {
        UUID taskId = Objects.requireNonNullElseGet(request.taskId(), UUID::randomUUID);
        TaskExecutionRecord record = new TaskExecutionRecord(
                taskId,
                request.instanceId(),
                request.commandType(),
                request.action(),
                TaskExecutionStatus.SUCCEEDED,
                "Command accepted and executed by bootstrap worker",
                Instant.now()
        );
        records.put(taskId, record);
        return record;
    }

    public List<TaskExecutionRecord> list() {
        return records.values().stream()
                .sorted(Comparator.comparing(TaskExecutionRecord::executedAt).reversed())
                .toList();
    }
}
