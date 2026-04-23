# syntax=docker/dockerfile:1.7

ARG CHIP_TOOL_IMAGE=piphinetwork/matter-chip-tool:v1.5.0.1
FROM ${CHIP_TOOL_IMAGE} AS chip-tool-binary

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

COPY --from=chip-tool-binary /usr/local/bin/chip-tool /usr/local/bin/chip-tool

EXPOSE 8710

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json, urllib.request; json.load(urllib.request.urlopen('http://127.0.0.1:8710/health', timeout=3))" || exit 1

ENTRYPOINT ["/usr/local/bin/piphi-matter-entrypoint"]
CMD ["serve-api"]
