from __future__ import annotations

import json
import queue
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterator, Protocol

from .adapter import MatterAdapterError
from .device_profiles import DEVICE_TYPE_NAMES, apply_device_profile


class ControllerBridgeBackend(Protocol):
    def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]: ...
    def list_devices(self) -> list[dict[str, Any]]: ...
    def list_registry(self) -> list[dict[str, Any]]: ...
    def upsert_device(self, *, device: dict[str, Any]) -> dict[str, Any]: ...
    def remove_device(self, *, node_id: str, endpoint_id: int) -> bool: ...
    def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]: ...
    def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
    def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> Iterator[dict[str, Any]]: ...


class NullBridgeBackend:
    def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        del timeout_seconds
        return []

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def list_registry(self) -> list[dict[str, Any]]:
        return []

    def upsert_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        del device
        raise MatterAdapterError("The null Matter controller backend cannot manage registry devices.")

    def remove_device(self, *, node_id: str, endpoint_id: int) -> bool:
        del node_id, endpoint_id
        raise MatterAdapterError("The null Matter controller backend cannot manage registry devices.")

    def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del node_id, setup_payload, device
        raise MatterAdapterError("The null Matter controller backend cannot commission devices.")

    def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        del node_id, endpoint_id
        raise MatterAdapterError("The null Matter controller backend cannot read state.")

    def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del node_id, endpoint_id, command, args
        raise MatterAdapterError("The null Matter controller backend cannot invoke commands.")

    def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> Iterator[dict[str, Any]]:
        del node_id, endpoint_id, min_interval_seconds, max_interval_seconds
        raise MatterAdapterError("The null Matter controller backend cannot subscribe to state.")


class SampleBridgeBackend:
    def __init__(self, *, data_file: str | None) -> None:
        if not data_file:
            raise MatterAdapterError(
                "The sample Matter controller backend requires --data-file or MATTER_CONTROLLER_DATA_FILE."
            )
        self.data_file = Path(data_file)

    def list_devices(self) -> list[dict[str, Any]]:
        return [apply_device_profile(item) for item in self.list_registry()]

    def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        del timeout_seconds
        results: list[dict[str, Any]] = []
        for item in self.list_registry():
            metadata = dict(item.get("metadata") or {})
            results.append(
                {
                    "instance_name": str(item.get("instance_name") or item.get("node_id")),
                    "vendor_id": item.get("vendor_id", metadata.get("vendor_id")),
                    "product_id": item.get("product_id", metadata.get("product_id")),
                    "device_type": item.get("device_type", metadata.get("device_type")),
                    "long_discriminator": item.get("long_discriminator", metadata.get("long_discriminator")),
                    "commissioning_mode": 1,
                    "name": item.get("name"),
                    "addresses": list(item.get("addresses") or metadata.get("addresses") or []),
                    "metadata": {
                        "source": "sample",
                    },
                }
            )
        return results

    def list_registry(self) -> list[dict[str, Any]]:
        payload = self._load_payload()
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError("Sample Matter controller payload must be a list or {'devices': [...]} object.")
        return [item for item in payload if isinstance(item, dict)]

    def upsert_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        normalized = apply_device_profile(_normalize_registry_device(device))
        retained = [item for item in self.list_registry() if _config_key_for_device(item) != _config_key_for_device(normalized)]
        retained.append(normalized)
        self._write_payload(retained)
        return normalized

    def remove_device(self, *, node_id: str, endpoint_id: int) -> bool:
        payload = self.list_registry()
        target_key = f"{node_id}:{int(endpoint_id)}"
        retained = [item for item in payload if _config_key_for_device(item) != target_key]
        if len(retained) == len(payload):
            return False
        self._write_payload(retained)
        return True

    def commission_with_code(
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
        return self.upsert_device(device=normalized)

    def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        state = dict(device.get("state") or {})
        if "connected" not in state:
            state["connected"] = True
        return state

    def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        return {
            "ok": True,
            "node_id": node_id,
            "endpoint_id": endpoint_id,
            "command": command,
            "args": dict(args or {}),
            "device_name": device.get("name"),
        }

    def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> Iterator[dict[str, Any]]:
        del min_interval_seconds
        while True:
            yield self.read_state(node_id=node_id, endpoint_id=endpoint_id)
            time.sleep(max(float(max_interval_seconds), 0.1))

    def _load_payload(self) -> Any:
        return _load_json_file(
            self.data_file,
            not_found_message="Sample Matter controller data file was not found",
            invalid_message="Sample Matter controller data file is not valid JSON",
        )

    def _find_device(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        for item in self.list_devices():
            if str(item.get("node_id")) == str(node_id) and int(item.get("endpoint_id", -1)) == int(endpoint_id):
                return item
        raise MatterAdapterError(
            f"Matter device {node_id}/{endpoint_id} was not found in controller backend data."
        )

    def _write_payload(self, payload: list[dict[str, Any]]) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(payload, indent=2, sort_keys=True))


class ChipToolBridgeBackend:
    def __init__(self, *, data_file: str | None, controller_binary: str | None = None) -> None:
        if not data_file:
            raise MatterAdapterError(
                "The chip-tool controller backend requires --data-file or MATTER_CONTROLLER_DATA_FILE."
            )
        self.data_file = Path(data_file)
        self.storage_directory = self.data_file.parent
        self.controller_binary = controller_binary or "chip-tool"
        self.controller_binary_parts = shlex.split(self.controller_binary)
        if not self.controller_binary_parts:
            raise MatterAdapterError("The chip-tool controller backend binary string was empty after parsing.")

    def list_devices(self) -> list[dict[str, Any]]:
        registry = self.list_registry()
        devices = [self._enrich_device_record(item) for item in registry]
        if devices != registry:
            self._write_devices(devices)
        return devices

    def discover_commissionables(self, *, timeout_seconds: int = 5) -> list[dict[str, Any]]:
        output = self._run_chip_tool(
            "discover",
            "commissionables",
            timeout_seconds=max(float(timeout_seconds), 0.1),
        )
        return self._parse_commissionables_output(output)

    def list_registry(self) -> list[dict[str, Any]]:
        return self._load_devices()

    def upsert_device(self, *, device: dict[str, Any]) -> dict[str, Any]:
        normalized = apply_device_profile(_normalize_registry_device(device))
        retained = [item for item in self.list_registry() if _config_key_for_device(item) != _config_key_for_device(normalized)]
        retained.append(normalized)
        self._write_devices(retained)
        return normalized

    def remove_device(self, *, node_id: str, endpoint_id: int) -> bool:
        payload = self.list_registry()
        target_key = f"{node_id}:{int(endpoint_id)}"
        retained = [item for item in payload if _config_key_for_device(item) != target_key]
        if len(retained) == len(payload):
            return False
        self._write_devices(retained)
        return True

    def commission_with_code(
        self,
        *,
        node_id: str,
        setup_payload: str,
        device: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        commissioning_options = self._chip_tool_option_args(device or {})
        output = self._run_chip_tool(
            "pairing",
            "code",
            str(node_id),
            str(setup_payload),
            option_args=commissioning_options,
        )
        endpoint_id = int((device or {}).get("endpoint_id", 1))
        probed_device = self._probe_commissioned_device(
            node_id=str(node_id),
            endpoint_id=endpoint_id,
            device=device or {},
        )
        normalized = apply_device_profile(
            _normalize_registry_device(
                {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "name": (device or {}).get("name") or f"Commissioned Matter Device {node_id}",
                "metadata": {
                    **dict((device or {}).get("metadata") or {}),
                    "commissioning_method": "code",
                    "setup_payload": setup_payload,
                    "chip_tool_output": output.strip(),
                },
                **probed_device,
                **{
                    key: value
                    for key, value in dict(device or {}).items()
                    if key not in {"node_id", "endpoint_id", "name", "metadata"}
                },
                }
            )
        )
        return self.upsert_device(device=normalized)

    def read_state(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        specs = dict(device.get("chip_tool_reads") or {})
        state: dict[str, Any] = {}
        option_args = self._chip_tool_option_args(device)
        for capability, spec in specs.items():
            if not isinstance(spec, dict):
                continue
            cluster = str(spec.get("cluster") or "").strip()
            attribute = str(spec.get("attribute") or "").strip()
            if not cluster or not attribute:
                continue
            output = self._run_chip_tool(
                cluster,
                "read",
                attribute,
                node_id,
                endpoint_id,
                option_args=option_args,
            )
            state[capability] = self._extract_read_value(output, spec)
        state["connected"] = True
        return state

    def invoke_command(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        specs = dict(device.get("chip_tool_commands") or {})
        spec = specs.get(command)
        if not isinstance(spec, dict):
            raise MatterAdapterError(f"chip-tool backend does not have a command mapping for '{command}'.")
        cluster = str(spec.get("cluster") or "").strip()
        chip_command = str(spec.get("command") or "").strip()
        if not cluster or not chip_command:
            raise MatterAdapterError(f"chip-tool backend command '{command}' is missing cluster or command metadata.")
        formatted_args = [
            str(item).format(**dict(args or {}))
            for item in list(spec.get("arg_templates") or [])
        ]
        output = self._run_chip_tool(
            cluster,
            chip_command,
            *formatted_args,
            node_id,
            endpoint_id,
            option_args=self._chip_tool_option_args(device),
        )
        return {
            "ok": True,
            "node_id": node_id,
            "endpoint_id": endpoint_id,
            "command": command,
            "chip_tool_command": [cluster, chip_command, *formatted_args, node_id, str(endpoint_id)],
            "output": output.strip(),
        }

    def subscribe_state(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        min_interval_seconds: int = 1,
        max_interval_seconds: int = 300,
    ) -> Iterator[dict[str, Any]]:
        device = self._find_device(node_id=node_id, endpoint_id=endpoint_id)
        specs = {
            capability: dict(spec)
            for capability, spec in dict(device.get("chip_tool_reads") or {}).items()
            if isinstance(spec, dict)
        }
        if not specs:
            raise MatterAdapterError(
                f"chip-tool backend does not have any read mappings for {node_id}/{endpoint_id}."
            )

        stop_event = threading.Event()
        event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        aggregate_state: dict[str, Any] = {}
        option_args = self._chip_tool_option_args(device)
        processes: list[subprocess.Popen[str]] = []

        def _reader(capability: str, spec: dict[str, Any]) -> None:
            cluster = str(spec.get("cluster") or "").strip()
            attribute = str(spec.get("attribute") or "").strip()
            if not cluster or not attribute:
                event_queue.put(("error", f"chip-tool subscribe spec for '{capability}' is missing cluster or attribute."))
                return
            command = [
                *self.controller_binary_parts,
                cluster,
                "subscribe",
                attribute,
                str(int(min_interval_seconds)),
                str(int(max_interval_seconds)),
                str(node_id),
                str(int(endpoint_id)),
                *option_args,
                "--storage-directory",
                str(self.storage_directory),
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                event_queue.put(("error", f"Unable to spawn chip-tool subscription for '{capability}': {exc}"))
                return
            processes.append(process)
            try:
                assert process.stdout is not None
                for raw_line in iter(process.stdout.readline, ""):
                    if stop_event.is_set():
                        break
                    try:
                        value = self._extract_read_value(raw_line, spec)
                    except MatterAdapterError:
                        continue
                    event_queue.put(
                        (
                            "update",
                            {
                                "capability": capability,
                                "value": value,
                                "sampled_at": _utc_now_iso(),
                            },
                        )
                    )
                returncode = process.wait()
                if stop_event.is_set():
                    return
                stderr_output = ""
                if process.stderr is not None:
                    stderr_output = process.stderr.read().strip()
                if returncode != 0:
                    event_queue.put(
                        (
                            "error",
                            f"chip-tool subscribe command for '{capability}' failed with exit code {returncode}: {stderr_output}",
                        )
                    )
                else:
                    event_queue.put(("closed", capability))
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()

        threads = [
            threading.Thread(target=_reader, args=(capability, spec), daemon=True)
            for capability, spec in specs.items()
        ]
        for thread in threads:
            thread.start()

        try:
            open_streams = len(threads)
            while open_streams > 0:
                try:
                    event_type, payload = event_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if event_type == "update":
                    capability = str(payload["capability"])
                    aggregate_state[capability] = payload["value"]
                    yield {
                        **dict(aggregate_state),
                        "connected": True,
                        "sampled_at": str(payload["sampled_at"]),
                    }
                    continue
                if event_type == "closed":
                    open_streams -= 1
                    continue
                if event_type == "error":
                    raise MatterAdapterError(str(payload))
        finally:
            stop_event.set()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
            for thread in threads:
                thread.join(timeout=1)

    def _load_devices(self) -> list[dict[str, Any]]:
        if not self.data_file.exists():
            return []
        payload = _load_json_file(
            self.data_file,
            not_found_message="chip-tool controller registry file was not found",
            invalid_message="chip-tool controller registry file is not valid JSON",
        )
        if isinstance(payload, dict):
            payload = payload.get("devices", [])
        if not isinstance(payload, list):
            raise MatterAdapterError("chip-tool controller registry must be a list or {'devices': [...]} object.")
        return [item for item in payload if isinstance(item, dict)]

    def _find_device(self, *, node_id: str, endpoint_id: int) -> dict[str, Any]:
        for item in self._load_devices():
            if str(item.get("node_id")) == str(node_id) and int(item.get("endpoint_id", -1)) == int(endpoint_id):
                return item
        raise MatterAdapterError(
            f"Matter device {node_id}/{endpoint_id} was not found in chip-tool controller registry."
        )

    def _run_chip_tool(
        self,
        cluster: str,
        subcommand: str,
        *args: object,
        option_args: list[str] | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        command = [
            *self.controller_binary_parts,
            cluster,
            subcommand,
            *[str(item) for item in args],
            *list(option_args or []),
            "--storage-directory",
            str(self.storage_directory),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MatterAdapterError(
                f"chip-tool backend command timed out after {timeout_seconds:g} seconds."
            ) from exc
        if result.returncode != 0:
            raise MatterAdapterError(
                f"chip-tool backend command failed with exit code {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout

    def _extract_read_value(self, output: str, spec: dict[str, Any]) -> Any:
        regex = str(spec.get("value_regex") or "").strip()
        if not regex:
            raise MatterAdapterError("chip-tool read spec is missing 'value_regex'.")
        match = re.search(regex, output, re.MULTILINE)
        if not match:
            raise MatterAdapterError(f"chip-tool output did not match regex: {regex}")
        raw_value = match.group(1)
        transform = str(spec.get("transform") or "string").strip().lower()
        if transform == "int":
            return int(raw_value)
        if transform == "float":
            return float(raw_value)
        if transform == "centi":
            return float(raw_value) / 100.0
        if transform == "bool":
            lowered = str(raw_value).strip().lower()
            return lowered in {"1", "true", "on", "yes"}
        if transform == "nonzero_bool":
            return int(raw_value) != 0
        if transform == "level_percent_254":
            return round((int(raw_value) / 254.0) * 100.0, 1)
        return raw_value

    def _parse_commissionables_output(self, output: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if "Discovered node:" in line:
                if current:
                    results.append(current)
                current = {
                    "addresses": [],
                    "metadata": {"source": "chip-tool"},
                }
                continue
            if current is None:
                continue
            if "Hostname:" in line:
                current["hostname"] = line.split("Hostname:", 1)[1].strip()
                current.setdefault("instance_name", current["hostname"])
                continue
            if "IP Address" in line:
                current.setdefault("addresses", []).append(line.split(":", 1)[1].strip())
                continue
            if "Port:" in line:
                current["port"] = _parse_int(line.split("Port:", 1)[1].strip())
                continue
            if "Vendor ID:" in line:
                current["vendor_id"] = _parse_int(line.split("Vendor ID:", 1)[1].split()[0])
                continue
            if "Product ID:" in line:
                current["product_id"] = _parse_int(line.split("Product ID:", 1)[1].split()[0])
                continue
            if "Device Type:" in line:
                current["device_type"] = _parse_int(line.split("Device Type:", 1)[1].split()[0])
                continue
            if "Long Discriminator:" in line:
                current["long_discriminator"] = _parse_int(line.split("Long Discriminator:", 1)[1].split()[0])
                continue
            if "Pairing Hint:" in line:
                current["pairing_hint"] = _parse_int(line.split("Pairing Hint:", 1)[1].split()[0])
                continue
            if "Instance Name:" in line:
                current["instance_name"] = line.split("Instance Name:", 1)[1].strip()
                continue
            if "Commissioning Mode:" in line:
                current["commissioning_mode"] = _parse_int(line.split("Commissioning Mode:", 1)[1].split()[0])
                continue
        if current:
            results.append(current)
        return results

    def _write_devices(self, payload: list[dict[str, Any]]) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _chip_tool_option_args(self, device: dict[str, Any]) -> list[str]:
        metadata = dict(device.get("metadata") or {})
        fabric_name = (
            str(device.get("fabric_name") or metadata.get("fabric_name") or metadata.get("commissioner_name") or "").strip()
        )
        commissioner_nodeid = (
            str(device.get("commissioner_nodeid") or metadata.get("commissioner_nodeid") or "").strip()
        )
        commissioner_vendor_id = (
            str(device.get("commissioner_vendor_id") or metadata.get("commissioner_vendor_id") or "").strip()
        )
        args: list[str] = []
        if fabric_name:
            args.extend(["--commissioner-name", fabric_name])
        if commissioner_nodeid:
            args.extend(["--commissioner-nodeid", commissioner_nodeid])
        if commissioner_vendor_id:
            args.extend(["--commissioner-vendor-id", commissioner_vendor_id])
        return args

    def _enrich_device_record(self, device: dict[str, Any]) -> dict[str, Any]:
        normalized = apply_device_profile(_normalize_registry_device(device))
        metadata = dict(normalized.get("metadata") or {})
        needs_probe = (
            not normalized.get("vendor_name")
            or not normalized.get("product_name")
            or not list(normalized.get("device_types") or [])
        )
        if needs_probe:
            probed = self._probe_commissioned_device(
                node_id=str(normalized["node_id"]),
                endpoint_id=int(normalized["endpoint_id"]),
                device=normalized,
            )
            if probed:
                normalized = apply_device_profile(
                    _normalize_registry_device(
                        {
                            **normalized,
                            **{key: value for key, value in probed.items() if key != "metadata"},
                            "metadata": {
                                **metadata,
                                **dict(probed.get("metadata") or {}),
                            },
                        }
                    )
                )
        return normalized

    def _probe_commissioned_device(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        device: dict[str, Any],
    ) -> dict[str, Any]:
        option_args = self._chip_tool_option_args(device)
        metadata = dict(device.get("metadata") or {})
        probed: dict[str, Any] = {}

        device_type_list = self._read_device_type_list(node_id=node_id, endpoint_id=endpoint_id, option_args=option_args)
        if device_type_list:
            probed["device_types"] = [DEVICE_TYPE_NAMES.get(item, str(item)) for item in device_type_list]
            metadata["device_type_list"] = device_type_list
            metadata["device_type"] = device_type_list[0]

        vendor_name = self._read_basic_string_attribute(
            "vendor-name",
            labels=["VendorName"],
            node_id=node_id,
            endpoint_candidates=[0, endpoint_id],
            option_args=option_args,
        )
        if vendor_name:
            probed["vendor_name"] = vendor_name

        product_name = self._read_basic_string_attribute(
            "product-name",
            labels=["ProductName"],
            node_id=node_id,
            endpoint_candidates=[0, endpoint_id],
            option_args=option_args,
        )
        if product_name:
            probed["product_name"] = product_name

        vendor_id = self._read_basic_int_attribute(
            "vendor-id",
            labels=["VendorID", "VendorId"],
            node_id=node_id,
            endpoint_candidates=[0, endpoint_id],
            option_args=option_args,
        )
        if vendor_id is not None:
            metadata["vendor_id"] = vendor_id

        product_id = self._read_basic_int_attribute(
            "product-id",
            labels=["ProductID", "ProductId"],
            node_id=node_id,
            endpoint_candidates=[0, endpoint_id],
            option_args=option_args,
        )
        if product_id is not None:
            metadata["product_id"] = product_id

        if metadata:
            metadata["inventory_source"] = "chip-tool"
            probed["metadata"] = metadata
        return probed

    def _read_device_type_list(
        self,
        *,
        node_id: str,
        endpoint_id: int,
        option_args: list[str],
    ) -> list[int]:
        output = self._run_chip_tool_best_effort(
            "descriptor",
            "read",
            "device-type-list",
            node_id,
            endpoint_id,
            option_args=option_args,
        )
        if not output:
            return []
        found: list[int] = []
        for raw_value in re.findall(r"deviceType[^0-9A-Fa-f]*(0x[0-9A-Fa-f]+|\d+)", output, re.IGNORECASE):
            parsed = _parse_int(raw_value)
            if parsed not in found:
                found.append(parsed)
        return found

    def _read_basic_string_attribute(
        self,
        attribute: str,
        *,
        labels: list[str],
        node_id: str,
        endpoint_candidates: list[int],
        option_args: list[str],
    ) -> str | None:
        for endpoint_id in endpoint_candidates:
            output = self._run_chip_tool_best_effort(
                "basicinformation",
                "read",
                attribute,
                node_id,
                endpoint_id,
                option_args=option_args,
            )
            value = _extract_string_value(output, labels=labels)
            if value:
                return value
        return None

    def _read_basic_int_attribute(
        self,
        attribute: str,
        *,
        labels: list[str],
        node_id: str,
        endpoint_candidates: list[int],
        option_args: list[str],
    ) -> int | None:
        for endpoint_id in endpoint_candidates:
            output = self._run_chip_tool_best_effort(
                "basicinformation",
                "read",
                attribute,
                node_id,
                endpoint_id,
                option_args=option_args,
            )
            value = _extract_int_value(output, labels=labels)
            if value is not None:
                return value
        return None

    def _run_chip_tool_best_effort(
        self,
        cluster: str,
        subcommand: str,
        *args: object,
        option_args: list[str],
    ) -> str | None:
        try:
            return self._run_chip_tool(
                cluster,
                subcommand,
                *args,
                option_args=option_args,
            )
        except MatterAdapterError:
            return None


def build_controller_backend(
    backend_kind: str,
    *,
    data_file: str | None = None,
    controller_binary: str | None = None,
) -> ControllerBridgeBackend:
    normalized = str(backend_kind or "").strip().lower()
    if normalized in {"", "null"}:
        return NullBridgeBackend()
    if normalized == "sample":
        return SampleBridgeBackend(data_file=data_file)
    if normalized == "chip-tool":
        return ChipToolBridgeBackend(data_file=data_file, controller_binary=controller_binary)
    raise MatterAdapterError(
        f"Unknown Matter controller backend kind: {backend_kind}. "
        "Supported backends right now are 'null', 'sample', and 'chip-tool'."
    )


def _load_json_file(path: Path, *, not_found_message: str, invalid_message: str) -> Any:
    try:
        raw = path.read_text()
    except FileNotFoundError as exc:
        raise MatterAdapterError(f"{not_found_message}: {path}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MatterAdapterError(f"{invalid_message}: {path}") from exc


def _normalize_registry_device(device: dict[str, Any]) -> dict[str, Any]:
    if device.get("node_id") in {None, ""} or device.get("endpoint_id") is None:
        raise MatterAdapterError("Registry devices require 'node_id' and 'endpoint_id'.")
    normalized = dict(device)
    normalized["node_id"] = str(device["node_id"])
    normalized["endpoint_id"] = int(device["endpoint_id"])
    return normalized


def _config_key_for_device(device: dict[str, Any]) -> str:
    return f"{device.get('node_id')}:{int(device.get('endpoint_id', 0))}"


def _parse_int(value: str) -> int:
    stripped = value.strip()
    if stripped.lower().startswith("0x"):
        return int(stripped, 16)
    return int(stripped)


def _extract_string_value(output: str | None, *, labels: list[str]) -> str | None:
    if not output:
        return None
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:=]\s*\"?([^\n\"]+)\"?", output, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    data_match = re.search(r"Data\s*=\s*\"?([^\n\"]+)\"?", output, re.IGNORECASE)
    if data_match:
        return data_match.group(1).strip()
    return None


def _extract_int_value(output: str | None, *, labels: list[str]) -> int | None:
    if not output:
        return None
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:=]\s*(0x[0-9A-Fa-f]+|\d+)", output, re.IGNORECASE)
        if match:
            return _parse_int(match.group(1))
    data_match = re.search(r"Data\s*=\s*(0x[0-9A-Fa-f]+|\d+)", output, re.IGNORECASE)
    if data_match:
        return _parse_int(data_match.group(1))
    return None


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()
