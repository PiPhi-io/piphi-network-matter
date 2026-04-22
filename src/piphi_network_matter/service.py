from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import MatterSidecarConfig
from .controller.adapter import MatterAdapter, build_adapter
from .controller.device_profiles import describe_capability, describe_command, describe_entity
from .controller.models import MatterConfiguredDevice, MatterDevice

logger = logging.getLogger("piphi_network_matter")


@dataclass(slots=True)
class MatterSidecarService:
    config: MatterSidecarConfig
    adapter: MatterAdapter
    started_at: str | None = None
    last_poll_at: str | None = None
    last_subscription_event_at: str | None = None
    last_error: str | None = None
    poll_count: int = 0
    discovered_device_count: int = 0
    configured_device_count: int = 0
    last_telemetry_batch_count: int = 0
    active_subscription_count: int = 0
    live_state_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    subscription_errors: dict[str, str] = field(default_factory=dict)
    _subscription_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict, repr=False)
    _subscription_supervisor_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _subscription_stop_event: asyncio.Event | None = field(default=None, repr=False)
    _background_started: bool = field(default=False, repr=False)
    _last_cache_flush_at: float = field(default=0.0, repr=False)

    @classmethod
    def from_config(cls, config: MatterSidecarConfig) -> "MatterSidecarService":
        service = cls(
            config=config,
            adapter=build_adapter(
                config.adapter_kind,
                data_file=config.adapter_data_file,
                command=config.adapter_command,
            ),
        )
        service._load_configs()
        service._load_live_state_cache()
        return service

    @property
    def storage_path(self) -> Path:
        return Path(self.config.storage_dir)

    @property
    def config_file_path(self) -> Path:
        return self.storage_path / "configured_devices.json"

    @property
    def live_state_cache_file_path(self) -> Path:
        return self.storage_path / "live_state_cache.json"

    def mark_started(self) -> None:
        if self.started_at is None:
            self.started_at = datetime.now(tz=UTC).isoformat()

    async def run_forever(self) -> None:
        self.mark_started()
        await self.start_background_runtime()
        logger.info(
            "matter_sidecar_started adapter_kind=%s storage_dir=%s poll_interval_seconds=%s",
            self.config.adapter_kind,
            self.config.storage_dir,
            self.config.poll_interval_seconds,
        )
        try:
            while True:
                await self.run_once()
                await asyncio.sleep(self.config.poll_interval_seconds)
        finally:
            await self.stop_background_runtime()

    async def run_once(self) -> None:
        try:
            devices = await self.adapter.list_devices()
            self.discovered_device_count = len(devices)
            telemetry_batch = await self.poll_configured_devices()
            self.last_telemetry_batch_count = len(telemetry_batch)
            await self._flush_live_state_cache(force=False)
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("matter_sidecar_cycle_failed error=%s", exc)
        self.poll_count += 1
        self.last_poll_at = datetime.now(tz=UTC).isoformat()

    def list_configs(self) -> list[MatterConfiguredDevice]:
        return [
            MatterConfiguredDevice(
                node_id=str(item["node_id"]),
                endpoint_id=int(item["endpoint_id"]),
                alias=str(item.get("alias") or "").strip() or None,
                enabled=bool(item.get("enabled", True)),
                preferred_source=str(item.get("preferred_source") or "matter"),
            )
            for item in self._read_config_payload()
        ]

    async def discover_devices(self, *, node_id: str | None = None) -> list[MatterDevice]:
        devices = await self.adapter.list_devices()
        if node_id is None:
            return devices
        return [device for device in devices if str(device.node_id) == str(node_id)]

    async def list_entities(self) -> dict[str, Any]:
        devices = await self.discover_devices()
        configs_by_key = {item.config_key(): item for item in self.list_configs()}
        entities: list[dict[str, Any]] = []
        capabilities: dict[str, Any] = {}
        commands: dict[str, Any] = {}

        for device in devices:
            config = configs_by_key.get(device.config_key())
            available_commands = [describe_command(command_id) for command_id in device.command_bindings]
            for command_payload in available_commands:
                command_id = str(command_payload.get("id") or "").strip()
                if command_id and command_id not in commands:
                    commands[command_id] = command_payload

            for capability_id in device.capabilities:
                capability_payload = describe_capability(capability_id)
                if capability_payload:
                    capabilities[str(capability_payload["id"])] = capability_payload

            entity_presentation = describe_entity(
                device_types=list(device.device_types),
                capabilities=list(device.capabilities),
                command_bindings=list(device.command_bindings),
            )
            entities.append(
                {
                    "id": device.config_key(),
                    "name": config.alias if config and config.alias else device.name,
                    "capabilities": list(device.capabilities),
                    "config_id": device.config_key(),
                    "device_id": device.config_key(),
                    "device_type": device.device_types[0] if device.device_types else None,
                    "device_class": entity_presentation.get("device_class"),
                    "entity_type": entity_presentation.get("entity_type"),
                    "available_commands": available_commands,
                    "dashboard": entity_presentation.get("dashboard"),
                    "metadata": {
                        **dict(device.metadata or {}),
                        "node_id": device.node_id,
                        "endpoint_id": device.endpoint_id,
                        "vendor_name": device.vendor_name,
                        "product_name": device.product_name,
                        "configured": config is not None,
                        "alias": config.alias if config else None,
                    },
                }
            )

        return {
            "entities": entities,
            "capabilities": capabilities,
            "commands": commands,
        }

    async def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        return await self.adapter.discover_commissionables(timeout_seconds=timeout_seconds)

    async def list_registry_devices(self) -> list[dict[str, Any]]:
        return await self.adapter.list_registry()

    async def upsert_registry_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        return await self.adapter.upsert_registry_device(device=device)

    async def remove_registry_device(self, *, node_id: str, endpoint_id: int) -> bool:
        return await self.adapter.remove_registry_device(node_id=node_id, endpoint_id=endpoint_id)

    async def commission_device_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        commissioned = await self.adapter.commission_with_code(
            node_id=node_id,
            setup_payload=setup_payload,
            device=device,
        )
        if self.config.auto_configure_commissioned_devices:
            await self.configure_device(
                node_id=str(commissioned["node_id"]),
                endpoint_id=int(commissioned["endpoint_id"]),
                alias=str(commissioned.get("name") or "").strip() or None,
            )
        return commissioned

    async def configure_device(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        alias: str | None = None,
        preferred_source: str = "matter",
    ) -> MatterConfiguredDevice:
        devices = await self.discover_devices(node_id=node_id)
        target = next((device for device in devices if int(device.endpoint_id) == int(endpoint_id)), None)
        if target is None:
            raise ValueError(f"Matter device {node_id}/{endpoint_id} was not found.")
        configured = MatterConfiguredDevice(
            node_id=str(target.node_id),
            endpoint_id=int(target.endpoint_id),
            alias=str(alias or "").strip() or None,
            enabled=True,
            preferred_source=str(preferred_source or "matter"),
        )
        existing = [item for item in self.list_configs() if item.config_key() != configured.config_key()]
        existing.append(configured)
        self._write_configs(existing)
        self.configured_device_count = len(existing)
        await self._reconcile_subscriptions()
        return configured

    def remove_configured_device(self, *, node_id: str, endpoint_id: int) -> bool:
        config_key = f"{node_id}:{int(endpoint_id)}"
        configs = self.list_configs()
        retained = [item for item in configs if item.config_key() != config_key]
        if len(retained) == len(configs):
            return False
        self._write_configs(retained)
        self.configured_device_count = len(retained)
        config_key = f"{node_id}:{int(endpoint_id)}"
        self.live_state_cache.pop(config_key, None)
        self.subscription_errors.pop(config_key, None)
        return True

    async def poll_configured_devices(self) -> list[dict[str, Any]]:
        telemetry_batch: list[dict[str, Any]] = []
        for configured in self.list_configs():
            if not configured.enabled:
                continue
            config_key = configured.config_key()
            state = self.live_state_cache.get(config_key)
            if state is None:
                try:
                    state = await self.adapter.read_state(
                        node_id=configured.node_id,
                        endpoint_id=int(configured.endpoint_id),
                    )
                    self._store_live_state(config_key, state)
                except Exception as exc:
                    telemetry_batch.append(
                        {
                            "config_key": config_key,
                            "node_id": configured.node_id,
                            "endpoint_id": configured.endpoint_id,
                            "preferred_source": configured.preferred_source,
                            "alias": configured.alias,
                            "read_failed": True,
                            "error": str(exc),
                            "sampled_at": datetime.now(tz=UTC).isoformat(),
                        }
                    )
                    continue
            if not isinstance(state, dict):
                telemetry_batch.append(
                    {
                        "config_key": config_key,
                        "node_id": configured.node_id,
                        "endpoint_id": configured.endpoint_id,
                        "preferred_source": configured.preferred_source,
                        "alias": configured.alias,
                        "read_failed": True,
                        "error": "Live Matter state cache is invalid.",
                        "sampled_at": datetime.now(tz=UTC).isoformat(),
                    }
                )
                continue
            telemetry_batch.append(
                {
                    "config_key": config_key,
                    "node_id": configured.node_id,
                    "endpoint_id": configured.endpoint_id,
                    "preferred_source": configured.preferred_source,
                    "alias": configured.alias,
                    "read_failed": False,
                    "state": dict(state),
                    "sampled_at": str(state.get("sampled_at") or datetime.now(tz=UTC).isoformat()),
                }
            )
        self.configured_device_count = len(self.list_configs())
        await self._flush_live_state_cache(force=False)
        return telemetry_batch

    async def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.adapter.invoke_command(
            node_id=node_id,
            endpoint_id=endpoint_id,
            command=command,
            args=args,
        )

    async def start_background_runtime(self) -> None:
        if self._background_started:
            return
        self._background_started = True
        self._subscription_stop_event = asyncio.Event()
        if self.config.subscriptions_enabled and self.adapter.supports_state_subscriptions():
            self._subscription_supervisor_task = asyncio.create_task(self._subscription_supervisor_loop())

    async def stop_background_runtime(self) -> None:
        if not self._background_started:
            await self.adapter.aclose()
            return
        self._background_started = False
        if self._subscription_stop_event is not None:
            self._subscription_stop_event.set()
        if self._subscription_supervisor_task is not None:
            self._subscription_supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._subscription_supervisor_task
            self._subscription_supervisor_task = None
        for task in list(self._subscription_tasks.values()):
            task.cancel()
        for task in list(self._subscription_tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._subscription_tasks.clear()
        self.active_subscription_count = 0
        await self._flush_live_state_cache(force=True)
        await self.adapter.aclose()

    def _load_configs(self) -> None:
        self.configured_device_count = len(self.list_configs())

    def _load_live_state_cache(self) -> None:
        try:
            raw = self.live_state_cache_file_path.read_text()
        except FileNotFoundError:
            self.live_state_cache = {}
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.live_state_cache = {}
            return
        if not isinstance(payload, dict):
            self.live_state_cache = {}
            return
        self.live_state_cache = {
            str(key): dict(value)
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def _read_config_payload(self) -> list[dict[str, Any]]:
        try:
            raw = self.config_file_path.read_text()
        except FileNotFoundError:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _write_configs(self, configs: list[MatterConfiguredDevice]) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.config_file_path.write_text(
            json.dumps([config.to_dict() for config in configs], indent=2, sort_keys=True)
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "adapter_kind": self.config.adapter_kind,
            "storage_dir": self.config.storage_dir,
            "adapter_data_file": self.config.adapter_data_file,
            "adapter_command": self.config.adapter_command,
            "auto_configure_commissioned_devices": self.config.auto_configure_commissioned_devices,
            "api_host": self.config.api_host,
            "api_port": self.config.api_port,
            "config_file_path": str(self.config_file_path),
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "subscriptions_enabled": self.config.subscriptions_enabled,
            "subscription_min_interval_seconds": self.config.subscription_min_interval_seconds,
            "subscription_max_interval_seconds": self.config.subscription_max_interval_seconds,
            "subscription_retry_seconds": self.config.subscription_retry_seconds,
            "started_at": self.started_at,
            "last_poll_at": self.last_poll_at,
            "last_subscription_event_at": self.last_subscription_event_at,
            "last_error": self.last_error,
            "poll_count": self.poll_count,
            "discovered_device_count": self.discovered_device_count,
            "configured_device_count": self.configured_device_count,
            "last_telemetry_batch_count": self.last_telemetry_batch_count,
            "active_subscription_count": self.active_subscription_count,
            "subscription_error_count": len(self.subscription_errors),
        }

    async def _subscription_supervisor_loop(self) -> None:
        assert self._subscription_stop_event is not None
        while not self._subscription_stop_event.is_set():
            try:
                await self._reconcile_subscriptions()
                await self._flush_live_state_cache(force=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("matter_subscription_supervisor_failed error=%s", exc)
                self.last_error = str(exc)
            try:
                await asyncio.wait_for(
                    self._subscription_stop_event.wait(),
                    timeout=max(float(self.config.subscription_retry_seconds), 0.5),
                )
            except asyncio.TimeoutError:
                continue

    async def _reconcile_subscriptions(self) -> None:
        if not self._background_started:
            return
        if not self.config.subscriptions_enabled or not self.adapter.supports_state_subscriptions():
            return
        desired_keys = {
            config.config_key(): config
            for config in self.list_configs()
            if config.enabled
        }
        for config_key, task in list(self._subscription_tasks.items()):
            if config_key not in desired_keys or task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                self._subscription_tasks.pop(config_key, None)
        for config_key, config in desired_keys.items():
            if config_key in self._subscription_tasks:
                continue
            self._subscription_tasks[config_key] = asyncio.create_task(
                self._subscription_worker(config)
            )
        self.active_subscription_count = len(self._subscription_tasks)

    async def _subscription_worker(self, config: MatterConfiguredDevice) -> None:
        config_key = config.config_key()
        while True:
            try:
                async for state in self.adapter.subscribe_state(
                    node_id=config.node_id,
                    endpoint_id=int(config.endpoint_id),
                    min_interval_seconds=int(self.config.subscription_min_interval_seconds),
                    max_interval_seconds=int(self.config.subscription_max_interval_seconds),
                ):
                    self._store_live_state(config_key, state)
                    self.subscription_errors.pop(config_key, None)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.subscription_errors[config_key] = str(exc)
                logger.warning("matter_subscription_worker_failed config_key=%s error=%s", config_key, exc)
                await asyncio.sleep(max(float(self.config.subscription_retry_seconds), 0.5))
                continue
            await asyncio.sleep(max(float(self.config.subscription_retry_seconds), 0.5))

    def _store_live_state(self, config_key: str, state: dict[str, Any]) -> None:
        normalized = dict(state)
        normalized["connected"] = bool(normalized.get("connected", True))
        normalized["sampled_at"] = str(normalized.get("sampled_at") or datetime.now(tz=UTC).isoformat())
        self.live_state_cache[str(config_key)] = normalized
        self.last_subscription_event_at = normalized["sampled_at"]

    async def _flush_live_state_cache(self, *, force: bool) -> None:
        now = asyncio.get_running_loop().time()
        if not force and now - self._last_cache_flush_at < 1.0:
            return
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.live_state_cache_file_path.write_text(
            json.dumps(self.live_state_cache, indent=2, sort_keys=True)
        )
        self._last_cache_flush_at = now
