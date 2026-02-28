package com.fun.ai.agent.plane.controller;

import com.fun.ai.agent.plane.model.HealthResponse;
import com.fun.ai.agent.plane.model.ListResponse;
import com.fun.ai.agent.plane.model.ReconcileCommandRequest;
import com.fun.ai.agent.plane.model.TaskExecutionRecord;
import com.fun.ai.agent.plane.service.ReconcileService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/v1")
public class InternalController {

    private final ReconcileService reconcileService;

    public InternalController(ReconcileService reconcileService) {
        this.reconcileService = reconcileService;
    }

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("UP", "fun-ai-agent-plane");
    }

    @PostMapping("/reconcile")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public TaskExecutionRecord reconcile(@Valid @RequestBody ReconcileCommandRequest request) {
        return reconcileService.accept(request);
    }

    @GetMapping("/tasks")
    public ListResponse<TaskExecutionRecord> listTasks() {
        return new ListResponse<>(reconcileService.list());
    }
}
