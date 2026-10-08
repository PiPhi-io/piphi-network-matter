from __future__ import annotations

import json
from pathlib import Path

import pytest

from piphi_network_matter.controller.bridge_backend import ChipToolBridgeBackend
from piphi_network_matter.controller.device_profiles import (
    apply_device_profile,
    describe_entity,
)


@pytest.mark.parametrize(
    ("device_type", "resolved_type", "capabilities"),
    [
        ("0x0076", "smoke_co_alarm", ["smoke_alarm", "carbon_monoxide_alarm"]),
        (67, "water_leak_detector", ["leak_detected"]),
        ("0x0041", "water_freeze_detector", ["freeze_detected"]),
    ],
)
def test_safety_device_types_negotiate_expected_capabilities(
    device_type: str | int,
    resolved_type: str,
    capabilities: list[str],
) -> None:
    device = apply_device_profile({"device_type": device_type})

    assert device["device_types"] == [resolved_type]
    assert device["capabilities"] == capabilities
    assert device["metadata"]["device_profiles"] == [resolved_type]
    assert set(device["chip_tool_reads"]) == set(capabilities)


def test_smoke_co_states_preserve_normal_warning_and_critical_semantics(tmp_path: Path) -> None:
    backend = ChipToolBridgeBackend(data_file=str(tmp_path / "devices.json"))
    device = apply_device_profile({"device_type": "0x0076"})
    smoke_spec = device["chip_tool_reads"]["smoke_alarm"]
    co_spec = device["chip_tool_reads"]["carbon_monoxide_alarm"]

    assert backend._extract_read_value("SmokeState: 0", smoke_spec) is False
    assert backend._extract_read_value("SmokeState: 1", smoke_spec) is True
    assert backend._extract_read_value("SmokeState: 2", smoke_spec) is True
    assert backend._extract_read_value("COState: 0", co_spec) is False
    assert backend._extract_read_value("COState: 2", co_spec) is True


@pytest.mark.parametrize(
    ("device_type", "expected_capability"),
    [
        ("0x0043", "leak_detected"),
        ("0x0041", "freeze_detected"),
    ],
)
def test_boolean_safety_states_normalize_chip_tool_output(
    tmp_path: Path,
    device_type: str,
    expected_capability: str,
) -> None:
    backend = ChipToolBridgeBackend(data_file=str(tmp_path / "devices.json"))
    device = apply_device_profile({"device_type": device_type})
    spec = device["chip_tool_reads"][expected_capability]

    assert backend._extract_read_value("StateValue: false", spec) is False
    assert backend._extract_read_value("StateValue: true", spec) is True


def test_safety_entities_use_a_concise_safety_presentation() -> None:
    entity = describe_entity(
        device_types=["smoke_co_alarm"],
        capabilities=["smoke_alarm", "carbon_monoxide_alarm"],
        command_bindings=[],
    )

    assert entity == {
        "device_class": "safety",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    }


def test_contact_sensor_remains_routine_state_not_a_safety_alarm() -> None:
    device = apply_device_profile({"device_type": "0x0015"})

    assert device["device_types"] == ["contact_sensor"]
    assert device["capabilities"] == ["contact_open"]
    assert not {"smoke_alarm", "carbon_monoxide_alarm", "leak_detected", "freeze_detected"}.intersection(
        device["capabilities"]
    )


def test_manifest_describes_current_security_delivery_boundary() -> None:
    manifest_path = Path(__file__).parents[1] / "src" / "manifest.json"
    mappings = json.loads(manifest_path.read_text(encoding="utf-8"))["security"]["event_mappings"]
    implemented = [mapping for mapping in mappings if mapping["status"] == "implemented"]
    excluded = [mapping for mapping in mappings if mapping["status"] == "excluded"]

    assert len(implemented) == 8
    assert all(mapping.get("canonical_event_type") for mapping in implemented)
    assert all(mapping["device_models"] and mapping["required_permissions"] for mapping in mappings)
    assert [mapping["source_event_type"] for mapping in excluded] == ["matter.contact.opened"]
    assert not any(mapping["status"] == "planned" for mapping in mappings)
