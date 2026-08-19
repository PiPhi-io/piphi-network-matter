from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from piphi_network_matter.api import create_app
from piphi_network_matter.config import MatterSidecarConfig
from piphi_network_matter.service import MatterSidecarService


def _write_sample_devices(path) -> None:
    path.write_text(
        json.dumps(
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
                        "command_bindings": ["refresh"],
                        "state": {
                            "temperature_c": 22.4,
                            "humidity_percent": 41,
                            "battery_percent": 88,
                            "connected": True,
                            "sampled_at": "2026-04-21T12:00:00+00:00",
                        },
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


def _build_client(tmp_path) -> TestClient:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    service = MatterSidecarService.from_config(
        MatterSidecarConfig(
            log_level="INFO",
            adapter_kind="sample",
            poll_interval_seconds=30.0,
            storage_dir=str(tmp_path / "state"),
            adapter_data_file=str(data_file),
            api_host="127.0.0.1",
            api_port=8710,
        )
    )
    return TestClient(create_app(service))


def test_api_health_and_discovery_routes(tmp_path) -> None:
    client = _build_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["service"]["api_port"] == 8710
    assert health.json()["service"]["started_at"] is not None

    discovery = client.get("/v1/devices/discover", params={"node_id": "1234"})
    assert discovery.status_code == 200
    assert discovery.json()[0]["device_id"] == "1234:1"
    assert discovery.json()[0]["command_bindings"] == ["refresh"]

    commissionables = client.get("/v1/discovery/commissionables", params={"timeout_seconds": 9})
    assert commissionables.status_code == 200
    assert commissionables.json()[0]["instance_name"] == "1234"

    entities = client.get("/entities")
    assert entities.status_code == 200
    assert entities.json()["entities"][0]["device_id"] == "1234:1"
    assert entities.json()["entities"][0]["device_class"] == "sensor"
    assert entities.json()["entities"][0]["dashboard"]["default_widget"] == "sensor-card"
    assert entities.json()["commands"]["refresh"]["kind"] == "secondary"
    assert entities.json()["capabilities"]["battery_percent"]["dashboard"]["default_widget"] == "device-health-card"

    registry = client.get("/v1/registry")
    assert registry.status_code == 200
    assert registry.json()[0]["node_id"] == "1234"


def test_api_config_and_telemetry_routes(tmp_path) -> None:
    client = _build_client(tmp_path)

    create = client.post(
        "/v1/configs",
        json={
            "node_id": "1234",
            "endpoint_id": 1,
            "alias": "Office climate",
        },
    )
    assert create.status_code == 201
    assert create.json()["alias"] == "Office climate"

    configs = client.get("/v1/configs")
    assert configs.status_code == 200
    assert configs.json()[0]["node_id"] == "1234"

    telemetry = client.post("/v1/telemetry/poll")
    assert telemetry.status_code == 200
    assert telemetry.json()[0]["config_key"] == "1234:1"
    assert telemetry.json()[0]["state"]["temperature_c"] == 22.4

    removed = client.delete("/v1/configs/1234/1")
    assert removed.status_code == 200
    assert removed.json()["removed"] is True


def test_api_registry_routes(tmp_path) -> None:
    client = _build_client(tmp_path)

    create = client.post(
        "/v1/registry",
        json={
            "node_id": "8888",
            "endpoint_id": 2,
            "name": "Garage Sensor",
            "capabilities": ["contact_open"],
        },
    )
    assert create.status_code == 201
    assert create.json()["node_id"] == "8888"

    registry = client.get("/v1/registry")
    assert registry.status_code == 200
    assert any(item["node_id"] == "8888" and item["endpoint_id"] == 2 for item in registry.json())

    removed = client.delete("/v1/registry/8888/2")
    assert removed.status_code == 200
    assert removed.json()["removed"] is True


def test_api_commission_with_code_route(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.post(
        "/v1/commission/code",
        json={
            "node_id": "5555",
            "setup_payload": "MT:TESTPAYLOAD",
            "endpoint_id": 4,
            "name": "Porch Sensor",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["node_id"] == "5555"
    assert payload["endpoint_id"] == 4
    assert payload["name"] == "Porch Sensor"

    configs = client.get("/v1/configs")
    assert configs.status_code == 200
    assert any(item["node_id"] == "5555" and item["endpoint_id"] == 4 for item in configs.json())


def test_api_commission_applies_device_profile_fields(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.post(
        "/v1/commission/code",
        json={
            "node_id": "8888",
            "setup_payload": "MT:PLUGPAYLOAD",
            "endpoint_id": 1,
            "name": "Office Plug",
            "device_type": "266",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["device_types"] == ["onoff_plug_in_unit"]
    assert payload["capabilities"] == ["switch_on"]
    assert payload["command_bindings"] == ["turn_on", "turn_off", "toggle"]


def test_api_invoke_command_route(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.post(
        "/v1/commands/invoke",
        json={
            "node_id": "1234",
            "endpoint_id": 1,
            "command": "refresh",
            "args": {"force": True},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["command"] == "refresh"
    assert payload["args"] == {"force": True}


def test_api_command_replays_key_without_repeating_matter_effect(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    service = MatterSidecarService.from_config(
        MatterSidecarConfig(
            log_level="INFO",
            adapter_kind="sample",
            poll_interval_seconds=30.0,
            storage_dir=str(tmp_path / "state"),
            adapter_data_file=str(data_file),
            api_host="127.0.0.1",
            api_port=8710,
        )
    )
    client = TestClient(create_app(service))
    headers = {"X-PiPhi-Idempotency-Key": "matter-action-idempotency-1"}
    payload = {
        "node_id": "1234",
        "endpoint_id": 1,
        "command": "refresh",
        "args": {"force": True},
    }

    with patch.object(
        MatterSidecarService,
        "invoke_command",
        new_callable=AsyncMock,
        return_value={
            "ok": True,
            "command": "refresh",
            "args": {"force": True},
        },
    ) as invoke_command:
        first = client.post("/v1/commands/invoke", json=payload, headers=headers)
        replay = client.post("/v1/commands/invoke", json=payload, headers=headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    invoke_command.assert_awaited_once_with(
        node_id="1234",
        endpoint_id=1,
        command="refresh",
        args={"force": True},
    )


def test_api_returns_not_found_for_unknown_config(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.delete("/v1/configs/9999/1")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
