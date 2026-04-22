from __future__ import annotations

import asyncio
import json
import shlex
import sys

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
                        "metadata": {
                            "vendor_id": 4447,
                            "product_id": 1001,
                        },
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )

def test_service_can_discover_configure_and_poll_sample_device(tmp_path) -> None:
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

    devices = asyncio.run(service.discover_devices())
    assert len(devices) == 1
    assert devices[0].node_id == "1234"

    commissionables = asyncio.run(service.discover_commissionables(timeout_seconds=8))
    assert len(commissionables) == 1
    assert commissionables[0]["instance_name"] == "1234"

    configured = asyncio.run(
        service.configure_device(
            node_id="1234",
            endpoint_id=1,
            alias="Office climate",
        )
    )
    assert configured.alias == "Office climate"
    assert service.config_file_path.exists()

    telemetry_batch = asyncio.run(service.poll_configured_devices())
    assert telemetry_batch == [
        {
            "alias": "Office climate",
            "config_key": "1234:1",
            "endpoint_id": 1,
            "node_id": "1234",
            "preferred_source": "matter",
            "read_failed": False,
            "sampled_at": "2026-04-21T12:00:00+00:00",
            "state": {
                "battery_percent": 88,
                "connected": True,
                "humidity_percent": 41,
                "sampled_at": "2026-04-21T12:00:00+00:00",
                "temperature_c": 22.4,
            },
        }
    ]


def test_service_run_once_updates_snapshot_for_sample_adapter(tmp_path) -> None:
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
    asyncio.run(service.configure_device(node_id="1234", endpoint_id=1))

    asyncio.run(service.run_once())
    snapshot = service.snapshot()

    assert snapshot["adapter_kind"] == "sample"
    assert snapshot["adapter_data_file"] == str(data_file)
    assert snapshot["api_host"] == "127.0.0.1"
    assert snapshot["api_port"] == 8710
    assert snapshot["poll_count"] == 1
    assert snapshot["discovered_device_count"] == 1
    assert snapshot["configured_device_count"] == 1
    assert snapshot["last_telemetry_batch_count"] == 1
    assert snapshot["last_poll_at"] is not None
    assert snapshot["last_error"] is None


def test_service_can_manage_registry_devices(tmp_path) -> None:
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

    registry = asyncio.run(service.list_registry_devices())
    assert registry[0]["node_id"] == "1234"

    created = asyncio.run(
        service.upsert_registry_device(
            device={"node_id": "7777", "endpoint_id": 3, "name": "Kitchen Contact"}
        )
    )
    assert created["endpoint_id"] == 3

    removed = asyncio.run(service.remove_registry_device(node_id="7777", endpoint_id=3))
    assert removed is True


def test_service_can_invoke_sample_command(tmp_path) -> None:
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

    response = asyncio.run(
        service.invoke_command(
            node_id="1234",
            endpoint_id=1,
            command="refresh",
            args={"force": True},
        )
    )

    assert response["ok"] is True
    assert response["command"] == "refresh"
    assert response["args"] == {"force": True}


def test_service_can_commission_with_code(tmp_path) -> None:
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

    created = asyncio.run(
        service.commission_device_with_code(
            node_id="5555",
            setup_payload="MT:TESTPAYLOAD",
            device={"endpoint_id": 2, "name": "Bedroom Sensor"},
        )
    )
    assert created["node_id"] == "5555"
    assert created["endpoint_id"] == 2
    assert created["name"] == "Bedroom Sensor"
    configs = service.list_configs()
    assert len(configs) == 1
    assert configs[0].node_id == "5555"
    assert configs[0].endpoint_id == 2
    assert configs[0].alias == "Bedroom Sensor"


def test_service_commission_applies_common_device_profile(tmp_path) -> None:
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

    created = asyncio.run(
        service.commission_device_with_code(
            node_id="7777",
            setup_payload="MT:PLUGPAYLOAD",
            device={
                "endpoint_id": 1,
                "name": "Desk Plug",
                "device_type": "0x010A",
            },
        )
    )

    assert created["device_types"] == ["onoff_plug_in_unit"]
    assert created["capabilities"] == ["switch_on"]
    assert created["command_bindings"] == ["turn_on", "turn_off", "toggle"]
    assert created["chip_tool_reads"]["switch_on"]["cluster"] == "onoff"
    assert created["chip_tool_commands"]["turn_on"]["command"] == "on"


def test_service_lists_runtime_entities(tmp_path) -> None:
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

    entities = asyncio.run(service.list_entities())

    assert entities["entities"][0]["device_id"] == "1234:1"
    assert entities["entities"][0]["available_commands"][0]["id"] == "refresh"
    assert entities["entities"][0]["device_class"] == "sensor"
    assert entities["entities"][0]["dashboard"]["default_widget"] == "sensor-card"
    assert entities["commands"]["refresh"]["kind"] == "secondary"
    assert entities["capabilities"]["temperature_c"]["unit"] == "°C"
    assert "room-climate-card" in entities["capabilities"]["humidity_percent"]["dashboard"]["allowed_widgets"]


def test_service_background_subscriptions_cache_live_state(tmp_path) -> None:
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

    async def _exercise() -> list[dict[str, object]]:
        await service.start_background_runtime()
        try:
            await service.configure_device(node_id="1234", endpoint_id=1)
            await asyncio.sleep(0.05)
            return await service.poll_configured_devices()
        finally:
            await service.stop_background_runtime()

    telemetry_batch = asyncio.run(_exercise())

    assert telemetry_batch[0]["state"]["temperature_c"] == 22.4
    assert service.active_subscription_count == 0
    assert service.last_subscription_event_at is not None
    assert service.live_state_cache_file_path.exists()


def test_service_can_use_command_adapter(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    command = " ".join(
        [
            shlex.quote(sys.executable),
            "-m",
            "piphi_network_matter.controller.bridge_cli",
            "--backend-kind",
            "sample",
            "--data-file",
            shlex.quote(str(data_file)),
        ]
    )
    service = MatterSidecarService.from_config(
        MatterSidecarConfig(
            log_level="INFO",
            adapter_kind="command",
            poll_interval_seconds=30.0,
            storage_dir=str(tmp_path / "state"),
            adapter_command=command,
            api_host="127.0.0.1",
            api_port=8710,
        )
    )

    devices = asyncio.run(service.discover_devices())
    assert len(devices) == 1
    assert devices[0].node_id == "1234"

    commissionables = asyncio.run(service.discover_commissionables())
    assert commissionables[0]["instance_name"] == "1234"

    configured = asyncio.run(service.configure_device(node_id="1234", endpoint_id=1))
    assert configured.node_id == "1234"

    telemetry_batch = asyncio.run(service.poll_configured_devices())
    assert telemetry_batch[0]["config_key"] == "1234:1"
    assert telemetry_batch[0]["state"]["temperature_c"] == 22.4
    assert telemetry_batch[0]["read_failed"] is False
