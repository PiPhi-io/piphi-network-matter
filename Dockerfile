# syntax=docker/dockerfile:1.7

ARG CONNECTEDHOMEIP_BUILD_IMAGE=ghcr.io/project-chip/chip-build:182
FROM ${CONNECTEDHOMEIP_BUILD_IMAGE} AS chip-tool-builder

ARG CONNECTEDHOMEIP_REF=v1.5.0.1
ARG CHIP_TOOL_BUILD_RETRIES=3

USER root
SHELL ["/bin/bash", "-lc"]

WORKDIR /opt

RUN git clone --depth 1 --branch "${CONNECTEDHOMEIP_REF}" --recurse-submodules --shallow-submodules \
    https://github.com/project-chip/connectedhomeip.git /opt/connectedhomeip

WORKDIR /opt/connectedhomeip

RUN --mount=type=cache,target=/root/.cipd-cache-dir \
    --mount=type=cache,target=/root/.cache/ccache \
    --mount=type=cache,target=/opt/connectedhomeip/.environment \
    --mount=type=cache,target=/opt/connectedhomeip/out \
    set -eo pipefail; \
    export CIPD_CACHE_DIR=/root/.cipd-cache-dir; \
    export CCACHE_DIR=/root/.cache/ccache; \
    export CHIP_PW_COMMAND_LAUNCHER=ccache; \
    for attempt in $(seq 1 "${CHIP_TOOL_BUILD_RETRIES}"); do \
      echo "Building chip-tool (attempt ${attempt}/${CHIP_TOOL_BUILD_RETRIES})"; \
      if { \
        bash ./scripts/bootstrap.sh && \
        ./scripts/run_in_build_env.sh "./scripts/examples/gn_build_example.sh examples/chip-tool out/chip-tool"; \
      }; then \
        exit 0; \
      fi; \
      status=$?; \
      if [[ "${attempt}" == "${CHIP_TOOL_BUILD_RETRIES}" ]]; then \
        echo "chip-tool build failed after ${CHIP_TOOL_BUILD_RETRIES} attempts" >&2; \
        exit "${status}"; \
      fi; \
      echo "chip-tool build attempt ${attempt} failed with exit code ${status}; retrying..." >&2; \
      sleep 15; \
    done


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MATTER_ADAPTER_KIND=command \
    MATTER_BRIDGE_BACKEND_KIND=chip-tool \
    MATTER_STORAGE_DIR=/var/lib/piphi/matter \
    MATTER_BRIDGE_DATA_FILE=/var/lib/piphi/matter/registry_devices.json \
    MATTER_CONTROLLER_BINARY=/usr/local/bin/chip-tool

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libavahi-client3 \
    libdbus-1-3 \
    libevent-2.1-7 \
    libglib2.0-0 \
    libreadline8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY docker/entrypoint.sh /usr/local/bin/piphi-matter-entrypoint

RUN pip install . && chmod +x /usr/local/bin/piphi-matter-entrypoint

COPY --from=chip-tool-builder /opt/connectedhomeip/out/chip-tool/chip-tool /usr/local/bin/chip-tool

EXPOSE 8710

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json, urllib.request; json.load(urllib.request.urlopen('http://127.0.0.1:8710/health', timeout=3))" || exit 1

ENTRYPOINT ["/usr/local/bin/piphi-matter-entrypoint"]
CMD ["serve-api"]
