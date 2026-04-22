from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class MatterConfiguredDevice:
    node_id: str
    endpoint_id: int
    alias: str | None = None
    enabled: bool = True
    preferred_source: str = "matter"

    def config_key(self) -> str:
        return f"{self.node_id}:{self.endpoint_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "endpoint_id": self.endpoint_id,
            "alias": self.alias,
            "enabled": self.enabled,
            "preferred_source": self.preferred_source,
        }


@dataclass(slots=True)
class MatterDevice:
    node_id: str
    endpoint_id: int
    name: str
    vendor_name: str | None = None
    product_name: str | None = None
    device_types: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    command_bindings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def config_key(self) -> str:
        return f"{self.node_id}:{self.endpoint_id}"

    def discovery_record(self) -> dict[str, Any]:
        return {
            "id": self.config_key(),
            "device_id": self.config_key(),
            "node_id": self.node_id,
            "endpoint_id": self.endpoint_id,
            "name": self.name,
            "vendor_name": self.vendor_name,
            "product_name": self.product_name,
            "device_types": list(self.device_types),
            "capabilities": list(self.capabilities),
            "command_bindings": list(self.command_bindings),
            "metadata": {
                **self.metadata,
                "node_id": self.node_id,
                "endpoint_id": self.endpoint_id,
            },
        }


def sampled_state(
    state: dict[str, Any] | None = None,
    *,
    connected: bool = True,
    sampled_at: str | None = None,
) -> dict[str, Any]:
    return {
        **dict(state or {}),
        "connected": connected,
        "sampled_at": sampled_at or datetime.now(tz=UTC).isoformat(),
    }
