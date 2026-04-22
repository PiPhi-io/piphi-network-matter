from __future__ import annotations

import json
import signal

import click

from .bridge_backend import build_controller_backend


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--backend-kind",
    envvar="MATTER_CONTROLLER_BACKEND_KIND",
    default="sample",
    show_default=True,
    help="Controller backend implementation to use.",
)
@click.option(
    "--data-file",
    envvar="MATTER_CONTROLLER_DATA_FILE",
    default=None,
    help="Backend data file. Used by the sample backend.",
)
@click.option(
    "--controller-binary",
    envvar="MATTER_CONTROLLER_BINARY",
    default=None,
    help="External controller binary. Used by the chip-tool backend.",
)
@click.pass_context
def main(
    ctx: click.Context,
    backend_kind: str,
    data_file: str | None,
    controller_binary: str | None,
) -> None:
    """Run the PiPhi Matter controller bridge."""
    ctx.obj = {
        "backend": build_controller_backend(
            backend_kind,
            data_file=data_file,
            controller_binary=controller_binary,
        ),
    }


@main.command("list-devices")
@click.pass_context
def list_devices_command(ctx: click.Context) -> None:
    backend = ctx.obj["backend"]
    click.echo(json.dumps({"devices": backend.list_devices()}, indent=2, sort_keys=True))


@main.command("discover-commissionables")
@click.option("--timeout-seconds", default=5, show_default=True, type=int)
@click.pass_context
def discover_commissionables_command(ctx: click.Context, timeout_seconds: int) -> None:
    backend = ctx.obj["backend"]
    click.echo(
        json.dumps(
            {"devices": backend.discover_commissionables(timeout_seconds=timeout_seconds)},
            indent=2,
            sort_keys=True,
        )
    )


@main.command("list-registry")
@click.pass_context
def list_registry_command(ctx: click.Context) -> None:
    backend = ctx.obj["backend"]
    click.echo(json.dumps({"devices": backend.list_registry()}, indent=2, sort_keys=True))


@main.command("upsert-device")
@click.option("--device-json", required=True)
@click.pass_context
def upsert_device_command(ctx: click.Context, device_json: str) -> None:
    backend = ctx.obj["backend"]
    payload = json.loads(device_json)
    click.echo(
        json.dumps(
            backend.upsert_device(device=payload if isinstance(payload, dict) else {}),
            indent=2,
            sort_keys=True,
        )
    )


@main.command("remove-device")
@click.option("--node-id", required=True)
@click.option("--endpoint-id", required=True, type=int)
@click.pass_context
def remove_device_command(ctx: click.Context, node_id: str, endpoint_id: int) -> None:
    backend = ctx.obj["backend"]
    click.echo(
        json.dumps(
            {
                "removed": backend.remove_device(node_id=node_id, endpoint_id=endpoint_id),
                "node_id": node_id,
                "endpoint_id": endpoint_id,
            },
            indent=2,
            sort_keys=True,
        )
    )


@main.command("commission-with-code")
@click.option("--node-id", required=True)
@click.option("--setup-payload", required=True)
@click.option("--device-json", default="{}", show_default=True)
@click.pass_context
def commission_with_code_command(
    ctx: click.Context,
    node_id: str,
    setup_payload: str,
    device_json: str,
) -> None:
    backend = ctx.obj["backend"]
    payload = json.loads(device_json)
    click.echo(
        json.dumps(
            backend.commission_with_code(
                node_id=node_id,
                setup_payload=setup_payload,
                device=payload if isinstance(payload, dict) else {},
            ),
            indent=2,
            sort_keys=True,
        )
    )


@main.command("read-state")
@click.option("--node-id", required=True)
@click.option("--endpoint-id", required=True, type=int)
@click.pass_context
def read_state_command(ctx: click.Context, node_id: str, endpoint_id: int) -> None:
    backend = ctx.obj["backend"]
    click.echo(
        json.dumps(
            backend.read_state(node_id=node_id, endpoint_id=endpoint_id),
            indent=2,
            sort_keys=True,
        )
    )


@main.command("invoke-command")
@click.option("--node-id", required=True)
@click.option("--endpoint-id", required=True, type=int)
@click.option("--command", "command_name", required=True)
@click.option("--args-json", default="{}", show_default=True)
@click.pass_context
def invoke_command_command(
    ctx: click.Context,
    node_id: str,
    endpoint_id: int,
    command_name: str,
    args_json: str,
) -> None:
    backend = ctx.obj["backend"]
    args = json.loads(args_json)
    click.echo(
        json.dumps(
            backend.invoke_command(
                node_id=node_id,
                endpoint_id=endpoint_id,
                command=command_name,
                args=args if isinstance(args, dict) else {},
            ),
            indent=2,
            sort_keys=True,
        )
    )


@main.command("subscribe-state")
@click.option("--node-id", required=True)
@click.option("--endpoint-id", required=True, type=int)
@click.option("--min-interval-seconds", default=1, show_default=True, type=int)
@click.option("--max-interval-seconds", default=300, show_default=True, type=int)
@click.pass_context
def subscribe_state_command(
    ctx: click.Context,
    node_id: str,
    endpoint_id: int,
    min_interval_seconds: int,
    max_interval_seconds: int,
) -> None:
    backend = ctx.obj["backend"]
    subscription = backend.subscribe_state(
        node_id=node_id,
        endpoint_id=endpoint_id,
        min_interval_seconds=min_interval_seconds,
        max_interval_seconds=max_interval_seconds,
    )

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _handle_shutdown(_signum, _frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    try:
        for payload in subscription:
            click.echo(json.dumps(payload, sort_keys=True), nl=True)
    except KeyboardInterrupt:
        return
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    main()
