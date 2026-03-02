#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/fun-ai-agent-plane}"
SERVICE_NAME="${SERVICE_NAME:-fun-ai-agent-plane}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8100/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-20}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-2}"
PYTHON_BIN="${PYTHON_BIN:-}"
PIP_EXTRA_ARGS="${PIP_EXTRA_ARGS:-}"
RECREATE_VENV="${RECREATE_VENV:-false}"
ENABLE_AGENT_SYNC="${ENABLE_AGENT_SYNC:-true}"
ENABLE_SKILLS_SYNC="${ENABLE_SKILLS_SYNC:-false}"
ENABLE_MCP_SYNC="${ENABLE_MCP_SYNC:-false}"
ENABLE_MODEL_SYNC="${ENABLE_MODEL_SYNC:-false}"
AGENT_SYNC_CMD="${AGENT_SYNC_CMD:-}"
SKILLS_SYNC_CMD="${SKILLS_SYNC_CMD:-}"
MCP_SYNC_CMD="${MCP_SYNC_CMD:-}"
MODEL_SYNC_CMD="${MODEL_SYNC_CMD:-}"
AGENT_SYNC_SCRIPT="${AGENT_SYNC_SCRIPT:-./deploy-hooks/agent-sync.sh}"
SKILLS_SYNC_SCRIPT="${SKILLS_SYNC_SCRIPT:-./deploy-hooks/skills-sync.sh}"
MCP_SYNC_SCRIPT="${MCP_SYNC_SCRIPT:-./deploy-hooks/mcp-sync.sh}"
MODEL_SYNC_SCRIPT="${MODEL_SYNC_SCRIPT:-./deploy-hooks/model-sync.sh}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || fail "${cmd} not found"
}

run_shell_step() {
  local step_name="$1"
  local cmd="$2"
  echo "Running ${step_name}: ${cmd}"
  bash -lc "${cmd}"
}

run_sync_step() {
  local step_name="$1"
  local enabled="$2"
  local cmd="$3"
  local script_path="$4"

  if [[ "${enabled}" != "true" ]]; then
    echo "Skip ${step_name}: disabled (ENABLE_${step_name^^}_SYNC=${enabled})"
    return 0
  fi

  if [[ -n "${cmd}" ]]; then
    run_shell_step "${step_name}" "${cmd}"
    return 0
  fi

  if [[ -f "${script_path}" ]]; then
    if [[ ! -x "${script_path}" ]]; then
      chmod +x "${script_path}"
    fi
    echo "Running ${step_name} sync script: ${script_path}"
    "${script_path}"
    return 0
  fi

  echo "Skip ${step_name}: no command set and script not found (${script_path})"
}

python_major_minor() {
  local bin="$1"
  "${bin}" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")'
}

python_is_supported() {
  local bin="$1"
  local major_minor
  major_minor="$(python_major_minor "${bin}")"
  local major="${major_minor%%.*}"
  local minor="${major_minor##*.}"
  [[ "${major}" -gt 3 ]] || ([[ "${major}" -eq 3 ]] && [[ "${minor}" -ge 8 ]])
}

dump_python_candidates() {
  local candidates=(
    python3.12 python3.11 python3.10 python3.9 python3.8 python3 python
    /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3.9 /usr/local/bin/python3.8
    /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 /usr/bin/python3.9 /usr/bin/python3.8
  )
  local c
  echo "Detected Python candidates:" >&2
  for c in "${candidates[@]}"; do
    if [[ "${c}" = /* ]]; then
      if [[ -x "${c}" ]]; then
        echo "  ${c}: $("${c}" -V 2>&1 || true)" >&2
      fi
    elif command -v "${c}" >/dev/null 2>&1; then
      local path
      path="$(command -v "${c}")"
      echo "  ${c}: ${path} ($("${c}" -V 2>&1 || true))" >&2
    fi
  done
}

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN}" ]]; then
    require_cmd "${PYTHON_BIN}"
    python_is_supported "${PYTHON_BIN}" || fail "Python ${PYTHON_BIN} is too old ($(python_major_minor "${PYTHON_BIN}")). Need >= 3.8."
    return
  fi

  # Non-login/root shells sometimes miss /usr/local/bin in PATH.
  # Probe both command names and common absolute paths.
  local candidates=(
    python3.12 python3.11 python3.10 python3.9 python3.8 python3 python
    /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3.10 /usr/local/bin/python3.9 /usr/local/bin/python3.8
    /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 /usr/bin/python3.9 /usr/bin/python3.8
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ "${c}" = /* ]]; then
      if [[ -x "${c}" ]] && python_is_supported "${c}"; then
        PYTHON_BIN="${c}"
        return
      fi
    else
      if command -v "${c}" >/dev/null 2>&1 && python_is_supported "${c}"; then
        PYTHON_BIN="${c}"
        return
      fi
    fi
  done

  dump_python_candidates
  fail "No supported Python found. Install Python >= 3.8 and rerun with PYTHON_BIN=/path/to/python. Current PATH=${PATH}"
}

ensure_venv_python() {
  local target_major_minor
  target_major_minor="$(python_major_minor "${PYTHON_BIN}")"

  if [[ "${RECREATE_VENV}" == "true" ]]; then
    echo "RECREATE_VENV=true, removing existing .venv"
    rm -rf .venv
  fi

  if [[ -d ".venv" ]]; then
    if [[ ! -x ".venv/bin/python" ]]; then
      echo "Existing .venv is broken (missing .venv/bin/python), recreating"
      rm -rf .venv
    else
      local venv_major_minor
      venv_major_minor="$(python_major_minor ".venv/bin/python" || true)"
      if [[ -z "${venv_major_minor}" ]] || ! python_is_supported ".venv/bin/python"; then
        echo "Existing .venv Python is unsupported (${venv_major_minor:-unknown}), recreating with ${target_major_minor}"
        rm -rf .venv
      elif [[ "${venv_major_minor}" != "${target_major_minor}" ]]; then
        echo "Existing .venv Python is ${venv_major_minor}, target is ${target_major_minor}; recreating"
        rm -rf .venv
      fi
    fi
  fi

  if [[ ! -d ".venv" ]]; then
    "${PYTHON_BIN}" -m venv .venv
  fi
}

if [[ ! -d "${APP_DIR}" ]]; then
  fail "APP_DIR is invalid: ${APP_DIR}"
fi

if ! git -C "${APP_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "APP_DIR is not a git repository: ${APP_DIR}"
fi

require_cmd git
require_cmd curl
require_cmd systemctl
resolve_python_bin

cd "${APP_DIR}"

echo "[1/5] Pull latest code from ${GIT_REMOTE}/${GIT_BRANCH}"
git fetch "${GIT_REMOTE}" "${GIT_BRANCH}"
git checkout "${GIT_BRANCH}"
git pull --ff-only "${GIT_REMOTE}" "${GIT_BRANCH}"

echo "[2/9] Sync Python venv and dependencies"
ensure_venv_python
.venv/bin/python -m pip install --upgrade pip
# shellcheck disable=SC2086
.venv/bin/python -m pip install ${PIP_EXTRA_ARGS} -r requirements.txt

echo "[3/9] Sync agent assets/config"
run_sync_step "agent" "${ENABLE_AGENT_SYNC}" "${AGENT_SYNC_CMD}" "${AGENT_SYNC_SCRIPT}"

echo "[4/9] Sync skills"
run_sync_step "skills" "${ENABLE_SKILLS_SYNC}" "${SKILLS_SYNC_CMD}" "${SKILLS_SYNC_SCRIPT}"

echo "[5/9] Sync MCP"
run_sync_step "mcp" "${ENABLE_MCP_SYNC}" "${MCP_SYNC_CMD}" "${MCP_SYNC_SCRIPT}"

echo "[6/9] Sync model profiles"
run_sync_step "model" "${ENABLE_MODEL_SYNC}" "${MODEL_SYNC_CMD}" "${MODEL_SYNC_SCRIPT}"

echo "[7/9] Restart service ${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "[8/9] Health check ${HEALTH_URL}"
for ((i=1; i<=HEALTH_RETRIES; i++)); do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "SUCCESS: ${SERVICE_NAME} is healthy"
    echo "[9/9] Show service status"
    systemctl --no-pager --full status "${SERVICE_NAME}" | head -n 20
    exit 0
  fi
  sleep "${HEALTH_WAIT_SECONDS}"
done

echo "ERROR: health check failed after ${HEALTH_RETRIES} retries"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
journalctl -u "${SERVICE_NAME}" -n 100 --no-pager || true
exit 1
