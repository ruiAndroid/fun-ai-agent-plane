package com.fun.ai.agent.plane.model;

import java.util.List;

public record ListResponse<T>(
        List<T> items
) {
}
