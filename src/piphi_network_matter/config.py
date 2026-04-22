from __future__ import annotations

from dataclasses import asdict, dataclass
import os


@dataclass(frozen=True)
class MatterSidecarConfig:
    log_level: str
    adapter_kind: str
    poll_interval_seconds: float
    storage_dir: str
    subscriptions_enabled: bool = True
    subscription_min_interval_seconds: int = 1
    subscription_max_interval_seconds: int = 300
    subscription_retry_seconds: float = 5.0
    adapter_data_file: str | None = None
    adapter_command: str | None = None
    auto_configure_commissioned_devices: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8710


DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_ADAPTER_KIND = "null"
DEFAULT_POLL_INTERVAL_SECONDS = 30.0
DEFAULT_STORAGE_DIR = "/var/lib/piphi/matter"
DEFAULT_SUBSCRIPTIONS_ENABLED = True
DEFAULT_SUBSCRIPTION_MIN_INTERVAL_SECONDS = 1
DEFAULT_SUBSCRIPTION_MAX_INTERVAL_SECONDS = 300
DEFAULT_SUBSCRIPTION_RETRY_SECONDS = 5.0
DEFAULT_AUTO_CONFIGURE_COMMISSIONED_DEVICES = True
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8710


def load_sidecar_config() -> MatterSidecarConfig:
    return MatterSidecarConfig(
        log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        adapter_kind=os.getenv("MATTER_ADAPTER_KIND", DEFAULT_ADAPTER_KIND).strip().lower() or DEFAULT_ADAPTER_KIND,
        poll_interval_seconds=float(os.getenv("MATTER_POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS))),
        storage_dir=os.getenv("MATTER_STORAGE_DIR", DEFAULT_STORAGE_DIR),
        subscriptions_enabled=_env_flag(
            "MATTER_SUBSCRIPTIONS_ENABLED",
            DEFAULT_SUBSCRIPTIONS_ENABLED,
        ),
        subscription_min_interval_seconds=int(
            os.getenv(
                "MATTER_SUBSCRIPTION_MIN_INTERVAL_SECONDS",
                str(DEFAULT_SUBSCRIPTION_MIN_INTERVAL_SECONDS),
            )
        ),
        subscription_max_interval_seconds=int(
            os.getenv(
                "MATTER_SUBSCRIPTION_MAX_INTERVAL_SECONDS",
                str(DEFAULT_SUBSCRIPTION_MAX_INTERVAL_SECONDS),
            )
        ),
        subscription_retry_seconds=float(
            os.getenv(
                "MATTER_SUBSCRIPTION_RETRY_SECONDS",
                str(DEFAULT_SUBSCRIPTION_RETRY_SECONDS),
            )
        ),
        adapter_data_file=os.getenv("MATTER_ADAPTER_DATA_FILE") or None,
        adapter_command=os.getenv("MATTER_ADAPTER_COMMAND") or None,
        auto_configure_commissioned_devices=_env_flag(
            "MATTER_AUTO_CONFIGURE_COMMISSIONED_DEVICES",
            DEFAULT_AUTO_CONFIGURE_COMMISSIONED_DEVICES,
        ),
        api_host=os.getenv("MATTER_API_HOST", DEFAULT_API_HOST),
        api_port=int(os.getenv("MATTER_API_PORT", str(DEFAULT_API_PORT))),
    )


def config_to_dict(config: MatterSidecarConfig) -> dict[str, object]:
    return asdict(config)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
