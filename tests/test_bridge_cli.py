from __future__ import annotations

import json
import stat
import textwrap

from click.testing import CliRunner

from piphi_network_matter.controller.bridge_cli import main


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
                            "long_discriminator": 3840,
                            "addresses": ["fd00::1234"],
                        },
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


def _write_chip_tool_registry(path) -> None:
    path.write_text(
        json.dumps(
            {
                "devices": [
                    {
                        "node_id": "8888",
                        "endpoint_id": 1,
                        "name": "Chip Tool Sensor",
                        "vendor_name": "Aqara",
                        "product_name": "P2 Sensor",
                        "device_types": ["temperature_sensor", "humidity_sensor"],
                        "capabilities": ["temperature_c", "humidity_percent", "switch_on"],
                        "chip_tool_reads": {
                            "temperature_c": {
                                "cluster": "temperaturemeasurement",
                                "attribute": "measured-value",
                                "value_regex": "MeasuredValue: (-?\\d+)",
                                "transform": "centi",
                            },
                            "humidity_percent": {
                                "cluster": "relativehumiditymeasurement",
                                "attribute": "measured-value",
                                "value_regex": "MeasuredValue: (\\d+)",
                                "transform": "centi",
                            },
                            "switch_on": {
                                "cluster": "onoff",
                                "attribute": "on-off",
                                "value_regex": "OnOff: (true|false)",
                                "transform": "bool",
                            },
                        },
                        "chip_tool_commands": {
                            "turn_on": {
                                "cluster": "onoff",
                                "command": "on",
                            }
                        },
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
    )


def _write_fake_chip_tool(path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import sys


args = sys.argv[1:]
if args[:3] == ["temperaturemeasurement", "read", "measured-value"]:
    print("MeasuredValue: 2240")
elif args[:3] == ["temperaturemeasurement", "subscribe", "measured-value"]:
    print("MeasuredValue: 2240")
elif args[:3] == ["relativehumiditymeasurement", "read", "measured-value"]:
    print("MeasuredValue: 4150")
elif args[:3] == ["relativehumiditymeasurement", "subscribe", "measured-value"]:
    print("MeasuredValue: 4150")
elif args[:3] == ["onoff", "read", "on-off"]:
    print("OnOff: true")
elif args[:2] == ["onoff", "on"]:
    print("Command succeeded")
elif args[:3] == ["onoff", "subscribe", "on-off"]:
    print("OnOff: true")
elif args[:2] == ["pairing", "code"]:
    print("Commissioning complete")
elif args[:3] == ["descriptor", "read", "device-type-list"]:
    print("deviceType: 0x010A")
elif args[:3] == ["basicinformation", "read", "vendor-name"]:
    print("VendorName: TP-Link")
elif args[:3] == ["basicinformation", "read", "product-name"]:
    print("ProductName: KP125M")
elif args[:3] == ["basicinformation", "read", "vendor-id"]:
    print("VendorID: 0x1234")
elif args[:3] == ["basicinformation", "read", "product-id"]:
    print("ProductID: 0x5678")
elif args[:2] == ["discover", "commissionables"]:
    print(\"\"\"Discovered node:
Hostname: matter-1234.local
IP Address #1: fd00::1234
Port: 5540
Vendor ID: 0x115F
Product ID: 0x03E9
Device Type: 0x0302
Long Discriminator: 3840
Pairing Hint: 33
Instance Name: AQARA-TEST
Commissioning Mode: 1
\"\"\")
else:
    print("unexpected args", " ".join(args), file=sys.stderr)
    raise SystemExit(1)
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _write_sleeping_chip_tool(path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            from __future__ import annotations

            import sys
            import time


            args = sys.argv[1:]
            if args[:2] == ["discover", "commissionables"]:
                time.sleep(2)
                print("Discovered node:")
            else:
                print("unexpected args", " ".join(args), file=sys.stderr)
                raise SystemExit(1)
            """
        )
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_bridge_cli_list_devices_and_read_state(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    list_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "list-devices",
        ],
    )
    assert list_result.exit_code == 0
    assert json.loads(list_result.output)["devices"][0]["node_id"] == "1234"

    state_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "read-state",
            "--node-id",
            "1234",
            "--endpoint-id",
            "1",
        ],
    )
    assert state_result.exit_code == 0
    assert json.loads(state_result.output)["temperature_c"] == 22.4

    registry_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "list-registry",
        ],
    )
    assert registry_result.exit_code == 0
    assert json.loads(registry_result.output)["devices"][0]["node_id"] == "1234"


def test_bridge_cli_discovers_commissionables(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "discover-commissionables",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["devices"][0]["instance_name"] == "1234"
    assert payload["devices"][0]["vendor_id"] == 4447


def test_bridge_cli_invoke_command(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "invoke-command",
            "--node-id",
            "1234",
            "--endpoint-id",
            "1",
            "--command",
            "refresh",
            "--args-json",
            '{"force": true}',
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "refresh"
    assert payload["args"] == {"force": True}


def test_bridge_cli_chip_tool_commission_enriches_common_device_profile(tmp_path) -> None:
    data_file = tmp_path / "chip_tool_registry.json"
    fake_chip_tool = tmp_path / "fake_chip_tool.py"
    _write_fake_chip_tool(fake_chip_tool)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(data_file),
            "--controller-binary",
            str(fake_chip_tool),
            "commission-with-code",
            "--node-id",
            "5555",
            "--setup-payload",
            "MT:PAIRCODE",
            "--device-json",
            '{"endpoint_id":1,"name":"Office Plug"}',
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["vendor_name"] == "TP-Link"
    assert payload["product_name"] == "KP125M"
    assert payload["device_types"] == ["onoff_plug_in_unit"]
    assert payload["capabilities"] == ["switch_on"]
    assert payload["command_bindings"] == ["turn_on", "turn_off", "toggle"]
    assert payload["metadata"]["vendor_id"] == 0x1234
    assert payload["metadata"]["product_id"] == 0x5678


def test_bridge_cli_chip_tool_subscribe_state_streams_json_lines(tmp_path) -> None:
    data_file = tmp_path / "chip_tool_registry.json"
    fake_chip_tool = tmp_path / "fake_chip_tool.py"
    _write_chip_tool_registry(data_file)
    _write_fake_chip_tool(fake_chip_tool)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(data_file),
            "--controller-binary",
            str(fake_chip_tool),
            "subscribe-state",
            "--node-id",
            "8888",
            "--endpoint-id",
            "1",
            "--min-interval-seconds",
            "1",
            "--max-interval-seconds",
            "5",
        ],
    )

    assert result.exit_code == 0
    first_line = json.loads(result.output.splitlines()[0])
    assert first_line["switch_on"] is True
    assert first_line["connected"] is True


def test_bridge_cli_registry_mutations(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    upsert = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "upsert-device",
            "--device-json",
            '{"node_id":"9999","endpoint_id":2,"name":"Garage Sensor"}',
        ],
    )
    assert upsert.exit_code == 0
    assert json.loads(upsert.output)["node_id"] == "9999"

    remove = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "remove-device",
            "--node-id",
            "9999",
            "--endpoint-id",
            "2",
        ],
    )
    assert remove.exit_code == 0
    assert json.loads(remove.output)["removed"] is True


def test_bridge_cli_commission_with_code(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "sample",
            "--data-file",
            str(data_file),
            "commission-with-code",
            "--node-id",
            "5555",
            "--setup-payload",
            "MT:TESTPAYLOAD",
            "--device-json",
            '{"endpoint_id":3,"name":"Hall Sensor"}',
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["node_id"] == "5555"
    assert payload["endpoint_id"] == 3
    assert payload["name"] == "Hall Sensor"


def test_bridge_cli_chip_tool_discovers_commissionables(tmp_path) -> None:
    registry_file = tmp_path / "chip_registry.json"
    fake_chip_tool = tmp_path / "fake_chip_tool.py"
    _write_chip_tool_registry(registry_file)
    _write_fake_chip_tool(fake_chip_tool)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(fake_chip_tool),
            "discover-commissionables",
            "--timeout-seconds",
            "7",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    device = payload["devices"][0]
    assert device["instance_name"] == "AQARA-TEST"
    assert device["vendor_id"] == 4447
    assert device["product_id"] == 1001
    assert device["addresses"] == ["fd00::1234"]


def test_bridge_cli_chip_tool_discovery_timeout(tmp_path) -> None:
    registry_file = tmp_path / "chip_registry.json"
    slow_chip_tool = tmp_path / "slow_chip_tool.py"
    _write_chip_tool_registry(registry_file)
    _write_sleeping_chip_tool(slow_chip_tool)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(slow_chip_tool),
            "discover-commissionables",
            "--timeout-seconds",
            "1",
        ],
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert "timed out after 1 seconds" in str(result.exception)



def test_bridge_cli_chip_tool_backend(tmp_path) -> None:
    registry_file = tmp_path / "chip_tool_registry.json"
    chip_tool_binary = tmp_path / "fake_chip_tool.py"
    _write_chip_tool_registry(registry_file)
    _write_fake_chip_tool(chip_tool_binary)
    runner = CliRunner()

    state_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(chip_tool_binary),
            "read-state",
            "--node-id",
            "8888",
            "--endpoint-id",
            "1",
        ],
    )
    assert state_result.exit_code == 0
    state_payload = json.loads(state_result.output)
    assert state_payload["temperature_c"] == 22.4
    assert state_payload["humidity_percent"] == 41.5
    assert state_payload["switch_on"] is True

    command_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(chip_tool_binary),
            "invoke-command",
            "--node-id",
            "8888",
            "--endpoint-id",
            "1",
            "--command",
            "turn_on",
        ],
    )
    assert command_result.exit_code == 0
    command_payload = json.loads(command_result.output)
    assert command_payload["ok"] is True
    assert command_payload["command"] == "turn_on"

    commission_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(chip_tool_binary),
            "commission-with-code",
            "--node-id",
            "9999",
            "--setup-payload",
            "MT:PAIRCODE",
            "--device-json",
            '{"endpoint_id":2,"name":"Commissioned Sensor"}',
        ],
    )
    assert commission_result.exit_code == 0
    commission_payload = json.loads(commission_result.output)
    assert commission_payload["node_id"] == "9999"
    assert commission_payload["endpoint_id"] == 2


def test_bridge_cli_chip_tool_commission_can_create_registry_from_empty_state(tmp_path) -> None:
    registry_file = tmp_path / "empty_chip_tool_registry.json"
    chip_tool_binary = tmp_path / "fake_chip_tool.py"
    _write_fake_chip_tool(chip_tool_binary)
    runner = CliRunner()

    commission_result = runner.invoke(
        main,
        [
            "--backend-kind",
            "chip-tool",
            "--data-file",
            str(registry_file),
            "--controller-binary",
            str(chip_tool_binary),
            "commission-with-code",
            "--node-id",
            "7777",
            "--setup-payload",
            "MT:PAIRCODE",
            "--device-json",
            '{"endpoint_id":1,"name":"Fresh Device"}',
        ],
    )

    assert commission_result.exit_code == 0
    payload = json.loads(commission_result.output)
    assert payload["node_id"] == "7777"
    assert registry_file.exists() is True
    registry = json.loads(registry_file.read_text())
    assert registry[0]["node_id"] == "7777"
