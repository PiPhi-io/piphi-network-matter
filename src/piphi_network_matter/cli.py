from __future__ import annotations

import json
import logging
import asyncio

import click

from .api import serve_api
from .config import MatterSidecarConfig, config_to_dict, load_sidecar_config
from .service import MatterSidecarService


LOG_LEVEL_CHOICES = click.Choice(
    ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    case_sensitive=False,
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="piphi-network-matter")
def main() -> None:
    """Run and inspect the PiPhi Matter sidecar."""


@main.command("run")
@click.option(
    "--adapter-kind",
    envvar="MATTER_ADAPTER_KIND",
    default=None,
    help="Matter adapter implementation to use. Supported adapters right now: null, sample, command.",
)
@click.option(
    "--poll-interval-seconds",
    envvar="MATTER_POLL_INTERVAL_SECONDS",
    default=None,
    type=float,
    help="Future default adapter poll interval in seconds.",
)
@click.option(
    "--storage-dir",
    envvar="MATTER_STORAGE_DIR",
    default=None,
    help="Directory reserved for Matter fabric/controller state.",
)
@click.option(
    "--adapter-data-file",
    envvar="MATTER_ADAPTER_DATA_FILE",
    default=None,
    help="Optional adapter-specific data file. Used by the sample adapter.",
)
@click.option(
    "--adapter-command",
    envvar="MATTER_ADAPTER_COMMAND",
    default=None,
    help="Optional adapter executable. Used by the command adapter.",
)
@click.option(
    "--api-host",
    envvar="MATTER_API_HOST",
    default=None,
    help="Bind host for the local sidecar API.",
)
@click.option(
    "--api-port",
    envvar="MATTER_API_PORT",
    default=None,
    type=int,
    help="Bind port for the local sidecar API.",
)
@click.option(
    "--log-level",
    envvar="LOG_LEVEL",
    default=None,
    type=LOG_LEVEL_CHOICES,
    help="Sidecar log level.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    show_default=True,
    help="Print the resolved sidecar config and exit.",
)
def run_command(
    adapter_kind: str | None,
    poll_interval_seconds: float | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    api_host: str | None,
    api_port: int | None,
    log_level: str | None,
    dry_run: bool,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=poll_interval_seconds,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=api_host,
        api_port=api_port,
        log_level=log_level,
    )
    if dry_run:
        click.echo(json.dumps(config_to_dict(config), indent=2, sort_keys=True))
        return
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    asyncio.run(service.run_forever())


@main.command("print-config")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--poll-interval-seconds", envvar="MATTER_POLL_INTERVAL_SECONDS", default=None, type=float)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--api-host", envvar="MATTER_API_HOST", default=None)
@click.option("--api-port", envvar="MATTER_API_PORT", default=None, type=int)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def print_config_command(
    adapter_kind: str | None,
    poll_interval_seconds: float | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    api_host: str | None,
    api_port: int | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=poll_interval_seconds,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=api_host,
        api_port=api_port,
        log_level=log_level,
    )
    click.echo(json.dumps(config_to_dict(config), indent=2, sort_keys=True))


@main.command("serve-api")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--api-host", envvar="MATTER_API_HOST", default=None)
@click.option("--api-port", envvar="MATTER_API_PORT", default=None, type=int)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    show_default=True,
    help="Print the resolved sidecar config and exit.",
)
def serve_api_command(
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    api_host: str | None,
    api_port: int | None,
    log_level: str | None,
    dry_run: bool,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=api_host,
        api_port=api_port,
        log_level=log_level,
    )
    if dry_run:
        click.echo(json.dumps(config_to_dict(config), indent=2, sort_keys=True))
        return
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    serve_api(service)


@main.command("discover")
@click.option("--node-id", default=None, help="Optional node id filter.")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def discover_command(
    node_id: str | None,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    devices = asyncio.run(service.discover_devices(node_id=node_id))
    click.echo(
        json.dumps(
            [device.discovery_record() for device in devices],
            indent=2,
            sort_keys=True,
        )
    )


@main.command("discover-commissionables")
@click.option("--timeout-seconds", default=5, show_default=True, type=int)
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def discover_commissionables_command(
    timeout_seconds: int,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    devices = asyncio.run(service.discover_commissionables(timeout_seconds=timeout_seconds))
    click.echo(json.dumps(devices, indent=2, sort_keys=True))


@main.command("configure")
@click.argument("node_id")
@click.argument("endpoint_id", type=int)
@click.option("--alias", default=None, help="Optional local alias for the configured device.")
@click.option("--preferred-source", default="matter", show_default=True, help="Preferred source label stored with the config.")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def configure_command(
    node_id: str,
    endpoint_id: int,
    alias: str | None,
    preferred_source: str,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    configured = asyncio.run(
        service.configure_device(
            node_id=node_id,
            endpoint_id=endpoint_id,
            alias=alias,
            preferred_source=preferred_source,
        )
    )
    click.echo(json.dumps(configured.to_dict(), indent=2, sort_keys=True))


@main.command("configs")
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def configs_command(
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=None,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    click.echo(json.dumps([item.to_dict() for item in service.list_configs()], indent=2, sort_keys=True))


@main.command("registry-list")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def registry_list_command(
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    registry = asyncio.run(service.list_registry_devices())
    click.echo(json.dumps(registry, indent=2, sort_keys=True))


@main.command("registry-upsert")
@click.option("--device-json", required=True)
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def registry_upsert_command(
    device_json: str,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    payload = json.loads(device_json)
    if not isinstance(payload, dict):
        raise click.ClickException("--device-json must decode to a JSON object.")
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    record = asyncio.run(service.upsert_registry_device(device=payload))
    click.echo(json.dumps(record, indent=2, sort_keys=True))


@main.command("commission-code")
@click.argument("node_id")
@click.argument("setup_payload")
@click.option("--endpoint-id", default=1, show_default=True, type=int)
@click.option("--name", default=None)
@click.option("--device-json", default=None)
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def commission_code_command(
    node_id: str,
    setup_payload: str,
    endpoint_id: int,
    name: str | None,
    device_json: str | None,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    payload: dict[str, object] = {"endpoint_id": endpoint_id}
    if name:
        payload["name"] = name
    if device_json:
        decoded = json.loads(device_json)
        if not isinstance(decoded, dict):
            raise click.ClickException("--device-json must decode to a JSON object.")
        payload.update(decoded)
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    record = asyncio.run(
        service.commission_device_with_code(
            node_id=node_id,
            setup_payload=setup_payload,
            device=payload,
        )
    )
    click.echo(json.dumps(record, indent=2, sort_keys=True))


@main.command("registry-remove")
@click.argument("node_id")
@click.argument("endpoint_id", type=int)
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def registry_remove_command(
    node_id: str,
    endpoint_id: int,
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    removed = asyncio.run(service.remove_registry_device(node_id=node_id, endpoint_id=endpoint_id))
    click.echo(
        json.dumps(
            {"removed": removed, "node_id": node_id, "endpoint_id": endpoint_id},
            indent=2,
            sort_keys=True,
        )
    )


@main.command("poll-once")
@click.option("--adapter-kind", envvar="MATTER_ADAPTER_KIND", default=None)
@click.option("--storage-dir", envvar="MATTER_STORAGE_DIR", default=None)
@click.option("--adapter-data-file", envvar="MATTER_ADAPTER_DATA_FILE", default=None)
@click.option("--adapter-command", envvar="MATTER_ADAPTER_COMMAND", default=None)
@click.option("--log-level", envvar="LOG_LEVEL", default=None, type=LOG_LEVEL_CHOICES)
def poll_once_command(
    adapter_kind: str | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    log_level: str | None,
) -> None:
    config = _resolve_config(
        adapter_kind=adapter_kind,
        poll_interval_seconds=None,
        storage_dir=storage_dir,
        adapter_data_file=adapter_data_file,
        adapter_command=adapter_command,
        api_host=None,
        api_port=None,
        log_level=log_level,
    )
    _configure_logging(config.log_level)
    service = MatterSidecarService.from_config(config)
    telemetry_batch = asyncio.run(service.poll_configured_devices())
    click.echo(json.dumps(telemetry_batch, indent=2, sort_keys=True))


def _resolve_config(
    *,
    adapter_kind: str | None,
    poll_interval_seconds: float | None,
    storage_dir: str | None,
    adapter_data_file: str | None,
    adapter_command: str | None,
    api_host: str | None,
    api_port: int | None,
    log_level: str | None,
) -> MatterSidecarConfig:
    base = load_sidecar_config()
    return MatterSidecarConfig(
        log_level=(log_level or base.log_level).upper(),
        adapter_kind=(adapter_kind or base.adapter_kind).strip().lower(),
        poll_interval_seconds=poll_interval_seconds or base.poll_interval_seconds,
        storage_dir=storage_dir or base.storage_dir,
        subscriptions_enabled=base.subscriptions_enabled,
        subscription_min_interval_seconds=base.subscription_min_interval_seconds,
        subscription_max_interval_seconds=base.subscription_max_interval_seconds,
        subscription_retry_seconds=base.subscription_retry_seconds,
        adapter_data_file=adapter_data_file or base.adapter_data_file,
        adapter_command=adapter_command or base.adapter_command,
        api_host=api_host or base.api_host,
        api_port=api_port or base.api_port,
    )


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
