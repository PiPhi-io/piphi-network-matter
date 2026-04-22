from __future__ import annotations

from piphi_network_matter.config import (
    DEFAULT_ADAPTER_KIND,
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_AUTO_CONFIGURE_COMMISSIONED_DEVICES,
    DEFAULT_LOG_LEVEL,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_STORAGE_DIR,
    config_to_dict,
    load_sidecar_config,
)


def test_load_sidecar_config_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("MATTER_ADAPTER_KIND", raising=False)
    monkeypatch.delenv("MATTER_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("MATTER_STORAGE_DIR", raising=False)
    monkeypatch.delenv("MATTER_ADAPTER_DATA_FILE", raising=False)
    monkeypatch.delenv("MATTER_ADAPTER_COMMAND", raising=False)
    monkeypatch.delenv("MATTER_AUTO_CONFIGURE_COMMISSIONED_DEVICES", raising=False)
    monkeypatch.delenv("MATTER_API_HOST", raising=False)
    monkeypatch.delenv("MATTER_API_PORT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    config = load_sidecar_config()

    assert config.log_level == DEFAULT_LOG_LEVEL
    assert config.adapter_kind == DEFAULT_ADAPTER_KIND
    assert config.poll_interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS
    assert config.storage_dir == DEFAULT_STORAGE_DIR
    assert config.adapter_data_file is None
    assert config.adapter_command is None
    assert config.auto_configure_commissioned_devices == DEFAULT_AUTO_CONFIGURE_COMMISSIONED_DEVICES
    assert config.api_host == DEFAULT_API_HOST
    assert config.api_port == DEFAULT_API_PORT


def test_config_to_dict_contains_expected_keys(monkeypatch) -> None:
    monkeypatch.setenv("MATTER_ADAPTER_KIND", "chip")
    monkeypatch.setenv("MATTER_POLL_INTERVAL_SECONDS", "12")
    monkeypatch.setenv("MATTER_STORAGE_DIR", "/tmp/matter")
    monkeypatch.setenv("MATTER_ADAPTER_DATA_FILE", "/tmp/matter/devices.json")
    monkeypatch.setenv("MATTER_ADAPTER_COMMAND", "/tmp/matter/fake-matter-controller")
    monkeypatch.setenv("MATTER_AUTO_CONFIGURE_COMMISSIONED_DEVICES", "false")
    monkeypatch.setenv("MATTER_API_HOST", "0.0.0.0")
    monkeypatch.setenv("MATTER_API_PORT", "8715")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    config = load_sidecar_config()
    payload = config_to_dict(config)

    assert payload == {
        "log_level": "DEBUG",
        "adapter_kind": "chip",
        "poll_interval_seconds": 12.0,
        "storage_dir": "/tmp/matter",
        "adapter_data_file": "/tmp/matter/devices.json",
        "adapter_command": "/tmp/matter/fake-matter-controller",
        "auto_configure_commissioned_devices": False,
        "api_host": "0.0.0.0",
        "api_port": 8715,
    }
