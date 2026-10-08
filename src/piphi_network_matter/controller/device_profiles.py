from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

DEVICE_TYPE_NAMES: dict[int, str] = {
    21: "contact_sensor",
    65: "water_freeze_detector",
    67: "water_leak_detector",
    118: "smoke_co_alarm",
    256: "onoff_light",
    257: "dimmable_light",
    262: "light_sensor",
    263: "occupancy_sensor",
    266: "onoff_plug_in_unit",
    267: "dimmable_plug_in_unit",
    770: "temperature_sensor",
    775: "humidity_sensor",
    2128: "onoff_sensor",
}

DEVICE_TYPE_ALIASES: dict[str, str] = {
    "on_off_light": "onoff_light",
    "on_off_plug_in_unit": "onoff_plug_in_unit",
    "on_off_sensor": "onoff_sensor",
    "dimmable_plug_in_unit": "dimmable_plug_in_unit",
}

CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "switch_on": {
        "label": "Power",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["tile", "status-list", "availability-card"],
            "default_widget": "tile",
            "recommended_widgets": ["tile"],
        },
    },
    "brightness_percent": {
        "label": "Brightness",
        "kind": "sensor",
        "state_type": "number",
        "unit": "%",
        "dashboard": {
            "allowed_widgets": ["light-card", "gauge", "sensor-card"],
            "default_widget": "gauge",
            "recommended_widgets": ["gauge"],
        },
    },
    "temperature_c": {
        "label": "Temperature",
        "kind": "sensor",
        "state_type": "number",
        "unit": "°C",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart", "gauge", "room-climate-card"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card", "line-chart"],
        },
    },
    "humidity_percent": {
        "label": "Humidity",
        "kind": "sensor",
        "state_type": "number",
        "unit": "%",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart", "gauge", "room-climate-card"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card", "line-chart"],
        },
    },
    "battery_percent": {
        "label": "Battery",
        "kind": "sensor",
        "state_type": "number",
        "unit": "%",
        "dashboard": {
            "allowed_widgets": ["device-health-card", "battery-fleet-card", "sensor-card"],
            "default_widget": "device-health-card",
            "recommended_widgets": ["device-health-card"],
        },
    },
    "contact_open": {
        "label": "Contact Open",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["access-control-card", "status-list"],
            "default_widget": "access-control-card",
            "recommended_widgets": ["access-control-card"],
        },
    },
    "smoke_alarm": {
        "label": "Smoke Alarm",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "carbon_monoxide_alarm": {
        "label": "Carbon Monoxide Alarm",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "leak_detected": {
        "label": "Water Leak",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "freeze_detected": {
        "label": "Freeze Risk",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "occupancy_detected": {
        "label": "Occupancy",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["presence-card", "status-list"],
            "default_widget": "presence-card",
            "recommended_widgets": ["presence-card"],
        },
    },
    "illuminance_raw": {
        "label": "Illuminance",
        "kind": "sensor",
        "state_type": "number",
        "unit": "lux",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card", "line-chart"],
        },
    },
    "sensor_on": {
        "label": "State",
        "kind": "state",
        "state_type": "boolean",
        "dashboard": {
            "allowed_widgets": ["availability-card", "status-list"],
            "default_widget": "availability-card",
            "recommended_widgets": ["availability-card"],
        },
    },
}

COMMAND_CATALOG: dict[str, dict[str, Any]] = {
    "turn_on": {
        "label": "Turn On",
        "description": "Turn the device on.",
        "kind": "primary",
        "args_schema": {},
    },
    "turn_off": {
        "label": "Turn Off",
        "description": "Turn the device off.",
        "kind": "secondary",
        "args_schema": {},
    },
    "toggle": {
        "label": "Toggle",
        "description": "Toggle the device state.",
        "kind": "primary",
        "args_schema": {},
    },
    "refresh": {
        "label": "Refresh",
        "description": "Refresh the latest device state.",
        "kind": "secondary",
        "args_schema": {},
    },
}

DEVICE_TYPE_PRESENTATION: dict[str, dict[str, Any]] = {
    "temperature_sensor": {
        "device_class": "sensor",
        "entity_type": "sensor",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart", "room-climate-card"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        },
    },
    "humidity_sensor": {
        "device_class": "sensor",
        "entity_type": "sensor",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart", "room-climate-card"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        },
    },
    "contact_sensor": {
        "device_class": "contact",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["access-control-card", "status-list"],
            "default_widget": "access-control-card",
            "recommended_widgets": ["access-control-card"],
        },
    },
    "smoke_co_alarm": {
        "device_class": "safety",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "water_leak_detector": {
        "device_class": "safety",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "water_freeze_detector": {
        "device_class": "safety",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["safety-overview-card", "status-list"],
            "default_widget": "safety-overview-card",
            "recommended_widgets": ["safety-overview-card"],
        },
    },
    "occupancy_sensor": {
        "device_class": "occupancy",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["presence-card", "status-list"],
            "default_widget": "presence-card",
            "recommended_widgets": ["presence-card"],
        },
    },
    "light_sensor": {
        "device_class": "sensor",
        "entity_type": "sensor",
        "dashboard": {
            "allowed_widgets": ["sensor-card", "line-chart"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        },
    },
    "onoff_sensor": {
        "device_class": "binary_sensor",
        "entity_type": "binary_sensor",
        "dashboard": {
            "allowed_widgets": ["availability-card", "status-list"],
            "default_widget": "availability-card",
            "recommended_widgets": ["availability-card"],
        },
    },
    "onoff_light": {
        "device_class": "light",
        "entity_type": "light",
        "dashboard": {
            "allowed_widgets": ["light-card", "tile", "status-list"],
            "default_widget": "light-card",
            "recommended_widgets": ["light-card"],
        },
    },
    "onoff_plug_in_unit": {
        "device_class": "plug",
        "entity_type": "switch",
        "dashboard": {
            "allowed_widgets": ["tile", "status-list", "availability-card"],
            "default_widget": "tile",
            "recommended_widgets": ["tile"],
        },
    },
    "dimmable_light": {
        "device_class": "light",
        "entity_type": "light",
        "dashboard": {
            "allowed_widgets": ["light-card", "tile", "gauge", "status-list"],
            "default_widget": "light-card",
            "recommended_widgets": ["light-card"],
        },
    },
    "dimmable_plug_in_unit": {
        "device_class": "plug",
        "entity_type": "switch",
        "dashboard": {
            "allowed_widgets": ["tile", "gauge", "status-list"],
            "default_widget": "tile",
            "recommended_widgets": ["tile"],
        },
    },
}


DEVICE_PROFILES: dict[str, dict[str, Any]] = {
    "temperature_sensor": {
        "capabilities": ["temperature_c"],
        "chip_tool_reads": {
            "temperature_c": {
                "cluster": "temperaturemeasurement",
                "attribute": "measured-value",
                "value_regex": r"(?:MeasuredValue|Data)\s*[:=]\s*(-?\d+)",
                "transform": "centi",
            }
        },
    },
    "humidity_sensor": {
        "capabilities": ["humidity_percent"],
        "chip_tool_reads": {
            "humidity_percent": {
                "cluster": "relativehumiditymeasurement",
                "attribute": "measured-value",
                "value_regex": r"(?:MeasuredValue|Data)\s*[:=]\s*(\d+)",
                "transform": "centi",
            }
        },
    },
    "contact_sensor": {
        "capabilities": ["contact_open"],
        "chip_tool_reads": {
            "contact_open": {
                "cluster": "booleanstate",
                "attribute": "state-value",
                "value_regex": r"(?:StateValue|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
    },
    "smoke_co_alarm": {
        "capabilities": ["smoke_alarm", "carbon_monoxide_alarm"],
        "chip_tool_reads": {
            "smoke_alarm": {
                "cluster": "smokecoalarm",
                "attribute": "smoke-state",
                "value_regex": r"(?:SmokeState|Data)\s*[:=]\s*(\d+)",
                "transform": "nonzero_bool",
            },
            "carbon_monoxide_alarm": {
                "cluster": "smokecoalarm",
                "attribute": "co-state",
                "value_regex": r"(?:COState|Data)\s*[:=]\s*(\d+)",
                "transform": "nonzero_bool",
            },
        },
    },
    "water_leak_detector": {
        "capabilities": ["leak_detected"],
        "chip_tool_reads": {
            "leak_detected": {
                "cluster": "booleanstate",
                "attribute": "state-value",
                "value_regex": r"(?:StateValue|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
    },
    "water_freeze_detector": {
        "capabilities": ["freeze_detected"],
        "chip_tool_reads": {
            "freeze_detected": {
                "cluster": "booleanstate",
                "attribute": "state-value",
                "value_regex": r"(?:StateValue|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
    },
    "occupancy_sensor": {
        "capabilities": ["occupancy_detected"],
        "chip_tool_reads": {
            "occupancy_detected": {
                "cluster": "occupancysensing",
                "attribute": "occupancy",
                "value_regex": r"(?:Occupancy|Data)\s*[:=]\s*(\d+)",
                "transform": "nonzero_bool",
            }
        },
    },
    "light_sensor": {
        "capabilities": ["illuminance_raw"],
        "chip_tool_reads": {
            "illuminance_raw": {
                "cluster": "illuminancemeasurement",
                "attribute": "measured-value",
                "value_regex": r"(?:MeasuredValue|Data)\s*[:=]\s*(\d+)",
                "transform": "int",
            }
        },
    },
    "onoff_sensor": {
        "capabilities": ["sensor_on"],
        "chip_tool_reads": {
            "sensor_on": {
                "cluster": "booleanstate",
                "attribute": "state-value",
                "value_regex": r"(?:StateValue|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
    },
    "onoff_light": {
        "capabilities": ["switch_on"],
        "command_bindings": ["turn_on", "turn_off", "toggle"],
        "chip_tool_reads": {
            "switch_on": {
                "cluster": "onoff",
                "attribute": "on-off",
                "value_regex": r"(?:OnOff|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
        "chip_tool_commands": {
            "turn_on": {"cluster": "onoff", "command": "on"},
            "turn_off": {"cluster": "onoff", "command": "off"},
            "toggle": {"cluster": "onoff", "command": "toggle"},
        },
    },
    "onoff_plug_in_unit": {
        "capabilities": ["switch_on"],
        "command_bindings": ["turn_on", "turn_off", "toggle"],
        "chip_tool_reads": {
            "switch_on": {
                "cluster": "onoff",
                "attribute": "on-off",
                "value_regex": r"(?:OnOff|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            }
        },
        "chip_tool_commands": {
            "turn_on": {"cluster": "onoff", "command": "on"},
            "turn_off": {"cluster": "onoff", "command": "off"},
            "toggle": {"cluster": "onoff", "command": "toggle"},
        },
    },
    "dimmable_light": {
        "capabilities": ["switch_on", "brightness_percent"],
        "command_bindings": ["turn_on", "turn_off", "toggle"],
        "chip_tool_reads": {
            "switch_on": {
                "cluster": "onoff",
                "attribute": "on-off",
                "value_regex": r"(?:OnOff|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            },
            "brightness_percent": {
                "cluster": "levelcontrol",
                "attribute": "current-level",
                "value_regex": r"(?:CurrentLevel|Data)\s*[:=]\s*(\d+)",
                "transform": "level_percent_254",
            },
        },
        "chip_tool_commands": {
            "turn_on": {"cluster": "onoff", "command": "on"},
            "turn_off": {"cluster": "onoff", "command": "off"},
            "toggle": {"cluster": "onoff", "command": "toggle"},
        },
    },
    "dimmable_plug_in_unit": {
        "capabilities": ["switch_on", "brightness_percent"],
        "command_bindings": ["turn_on", "turn_off", "toggle"],
        "chip_tool_reads": {
            "switch_on": {
                "cluster": "onoff",
                "attribute": "on-off",
                "value_regex": r"(?:OnOff|Data)\s*[:=]\s*(true|false)",
                "transform": "bool",
            },
            "brightness_percent": {
                "cluster": "levelcontrol",
                "attribute": "current-level",
                "value_regex": r"(?:CurrentLevel|Data)\s*[:=]\s*(\d+)",
                "transform": "level_percent_254",
            },
        },
        "chip_tool_commands": {
            "turn_on": {"cluster": "onoff", "command": "on"},
            "turn_off": {"cluster": "onoff", "command": "off"},
            "toggle": {"cluster": "onoff", "command": "toggle"},
        },
    },
}


def normalize_device_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return DEVICE_TYPE_NAMES.get(int(value))
    token = str(value).strip()
    if not token:
        return None
    parsed_int = _parse_device_type_int(token)
    if parsed_int is not None:
        return DEVICE_TYPE_NAMES.get(parsed_int)
    lowered = token.lower().replace("-", "_").replace("/", "_")
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    lowered = DEVICE_TYPE_ALIASES.get(lowered, lowered)
    if lowered in DEVICE_PROFILES:
        return lowered
    return None


def apply_device_profile(device: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(device)
    resolved_types = _resolve_device_types(normalized)
    if resolved_types:
        normalized["device_types"] = resolved_types

    capabilities = list(normalized.get("capabilities") or [])
    command_bindings = list(normalized.get("command_bindings") or [])
    chip_tool_reads = dict(normalized.get("chip_tool_reads") or {})
    chip_tool_commands = dict(normalized.get("chip_tool_commands") or {})

    applied_profiles: list[str] = []
    for device_type in resolved_types:
        profile = DEVICE_PROFILES.get(device_type)
        if not isinstance(profile, dict):
            continue
        applied_profiles.append(device_type)
        capabilities = _merge_unique(capabilities, profile.get("capabilities") or [])
        command_bindings = _merge_unique(command_bindings, profile.get("command_bindings") or [])
        chip_tool_reads = _merge_mapping(chip_tool_reads, profile.get("chip_tool_reads"))
        chip_tool_commands = _merge_mapping(chip_tool_commands, profile.get("chip_tool_commands"))

    if capabilities:
        normalized["capabilities"] = capabilities
    if command_bindings:
        normalized["command_bindings"] = command_bindings
    if chip_tool_reads:
        normalized["chip_tool_reads"] = chip_tool_reads
    if chip_tool_commands:
        normalized["chip_tool_commands"] = chip_tool_commands

    metadata = dict(normalized.get("metadata") or {})
    if applied_profiles:
        metadata["device_profiles"] = applied_profiles
        normalized["metadata"] = metadata
    return normalized


def describe_capability(capability_id: str) -> dict[str, Any]:
    token = str(capability_id or "").strip()
    if not token:
        return {}

    payload = deepcopy(CAPABILITY_CATALOG.get(token) or _infer_capability_payload(token))
    payload["id"] = token
    return payload


def describe_command(command_id: str) -> dict[str, Any]:
    token = str(command_id or "").strip()
    if not token:
        return {}

    payload = deepcopy(
        COMMAND_CATALOG.get(token)
        or {
            "label": _humanize_token(token),
            "description": None,
            "kind": "action",
            "args_schema": {},
        }
    )
    payload["id"] = token
    return payload


def describe_entity(
    *,
    device_types: list[str],
    capabilities: list[str],
    command_bindings: list[str],
) -> dict[str, Any]:
    presentation = next(
        (deepcopy(DEVICE_TYPE_PRESENTATION[device_type]) for device_type in device_types if device_type in DEVICE_TYPE_PRESENTATION),
        {},
    )
    dashboard = _merge_dashboards(
        [
            presentation.get("dashboard"),
            *(describe_capability(capability_id).get("dashboard") for capability_id in capabilities),
        ]
    )
    return {
        "device_class": presentation.get("device_class") or _infer_device_class(capabilities, command_bindings),
        "entity_type": presentation.get("entity_type") or _infer_entity_type(capabilities, command_bindings),
        "dashboard": dashboard,
    }


def _resolve_device_types(device: dict[str, Any]) -> list[str]:
    resolved: list[str] = []
    for item in list(device.get("device_types") or []):
        normalized = normalize_device_type(item)
        if normalized and normalized not in resolved:
            resolved.append(normalized)

    top_level_device_type = normalize_device_type(device.get("device_type"))
    if top_level_device_type and top_level_device_type not in resolved:
        resolved.append(top_level_device_type)

    metadata = dict(device.get("metadata") or {})
    metadata_device_type = normalize_device_type(metadata.get("device_type"))
    if metadata_device_type and metadata_device_type not in resolved:
        resolved.append(metadata_device_type)

    for item in list(metadata.get("device_type_list") or []):
        normalized = normalize_device_type(item)
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _parse_device_type_int(value: str) -> int | None:
    token = str(value).strip()
    if not token:
        return None
    try:
        if token.lower().startswith("0x"):
            return int(token, 16)
        if token.isdigit():
            return int(token)
    except ValueError:
        return None
    return None


def _merge_unique(existing: list[Any], additions: list[Any]) -> list[Any]:
    merged = [item for item in existing]
    seen = {str(item) for item in merged}
    for item in additions:
        if str(item) in seen:
            continue
        merged.append(item)
        seen.add(str(item))
    return merged


def _merge_mapping(existing: dict[str, Any], additions: Any) -> dict[str, Any]:
    merged = dict(existing)
    if not isinstance(additions, dict):
        return merged
    for key, value in additions.items():
        if key not in merged:
            merged[key] = deepcopy(value)
    return merged


def _infer_capability_payload(capability_id: str) -> dict[str, Any]:
    lowered = capability_id.lower()
    payload: dict[str, Any] = {
        "label": _humanize_token(capability_id),
        "kind": "sensor",
        "state_type": "text",
        "dashboard": {
            "allowed_widgets": ["status-list", "sensor-card"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        },
    }
    if lowered.endswith("_percent"):
        payload["state_type"] = "number"
        payload["unit"] = "%"
        payload["dashboard"] = {
            "allowed_widgets": ["sensor-card", "gauge"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        }
    elif lowered.endswith("_c"):
        payload["state_type"] = "number"
        payload["unit"] = "°C"
        payload["dashboard"] = {
            "allowed_widgets": ["sensor-card", "line-chart", "gauge"],
            "default_widget": "sensor-card",
            "recommended_widgets": ["sensor-card"],
        }
    elif lowered.endswith(("_on", "_open", "_detected")):
        payload["kind"] = "state"
        payload["state_type"] = "boolean"
        payload["dashboard"] = {
            "allowed_widgets": ["availability-card", "status-list"],
            "default_widget": "availability-card",
            "recommended_widgets": ["availability-card"],
        }
    return payload


def _infer_device_class(capabilities: list[str], command_bindings: list[str]) -> str:
    if any(command_id in {"turn_on", "turn_off", "toggle"} for command_id in command_bindings):
        return "switch"
    if any(capability_id in {"contact_open"} for capability_id in capabilities):
        return "contact"
    if any(capability_id in {"occupancy_detected"} for capability_id in capabilities):
        return "occupancy"
    if any(capability_id.endswith(("_on", "_open", "_detected")) for capability_id in capabilities):
        return "binary_sensor"
    return "sensor"


def _infer_entity_type(capabilities: list[str], command_bindings: list[str]) -> str:
    if any(command_id in {"turn_on", "turn_off", "toggle"} for command_id in command_bindings):
        return "switch"
    if any(capability_id.endswith(("_on", "_open", "_detected")) for capability_id in capabilities):
        return "binary_sensor"
    return "sensor"


def _merge_dashboards(dashboards: list[Any]) -> dict[str, Any] | None:
    allowed_widgets: list[str] = []
    recommended_widgets: list[str] = []
    default_widget: str | None = None

    for dashboard in dashboards:
        if not isinstance(dashboard, dict):
            continue
        for widget in dashboard.get("allowed_widgets") or []:
            token = str(widget or "").strip()
            if token and token not in allowed_widgets:
                allowed_widgets.append(token)
        for widget in dashboard.get("recommended_widgets") or []:
            token = str(widget or "").strip()
            if token and token not in recommended_widgets:
                recommended_widgets.append(token)
        if default_widget is None:
            candidate = str(dashboard.get("default_widget") or "").strip() or None
            if candidate:
                default_widget = candidate

    if default_widget and default_widget not in allowed_widgets:
        allowed_widgets.append(default_widget)
    if default_widget and default_widget not in recommended_widgets:
        recommended_widgets.insert(0, default_widget)

    if not allowed_widgets and default_widget is None and not recommended_widgets:
        return None
    return {
        "allowed_widgets": allowed_widgets,
        "default_widget": default_widget,
        "recommended_widgets": recommended_widgets,
    }


def _humanize_token(value: str) -> str:
    cleaned = str(value or "").strip().replace("_", " ").replace("-", " ")
    if not cleaned:
        return "Unknown"
    return cleaned[:1].upper() + cleaned[1:]
