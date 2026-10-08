# piphi-network-matter

Small local Matter/Thread sidecar for PiPhi.

## Why this project exists

Matter and Thread need a local helper that can eventually own controller state,
fabric credentials, discovery, and command execution without pushing all of that
complexity into PiPhi core.

This repo is that sidecar.

## Mental model

- the Matter controller adapter is the local protocol brain
- this sidecar is the local service wrapper
- PiPhi core will eventually talk to this sidecar through a dedicated sidecar contract, not a full integration manifest/runtime package

The current repo now has the sidecar shape:

- env-backed sidecar config
- `run`, `serve-api`, `print-config`, `discover`, `configure`, `configs`, `poll-once`, registry-management CLI commands, and commissioning commands
- Docker packaging
- a small long-running service loop
- a pluggable controller adapter layer

## Current scope

- Provides a real sidecar scaffold, not just a placeholder README
- Loads env-backed sidecar config
- Starts a long-running local service process
- Exposes a local FastAPI sidecar contract for health, discovery, configs, and on-demand telemetry polling
- Polls a pluggable Matter adapter
- Persists configured devices in `configured_devices.json` under the storage directory
- Can run a file-backed `sample` adapter for local development and sidecar-contract work
- Can run a `command` adapter that shells out to an external controller bridge
- Can manage a Matter device registry through the sidecar API and CLI
- Can commission devices with setup codes into the registry flow
- Can discover commissionable Matter devices through the bridge/backend path
- Auto-configures commissioned devices into the configured poll set by default
- Negotiates concise safety capabilities for Matter Smoke/CO Alarm, Water Leak Detector, and Water Freeze Detector device types
- Publishes machine-readable safety-event coverage for Core's baseline-safe telemetry bridge; routine contact-open state is explicitly excluded
- Ships a container path that bundles `chip-tool` for live controller-backed operation
- Tracks simple sidecar health state like last poll time, discovered device count, and last error

## What is not implemented yet

- No native Matter Python/controller backend is wired in yet; the real path currently uses `chip-tool`
- No controller-native inventory of already commissioned devices yet; steady-state discovery still depends on the registry layer
- No general-purpose sidecar-to-Core push contract yet; Core currently consumes safety telemetry through the local polling API
- No subscriptions / push updates yet
- No persistent multi-fabric controller management yet

The current sidecar is intentionally honest: it is a strong local-service
foundation for the future Matter controller integration, not a fake fully
working Matter stack and not a pretend PiPhi integration package.

## Environment variables

- `MATTER_ADAPTER_KIND`
  Default: `null`
- `MATTER_POLL_INTERVAL_SECONDS`
  Default: `30`
- `MATTER_STORAGE_DIR`
  Default: `/var/lib/piphi/matter`
- `MATTER_ADAPTER_DATA_FILE`
  Optional adapter-specific file path. Used by the `sample` adapter.
- `MATTER_ADAPTER_COMMAND`
  Optional adapter executable. Used by the `command` adapter.
- `MATTER_AUTO_CONFIGURE_COMMISSIONED_DEVICES`
  Default: `true`
- `MATTER_API_HOST`
  Default: `127.0.0.1`
- `MATTER_API_PORT`
  Default: `8710`
- `LOG_LEVEL`
  Default: `INFO`

## Local development

Install dependencies:

```bash
pdm install -G dev
```

Run the sidecar:

```bash
pdm run matter run
```

Run the local sidecar API:

```bash
pdm run matter serve-api
```

Print the resolved sidecar config:

```bash
pdm run matter print-config
```

Dry run without starting the sidecar loop:

```bash
pdm run matter run --dry-run
```

Discover devices from a sample adapter file:

```bash
pdm run matter discover \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --storage-dir /tmp/piphi-matter
```

Discover commissionable devices:

```bash
pdm run matter discover-commissionables \
  --adapter-kind command \
  --adapter-command "python -m piphi_network_matter.controller.bridge_cli --backend-kind chip-tool --data-file ./matter_registry.json --controller-binary chip-tool" \
  --storage-dir /tmp/piphi-matter
```

Configure one discovered device for future polling:

```bash
pdm run matter configure 1234 1 \
  --alias "Office climate" \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --storage-dir /tmp/piphi-matter
```

List configured devices:

```bash
pdm run matter configs --storage-dir /tmp/piphi-matter
```

List registry devices:

```bash
pdm run matter registry-list \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json
```

Upsert a registry device:

```bash
pdm run matter registry-upsert \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --device-json '{"node_id":"8888","endpoint_id":1,"name":"Garage Sensor"}'
```

Remove a registry device:

```bash
pdm run matter registry-remove 8888 1 \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json
```

Commission a device with a setup payload:

```bash
pdm run matter commission-code 5555 MT:TESTPAYLOAD \
  --endpoint-id 1 \
  --name "Hall Sensor" \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json
```

Poll configured devices once and print a telemetry-style batch:

```bash
pdm run matter poll-once \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --storage-dir /tmp/piphi-matter
```

Example custom run:

```bash
pdm run matter run \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --storage-dir /var/lib/piphi/matter \
  --log-level DEBUG
```

Example API server run:

```bash
pdm run matter serve-api \
  --adapter-kind sample \
  --adapter-data-file ./sample_matter_devices.json \
  --storage-dir /tmp/piphi-matter \
  --api-host 0.0.0.0 \
  --api-port 8710
```

Example command-adapter run:

```bash
pdm run matter serve-api \
  --adapter-kind command \
  --adapter-command "python -m piphi_network_matter.controller.bridge_cli --backend-kind sample --data-file ./sample_matter_devices.json" \
  --storage-dir /tmp/piphi-matter \
  --api-host 0.0.0.0 \
  --api-port 8710
```

Live `chip-tool`-backed run:

```bash
pdm run matter serve-api \
  --adapter-kind command \
  --adapter-command "python -m piphi_network_matter.controller.bridge_cli --backend-kind chip-tool --data-file ./matter_registry.json --controller-binary chip-tool" \
  --storage-dir /tmp/piphi-matter \
  --api-host 0.0.0.0 \
  --api-port 8710
```

## Image release flow

The Docker release path is intentionally split in two:

- `piphinetwork/matter-chip-tool:<CONNECTEDHOMEIP_REF>`
  A rarely updated artifact image that only contains a prebuilt `chip-tool` binary.
- `piphinetwork/matter-sidecar:<version>`
  The normal sidecar image that copies `chip-tool` from the prebuilt artifact image and ships the Python API/runtime.

Recommended release order:

1. Build or refresh the `chip-tool` artifact image with the `Build Matter chip-tool image` workflow when `CONNECTEDHOMEIP_REF` changes.
2. Release the normal sidecar image with the `Release Matter Sidecar to Docker Hub` workflow, pointing it at the desired prebuilt `chip-tool` image tag.

The `chip-tool` workflow builds the binary in the upstream Matter build environment first, then packages only that binary into the artifact image. This avoids compiling `connectedhomeip` inside the normal sidecar Docker release build.

The repo also keeps the currently recommended prebuilt `chip-tool` artifact pinned in:

- `.github/matter-chip-tool-image.txt`

The `Build Matter chip-tool image` workflow updates that file to a digest-pinned image reference after a successful publish.
The `Release Matter Sidecar to Docker Hub` workflow defaults `chip_tool_image` to `pinned`, which resolves to that tracked digest.

This keeps normal sidecar releases lightweight and avoids rebuilding the full Matter toolchain on every app release.

## Sidecar API

The sidecar now exposes a small local FastAPI contract:

- `GET /health`
- `GET /v1/snapshot`
- `GET /v1/devices/discover`
- `GET /v1/discovery/commissionables`
- `GET /v1/registry`
- `POST /v1/registry`
- `DELETE /v1/registry/<node_id>/<endpoint_id>`
- `POST /v1/commission/code`
- `GET /v1/configs`
- `POST /v1/configs`
- `DELETE /v1/configs/<node_id>/<endpoint_id>`
- `POST /v1/telemetry/poll`
- `POST /v1/commands/invoke`

Interactive docs are available at:

- `GET /docs`

Example:

```bash
curl http://127.0.0.1:8710/health
curl http://127.0.0.1:8710/v1/devices/discover
curl http://127.0.0.1:8710/v1/discovery/commissionables
curl http://127.0.0.1:8710/v1/registry
curl -X POST http://127.0.0.1:8710/v1/registry \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"8888","endpoint_id":1,"name":"Garage Sensor"}'
curl -X POST http://127.0.0.1:8710/v1/commission/code \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"5555","setup_payload":"MT:TESTPAYLOAD","endpoint_id":1,"name":"Hall Sensor"}'
curl -X POST http://127.0.0.1:8710/v1/configs \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"1234","endpoint_id":1,"alias":"Office climate"}'
curl -X POST http://127.0.0.1:8710/v1/telemetry/poll
curl -X POST http://127.0.0.1:8710/v1/commands/invoke \
  -H 'Content-Type: application/json' \
  -d '{"node_id":"5555","endpoint_id":1,"command":"turn_on","args":{}}'
```

Commissioned devices are auto-configured for polling by default, so a successful `POST /v1/commission/code` also makes the device appear under `/v1/configs`.

## Sample adapter payload

The `sample` adapter accepts either:

- a top-level JSON array of device objects
- or an object with a `devices` array

Example:

```json
{
  "devices": [
    {
      "node_id": "1234",
      "endpoint_id": 1,
      "name": "Living Room Climate Sensor",
      "vendor_name": "Aqara",
      "product_name": "Climate Sensor P2",
      "device_types": ["temperature_sensor", "humidity_sensor"],
      "capabilities": ["temperature_c", "humidity_percent", "battery_percent"],
      "state": {
        "temperature_c": 22.4,
        "humidity_percent": 41,
        "battery_percent": 88,
        "connected": true,
        "sampled_at": "2026-04-21T12:00:00+00:00"
      },
      "metadata": {
        "vendor_id": 4447,
        "product_id": 1001
      }
    }
  ]
}
```

## Command adapter contract

The `command` adapter shells out to an external executable and expects JSON on stdout.

Supported invocations:

- `controller-binary list-devices`
- `controller-binary read-state --node-id <id> --endpoint-id <id>`
- `controller-binary commission-with-code --node-id <id> --setup-payload <payload> --device-json <json>`
- `controller-binary invoke-command --node-id <id> --endpoint-id <id> --command <name> --args-json <json>`

This gives us a clean path to wrap a real Matter controller process later without changing the sidecar API.

## chip-tool backend

The bundled controller bridge now also supports a `chip-tool` backend.

This backend is registry-driven:

- the registry file provides the commissioned device inventory
- each device can define `chip_tool_reads` capability mappings
- each device can define `chip_tool_commands` command mappings

Example:

```json
{
  "devices": [
    {
      "node_id": "8888",
      "endpoint_id": 1,
      "name": "Chip Tool Sensor",
      "capabilities": ["temperature_c", "humidity_percent", "switch_on"],
      "chip_tool_reads": {
        "temperature_c": {
          "cluster": "temperaturemeasurement",
          "attribute": "measured-value",
          "value_regex": "MeasuredValue: (-?\\d+)",
          "transform": "centi"
        },
        "humidity_percent": {
          "cluster": "relativehumiditymeasurement",
          "attribute": "measured-value",
          "value_regex": "MeasuredValue: (\\d+)",
          "transform": "centi"
        }
      },
      "chip_tool_commands": {
        "turn_on": {
          "cluster": "onoff",
          "command": "on"
        }
      }
    }
  ]
}
```

Run the bridge directly against `chip-tool`:

```bash
pdm run matter-controller-bridge \
  --backend-kind chip-tool \
  --data-file ./matter_registry.json \
  --controller-binary chip-tool \
  read-state --node-id 8888 --endpoint-id 1
```

Point the sidecar at the bridge:

```bash
pdm run matter serve-api \
  --adapter-kind command \
  --adapter-command "python -m piphi_network_matter.controller.bridge_cli --backend-kind chip-tool --data-file ./matter_registry.json --controller-binary chip-tool"
```

This backend is intentionally practical rather than magical: chip-tool is the real controller, and PiPhi supplies the persistent registry and capability mapping layer around it.

## Bundled controller bridge

This repo now ships a bundled controller bridge CLI that already speaks the command-adapter contract.

Run it directly:

```bash
pdm run matter-controller-bridge --backend-kind sample --data-file ./sample_matter_devices.json list-devices
```

Or point the sidecar at it through the command adapter:

```bash
pdm run matter serve-api \
  --adapter-kind command \
  --adapter-command "python -m piphi_network_matter.controller.bridge_cli --backend-kind sample --data-file ./sample_matter_devices.json"
```

That gives us a stable bridge entrypoint now, while leaving room to swap the backend from `sample` to a real Matter controller later.

## Docker

Build:

```bash
docker build -t piphinetwork/matter-sidecar .
```

Run:

```bash
docker run --rm \
  -e MATTER_STORAGE_DIR=/var/lib/piphi/matter \
  -e MATTER_API_HOST=0.0.0.0 \
  -e MATTER_API_PORT=8710 \
  -p 8710:8710 \
  piphinetwork/matter-sidecar
```

The image now defaults to:

- `MATTER_ADAPTER_KIND=command`
- `MATTER_BRIDGE_BACKEND_KIND=chip-tool`
- `MATTER_BRIDGE_DATA_FILE=/var/lib/piphi/matter/registry_devices.json`
- `MATTER_CONTROLLER_BINARY=/usr/local/bin/chip-tool`

So for a live `chip-tool`-backed run you only need to persist the storage directory:

```bash
docker run --rm \
  -v ./matter-state:/var/lib/piphi/matter \
  -e MATTER_STORAGE_DIR=/var/lib/piphi/matter \
  -e MATTER_API_HOST=0.0.0.0 \
  -e MATTER_API_PORT=8710 \
  -p 8710:8710 \
  piphinetwork/matter-sidecar
```

## Testing

```bash
pdm run pytest
```
