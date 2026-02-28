package com.fun.ai.agent.plane.service;

import com.fun.ai.agent.plane.config.DockerRuntimeProperties;
import com.fun.ai.agent.plane.model.CommandAction;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
public class DockerRuntimeService {

    private final DockerRuntimeProperties properties;

    public DockerRuntimeService(DockerRuntimeProperties properties) {
        this.properties = properties;
    }

    public String execute(UUID instanceId, CommandAction action, Map<String, Object> payload) {
        if (!properties.isEnabled()) {
            throw new DockerOperationException("docker runtime is disabled");
        }

        String image = resolveImage(payload);
        Integer gatewayHostPort = resolveGatewayHostPort(payload);
        return switch (action) {
            case START -> startInstance(instanceId, image, gatewayHostPort);
            case STOP -> stopInstance(instanceId);
            case RESTART, ROLLBACK -> restartInstance(instanceId, image, gatewayHostPort);
            case DELETE -> deleteInstance(instanceId);
        };
    }

    private String startInstance(UUID instanceId, String image, Integer gatewayHostPort) {
        String containerName = containerName(instanceId);
        if (!containerExists(containerName)) {
            if (!StringUtils.hasText(image)) {
                throw new DockerOperationException("image is required to create container");
            }
            createContainer(containerName, instanceId, image.trim(), gatewayHostPort);
        }

        if (containerRunning(containerName)) {
            return "Container already running: " + containerName;
        }

        runDockerChecked(List.of(properties.getCommand(), "start", containerName), "failed to start container");
        return "Container started: " + containerName;
    }

    private String stopInstance(UUID instanceId) {
        String containerName = containerName(instanceId);
        if (!containerExists(containerName)) {
            return "Container not found, stop skipped: " + containerName;
        }

        if (!containerRunning(containerName)) {
            return "Container already stopped: " + containerName;
        }

        runDockerChecked(List.of(properties.getCommand(), "stop", containerName), "failed to stop container");
        return "Container stopped: " + containerName;
    }

    private String restartInstance(UUID instanceId, String image, Integer gatewayHostPort) {
        String containerName = containerName(instanceId);
        if (!containerExists(containerName)) {
            if (!StringUtils.hasText(image)) {
                throw new DockerOperationException("image is required to create container for restart");
            }
            createContainer(containerName, instanceId, image.trim(), gatewayHostPort);
            runDockerChecked(List.of(properties.getCommand(), "start", containerName), "failed to start container");
            return "Container created and started: " + containerName;
        }

        runDockerChecked(List.of(properties.getCommand(), "restart", containerName), "failed to restart container");
        return "Container restarted: " + containerName;
    }

    private String deleteInstance(UUID instanceId) {
        String containerName = containerName(instanceId);
        if (!containerExists(containerName)) {
            return "Container not found, delete skipped: " + containerName;
        }

        if (containerRunning(containerName)) {
            runDockerChecked(
                    List.of(
                            properties.getCommand(),
                            "stop",
                            "-t",
                            String.valueOf(properties.getStopTimeoutSeconds()),
                            containerName
                    ),
                    "failed to stop container before delete"
            );
        }

        runDockerChecked(List.of(properties.getCommand(), "rm", containerName), "failed to delete container");
        return "Container deleted: " + containerName;
    }

    private void createContainer(String containerName, UUID instanceId, String image, Integer gatewayHostPort) {
        int hostPort = gatewayHostPort != null ? gatewayHostPort : properties.getGatewayHostPort();
        if (hostPort <= 0 || hostPort > 65535) {
            throw new DockerOperationException("invalid gateway host port: " + hostPort);
        }

        List<String> command = new ArrayList<>();
        command.add(properties.getCommand());
        command.add("create");
        command.add("--name");
        command.add(containerName);
        command.add("--label");
        command.add("fun.ai.instance-id=" + instanceId);
        command.add("-p");
        command.add(hostPort + ":" + properties.getGatewayContainerPort());
        command.add("-e");
        command.add("ZEROCLAW_GATEWAY_PORT=" + properties.getGatewayContainerPort());
        command.add("-e");
        command.add("ZEROCLAW_ALLOW_PUBLIC_BIND=" + properties.isAllowPublicBind());
        if (StringUtils.hasText(properties.getApiKey())) {
            command.add("-e");
            command.add("API_KEY=" + properties.getApiKey().trim());
        }
        if (StringUtils.hasText(properties.getRestartPolicy())) {
            command.add("--restart");
            command.add(properties.getRestartPolicy().trim());
        }
        command.add(image);
        command.add("gateway");
        command.add("--host");
        command.add(properties.getGatewayHost());
        command.add("--port");
        command.add(String.valueOf(properties.getGatewayContainerPort()));
        runDockerChecked(command, "failed to create container");
    }

    private boolean containerExists(String containerName) {
        CommandResult result = runDocker(List.of(properties.getCommand(), "container", "inspect", containerName));
        return result.exitCode == 0;
    }

    private boolean containerRunning(String containerName) {
        CommandResult result = runDocker(List.of(properties.getCommand(), "inspect", "-f", "{{.State.Running}}", containerName));
        if (result.exitCode != 0) {
            return false;
        }
        return "true".equalsIgnoreCase(result.output.trim());
    }

    private void runDockerChecked(List<String> command, String messagePrefix) {
        CommandResult result = runDocker(command);
        if (result.exitCode == 0) {
            return;
        }
        String details = result.output.isBlank() ? "exit code " + result.exitCode : result.output.trim();
        throw new DockerOperationException(messagePrefix + ": " + details);
    }

    private CommandResult runDocker(List<String> command) {
        ProcessBuilder processBuilder = new ProcessBuilder(command);
        processBuilder.redirectErrorStream(true);
        try {
            Process process = processBuilder.start();
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            process.getInputStream().transferTo(output);
            boolean finished = process.waitFor(properties.getCommandTimeoutSeconds(), TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new DockerOperationException("docker command timed out");
            }
            return new CommandResult(process.exitValue(), output.toString(StandardCharsets.UTF_8));
        } catch (IOException ex) {
            throw new DockerOperationException("failed to execute docker command: " + ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new DockerOperationException("docker command interrupted");
        }
    }

    private String resolveImage(Map<String, Object> payload) {
        if (payload == null) {
            return null;
        }
        Object rawImage = payload.get("image");
        if (rawImage instanceof String image && StringUtils.hasText(image)) {
            return image;
        }
        return null;
    }

    private Integer resolveGatewayHostPort(Map<String, Object> payload) {
        if (payload == null) {
            return null;
        }
        Object rawGatewayHostPort = payload.get("gatewayHostPort");
        if (rawGatewayHostPort == null) {
            return null;
        }
        if (rawGatewayHostPort instanceof Number numberValue) {
            return numberValue.intValue();
        }
        if (rawGatewayHostPort instanceof String stringValue && StringUtils.hasText(stringValue)) {
            try {
                return Integer.parseInt(stringValue.trim());
            } catch (NumberFormatException ex) {
                throw new DockerOperationException("invalid gateway host port: " + stringValue);
            }
        }
        throw new DockerOperationException("invalid gateway host port payload");
    }

    private String containerName(UUID instanceId) {
        return properties.getContainerPrefix() + "-" + instanceId;
    }

    private record CommandResult(int exitCode, String output) {
    }
}
