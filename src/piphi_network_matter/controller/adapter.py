from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import shlex
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

from .device_profiles import apply_device_profile
from .models import MatterDevice, sampled_state


class MatterAdapterError(RuntimeError):
    pass


class MatterAdapter(Protocol):
    async def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]: ...
    async def list_devices(self) -> list[MatterDevice]: ...
    async def list_registry(self) -> list[dict[str, Any]]: ...
    async def upsert_registry_device(self, *, device: dict[str, Any]) -> dict[str, Any]: ...
    async def remove_registry_device(self, *, node_id: str, endpoint_id: int) -> bool: ...
    async def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    async def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]: ...
    async def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    def supports_state_subscriptions(self) -> bool: ...
    async def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> AsyncIterator[dict[str, Any]]: ...
    async def aclose(self) -> None: ...


class NullMatterAdapter:
    async def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        del timeout_seconds
        return []

    async def list_devices(self) -> list[MatterDevice]:
        return []

    async def list_registry(self) -> list[dict[str, Any]]:
        return []

    async def upsert_registry_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        del device
        raise MatterAdapterError("No Matter controller adapter has been configured yet.")

    async def remove_registry_device(self, *, node_id: str, endpoint_id: int) -> bool:
        del node_id, endpoint_id
        raise MatterAdapterError("No Matter controller adapter has been configured yet.")

    async def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del node_id, setup_payload, device
        raise MatterAdapterError("No Matter controller adapter has been configured yet.")

    async def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        del node_id, endpoint_id
        return sampled_state({}, connected=False)

    async def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del node_id, endpoint_id, command, args
        raise MatterAdapterError("No Matter controller adapter has been configured yet.")

    def supports_state_subscriptions(self) -> bool:
        return False

    async def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> AsyncIterator[dict[str, Any]]:
        del node_id, endpoint_id, min_interval_seconds, max_interval_seconds
        raise MatterAdapterError("No Matter controller adapter has been configured yet.")

    async def aclose(self) -> None:
        return None


class SampleMatterAdapter:
    def __init__(self, *, data_file: str | None) -> None:
        if not data_file:
            raise MatterAdapterError(
                "The 'sample' Matter adapter requires MATTER_ADAPTER_DATA_FILE or --adapter-data-file."
            )
        self.data_file = Path(data_file)

    async def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        del timeout_seconds
        results: list[dict[str, Any]] = []
        for item in self._load_payload():
            results.append(
                {
                    "instance_name": str(item.get("instance_name") or item.get("node_id")),
                    "vendor_id": item.get("metadata", {}).get("vendor_id"),
                    "product_id": item.get("metadata", {}).get("product_id"),
                    "device_type": (item.get("device_types") or [None])[0],
                    "long_discriminator": item.get("metadata", {}).get("long_discriminator"),
                    "commissioning_mode": 1,
                    "name": item.get("name"),
                    "addresses": list(item.get("metadata", {}).get("addresses") or []),
                    "metadata": {
                        "source": "sample-adapter",
                    },
                }
            )
        return results

    async def list_devices(self) -> list[MatterDevice]:
        return [_device_from_payload(apply_device_profile(item)) for item in self._load_payload()]

    async def list_registry(self) -> list[dict[str, Any]]:
        return [apply_device_profile(dict(item)) for item in self._load_payload()]

    async def upsert_registry_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        payload = self._load_payload()
        normalized = apply_device_profile(_normalize_registry_device(device))
        retained = [item for item in payload if _config_key_for_device(item) != _config_key_for_device(normalized)]
        retained.append(normalized)
        self._write_payload(retained)
        return normalized

    async def remove_registry_device(self, *, node_id: str, endpoint_id: int) -> bool:
        payload = self._load_payload()
        target_key = f"{node_id}:{int(endpoint_id)}"
        retained = [item for item in payload if _config_key_for_device(item) != target_key]
        if len(retained) == len(payload):
            return False
        self._write_payload(retained)
        return True

    async def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = apply_device_profile(_normalize_registry_device(
            {
                "node_id": node_id,
                "endpoint_id": int((device or {}).get("endpoint_id", 1)),
                "name": (device or {}).get("name") or f"Commissioned Matter Device {node_id}",
                "metadata": {
                    **dict((device or {}).get("metadata") or {}),
                    "commissioning_method": "code",
                    "setup_payload": setup_payload,
                },
                **{
                    key: value
                    for key, value in dict(device or {}).items()
                    if key not in {"node_id", "endpoint_id", "name", "metadata"}
                },
            }
        ))
        return await self.upsert_registry_device(device=normalized)

    async def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        return _sampled_state_from_payload(dict(device.get("state") or {}))

    async def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "node_id": str(node_id),
            "endpoint_id": int(endpoint_id),
            "command": str(command),
            "args": dict(args or {}),
        }

    def supports_state_subscriptions(self) -> bool:
        return True

    async def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> AsyncIterator[dict[str, Any]]:
        del min_interval_seconds
        while True:
            yield await self.read_state(node_id=node_id, endpoint_id=endpoint_id)
            await asyncio.sleep(max(float(max_interval_seconds), 0.1))

    async def aclose(self) -> None:
        return None

    def _load_payload(self) -> list[dict[str, Any]]:
        try:
            raw = self.data_file.read_text()
        except FileNotFoundError as exc:
            raise MatterAdapterError(f"Sample Matter adapter data file was not found: {self.data_file}") from exc
        payload = _decode_payload_json(raw, source=str(self.data_file))
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError("Sample Matter adapter payload must be a device list or {'devices': [...]} object.")
        return [item for item in payload if isinstance(item, dict)]

    def _find_device(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        for item in self._load_payload():
            if str(item.get("node_id")) == str(node_id) and int(item.get("endpoint_id", -1)) == int(endpoint_id):
                return item
        raise MatterAdapterError(f"Matter device {node_id}/{endpoint_id} was not found in sample adapter data.")

    def _write_payload(self, payload: list[dict[str, Any]]) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(payload, indent=2, sort_keys=True))


class CommandMatterAdapter:
    def __init__(self, *, command: str | None) -> None:
        if not command:
            raise MatterAdapterError(
                "The 'command' Matter adapter requires MATTER_ADAPTER_COMMAND or --adapter-command."
            )
        self.command = command
        self.command_parts = shlex.split(command)
        if not self.command_parts:
            raise MatterAdapterError("The 'command' Matter adapter command string was empty after parsing.")

    async def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        payload = await self._run_json(
            "discover-commissionables",
            "--timeout-seconds",
            str(int(timeout_seconds)),
        )
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError(
                "Command Matter adapter 'discover-commissionables' output must be a list or {'devices': [...]} object."
            )
        return [dict(item) for item in payload if isinstance(item, dict)]

    async def list_devices(self) -> list[MatterDevice]:
        payload = await self._run_json("list-devices")
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError("Command Matter adapter 'list-devices' output must be a list or {'devices': [...]} object.")
        return [_device_from_payload(item) for item in payload if isinstance(item, dict)]

    async def list_registry(self) -> list[dict[str, Any]]:
        payload = await self._run_json("list-registry")
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError("Command Matter adapter 'list-registry' output must be a list or {'devices': [...]} object.")
        return [dict(item) for item in payload if isinstance(item, dict)]

    async def upsert_registry_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        payload = await self._run_json(
            "upsert-device",
            "--device-json",
            json.dumps(device, sort_keys=True),
        )
        if not isinstance(payload, dict):
            raise MatterAdapterError("Command Matter adapter 'upsert-device' output must be a JSON object.")
        return payload

    async def remove_registry_device(self, *, node_id: str, endpoint_id: int) -> bool:
        payload = await self._run_json(
            "remove-device",
            "--node-id",
            str(node_id),
            "--endpoint-id",
            str(int(endpoint_id)),
        )
        if not isinstance(payload, dict):
            raise MatterAdapterError("Command Matter adapter 'remove-device' output must be a JSON object.")
        return bool(payload.get("removed"))

    async def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = await self._run_json(
            "commission-with-code",
            "--node-id",
            str(node_id),
            "--setup-payload",
            str(setup_payload),
            "--device-json",
            json.dumps(device or {}, sort_keys=True),
        )
        if not isinstance(payload, dict):
            raise MatterAdapterError("Command Matter adapter 'commission-with-code' output must be a JSON object.")
        return payload

    async def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        payload = await self._run_json(
            "read-state",
            "--node-id",
            str(node_id),
            "--endpoint-id",
            str(int(endpoint_id)),
        )
        if not isinstance(payload, dict):
            raise MatterAdapterError("Command Matter adapter 'read-state' output must be a JSON object.")
        return _sampled_state_from_payload(dict(payload))

    async def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = await self._run_json(
            "invoke-command",
            "--node-id",
            str(node_id),
            "--endpoint-id",
            str(int(endpoint_id)),
            "--command",
            str(command),
            "--args-json",
            json.dumps(args or {}, sort_keys=True),
        )
        if not isinstance(payload, dict):
            raise MatterAdapterError("Command Matter adapter 'invoke-command' output must be a JSON object.")
        return payload

    def supports_state_subscriptions(self) -> bool:
        return True

    async def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> AsyncIterator[dict[str, Any]]:
        process = await asyncio.create_subprocess_exec(
            *self.command_parts,
            "subscribe-state",
            "--node-id",
            str(node_id),
            "--endpoint-id",
            str(int(endpoint_id)),
            "--min-interval-seconds",
            str(int(min_interval_seconds)),
            "--max-interval-seconds",
            str(int(max_interval_seconds)),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            while True:
                if process.stdout is None:
                    raise MatterAdapterError("Command Matter adapter subscription stream did not expose stdout.")
                raw_line = await process.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                payload = _decode_payload_json(line, source=self.command)
                if not isinstance(payload, dict):
                    raise MatterAdapterError(
                        "Command Matter adapter 'subscribe-state' output must be a JSON object per line."
                    )
                yield _sampled_state_from_payload(dict(payload))
            stderr_text = ""
            if process.stderr is not None:
                stderr_text = (await process.stderr.read()).decode("utf-8").strip()
            returncode = await process.wait()
            if returncode != 0:
                raise MatterAdapterError(
                    f"Command Matter adapter subscription failed with exit code {returncode}: {stderr_text}"
                )
        finally:
            if process.returncode is None:
                process.terminate()
                with suppress(ProcessLookupError):
                    await process.wait()

    async def aclose(self) -> None:
        return None

    async def _run_json(self, *args: str) -> Any:
        process = await asyncio.create_subprocess_exec(
            *self.command_parts,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise MatterAdapterError(
                f"Command Matter adapter failed with exit code {process.returncode}: {stderr.decode('utf-8').strip()}"
            )
        return _decode_payload_json(stdout.decode("utf-8"), source=self.command)


def _decode_payload_json(raw: str, *, source: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MatterAdapterError(f"Matter adapter output is not valid JSON from {source}.") from exc


def _sampled_state_from_payload(state: dict[str, Any]) -> dict[str, Any]:
    connected = bool(state.get("connected", True))
    sampled_at = state.get("sampled_at")
    sanitized_state = {
        key: value
        for key, value in state.items()
        if key not in {"connected", "sampled_at"}
    }
    return sampled_state(sanitized_state, connected=connected, sampled_at=sampled_at)


def _normalize_registry_device(device: dict[str, Any]) -> dict[str, Any]:
    if device.get("node_id") in {None, ""} or device.get("endpoint_id") is None:
        raise MatterAdapterError("Registry devices require 'node_id' and 'endpoint_id'.")
    normalized = dict(device)
    normalized["node_id"] = str(device["node_id"])
    normalized["endpoint_id"] = int(device["endpoint_id"])
    return normalized


def _config_key_for_device(device: dict[str, Any]) -> str:
    return f"{device.get('node_id')}:{int(device.get('endpoint_id', 0))}"


def _device_from_payload(payload: dict[str, Any]) -> MatterDevice:
    return MatterDevice(
        node_id=str(payload.get("node_id")),
        endpoint_id=int(payload.get("endpoint_id", 0)),
        name=str(payload.get("name") or f"Matter device {payload.get('node_id')}:{payload.get('endpoint_id')}"),
        vendor_name=str(payload.get("vendor_name")) if payload.get("vendor_name") is not None else None,
        product_name=str(payload.get("product_name")) if payload.get("product_name") is not None else None,
        device_types=[str(item) for item in payload.get("device_types", [])],
        capabilities=[str(item) for item in payload.get("capabilities", [])],
        state=dict(payload.get("state") or {}),
        command_bindings=[str(item) for item in payload.get("command_bindings", [])],
        metadata=dict(payload.get("metadata") or {}),
    )


def build_adapter(
    adapter_kind: str,
    *,
    data_file: str | None = None,
    command: str | None = None,
) -> MatterAdapter:
    normalized = str(adapter_kind or "").strip().lower()
    if normalized in {"", "null"}:
        return NullMatterAdapter()
    if normalized == "sample":
        return SampleMatterAdapter(data_file=data_file)
    if normalized == "command":
        return CommandMatterAdapter(command=command)
    raise MatterAdapterError(
        f"Unknown Matter adapter kind: {adapter_kind}. "
        "Supported adapters right now are 'null', 'sample', and 'command'."
    )
