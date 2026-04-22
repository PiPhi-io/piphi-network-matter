from __future__ import annotations

import json

from click.testing import CliRunner

from piphi_network_matter.cli import main


def _write_sample_devices(path) -> None:
    path.write_text(
        json.dumps(
            [
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
                }
            ],
            indent=2,
            sort_keys=True,
        )
    )


def test_print_config_outputs_resolved_config() -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "print-config",
            "--adapter-kind",
            "sample",
            "--poll-interval-seconds",
            "12",
            "--storage-dir",
            "/tmp/matter",
            "--adapter-data-file",
            "/tmp/matter/devices.json",
            "--api-host",
            "0.0.0.0",
            "--api-port",
            "8715",
            "--log-level",
            "debug",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["adapter_kind"] == "sample"
    assert payload["poll_interval_seconds"] == 12.0
    assert payload["storage_dir"] == "/tmp/matter"
    assert payload["adapter_data_file"] == "/tmp/matter/devices.json"
    assert payload["adapter_command"] is None
    assert payload["api_host"] == "0.0.0.0"
    assert payload["api_port"] == 8715
    assert payload["log_level"] == "DEBUG"


def test_run_dry_run_outputs_resolved_config() -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "run",
            "--adapter-kind",
            "null",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["adapter_kind"] == "null"
    assert payload["adapter_data_file"] is None
    assert payload["adapter_command"] is None
    assert payload["api_host"] == "127.0.0.1"
    assert payload["api_port"] == 8710


def test_serve_api_dry_run_outputs_resolved_config() -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "serve-api",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            "/tmp/matter/devices.json",
            "--adapter-command",
            "/tmp/matter/fake-controller",
            "--api-host",
            "0.0.0.0",
            "--api-port",
            "8760",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["adapter_kind"] == "sample"
    assert payload["adapter_data_file"] == "/tmp/matter/devices.json"
    assert payload["adapter_command"] == "/tmp/matter/fake-controller"
    assert payload["api_host"] == "0.0.0.0"
    assert payload["api_port"] == 8760


def test_discover_configure_and_poll_once_commands(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    storage_dir = tmp_path / "matter_state"
    _write_sample_devices(data_file)
    runner = CliRunner()

    discover_result = runner.invoke(
        main,
        [
            "discover",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(storage_dir),
        ],
    )
    assert discover_result.exit_code == 0
    discovered = json.loads(discover_result.output)
    assert discovered[0]["device_id"] == "1234:1"

    commissionables_result = runner.invoke(
        main,
        [
            "discover-commissionables",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(storage_dir),
            "--timeout-seconds",
            "6",
        ],
    )
    assert commissionables_result.exit_code == 0
    commissionables = json.loads(commissionables_result.output)
    assert commissionables[0]["instance_name"] == "1234"

    configure_result = runner.invoke(
        main,
        [
            "configure",
            "1234",
            "1",
            "--alias",
            "Office climate",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(storage_dir),
        ],
    )
    assert configure_result.exit_code == 0
    configured = json.loads(configure_result.output)
    assert configured["alias"] == "Office climate"

    configs_result = runner.invoke(
        main,
        [
            "configs",
            "--storage-dir",
            str(storage_dir),
        ],
    )
    assert configs_result.exit_code == 0
    configs = json.loads(configs_result.output)
    assert configs == [
        {
            "alias": "Office climate",
            "enabled": True,
            "endpoint_id": 1,
            "node_id": "1234",
            "preferred_source": "matter",
        }
    ]

    poll_result = runner.invoke(
        main,
        [
            "poll-once",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(storage_dir),
        ],
    )
    assert poll_result.exit_code == 0
    telemetry_batch = json.loads(poll_result.output)
    assert telemetry_batch[0]["config_key"] == "1234:1"
    assert telemetry_batch[0]["read_failed"] is False
    assert telemetry_batch[0]["state"]["temperature_c"] == 22.4


def test_registry_commands(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    list_result = runner.invoke(
        main,
        [
            "registry-list",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(tmp_path / "state"),
        ],
    )
    assert list_result.exit_code == 0
    assert json.loads(list_result.output)[0]["node_id"] == "1234"

    upsert_result = runner.invoke(
        main,
        [
            "registry-upsert",
            "--device-json",
            '{"node_id":"7777","endpoint_id":4,"name":"Patio Sensor"}',
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(tmp_path / "state"),
        ],
    )
    assert upsert_result.exit_code == 0
    assert json.loads(upsert_result.output)["node_id"] == "7777"

    remove_result = runner.invoke(
        main,
        [
            "registry-remove",
            "7777",
            "4",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(tmp_path / "state"),
        ],
    )
    assert remove_result.exit_code == 0
    assert json.loads(remove_result.output)["removed"] is True


def test_commission_code_command(tmp_path) -> None:
    data_file = tmp_path / "sample_devices.json"
    _write_sample_devices(data_file)
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "commission-code",
            "5555",
            "MT:TESTPAYLOAD",
            "--endpoint-id",
            "2",
            "--name",
            "Patio Sensor",
            "--adapter-kind",
            "sample",
            "--adapter-data-file",
            str(data_file),
            "--storage-dir",
            str(tmp_path / "state"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["node_id"] == "5555"
    assert payload["endpoint_id"] == 2
    assert payload["name"] == "Patio Sensor"

    configs_result = runner.invoke(
        main,
        [
            "configs",
            "--storage-dir",
            str(tmp_path / "state"),
        ],
    )
    assert configs_result.exit_code == 0
    assert any(item["node_id"] == "5555" and item["endpoint_id"] == 2 for item in json.loads(configs_result.output))
