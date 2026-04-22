#!/bin/sh
set -eu

: "${MATTER_STORAGE_DIR:=/var/lib/piphi/matter}"
: "${MATTER_ADAPTER_KIND:=command}"
: "${MATTER_BRIDGE_BACKEND_KIND:=chip-tool}"
: "${MATTER_BRIDGE_DATA_FILE:=${MATTER_STORAGE_DIR}/registry_devices.json}"
: "${MATTER_CONTROLLER_BINARY:=/usr/local/bin/chip-tool}"

mkdir -p "${MATTER_STORAGE_DIR}"

if [ ! -f "${MATTER_BRIDGE_DATA_FILE}" ]; then
  mkdir -p "$(dirname "${MATTER_BRIDGE_DATA_FILE}")"
  printf '[]\n' > "${MATTER_BRIDGE_DATA_FILE}"
fi

if [ -z "${MATTER_ADAPTER_DATA_FILE:-}" ]; then
  export MATTER_ADAPTER_DATA_FILE="${MATTER_BRIDGE_DATA_FILE}"
fi

if [ "${MATTER_ADAPTER_KIND}" = "command" ] && [ -z "${MATTER_ADAPTER_COMMAND:-}" ]; then
  MATTER_ADAPTER_COMMAND="python -m piphi_network_matter.controller.bridge_cli --backend-kind ${MATTER_BRIDGE_BACKEND_KIND} --data-file ${MATTER_BRIDGE_DATA_FILE}"
  if [ "${MATTER_BRIDGE_BACKEND_KIND}" = "chip-tool" ]; then
    MATTER_ADAPTER_COMMAND="${MATTER_ADAPTER_COMMAND} --controller-binary ${MATTER_CONTROLLER_BINARY}"
  fi
  export MATTER_ADAPTER_COMMAND
fi

if [ "$#" -eq 0 ]; then
  set -- serve-api
fi

exec python -m piphi_network_matter "$@"
