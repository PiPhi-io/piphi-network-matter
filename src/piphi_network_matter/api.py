from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from .service import MatterSidecarService


class ConfigureDeviceRequest(BaseModel):
    node_id: str
    endpoint_id: int
    alias: str | None = None
    preferred_source: str = "matter"


class RegistryDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    node_id: str
    endpoint_id: int


class CommissionWithCodeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    node_id: str
    setup_payload: str
    endpoint_id: int = 1
    name: str | None = None


class RemoveConfigResponse(BaseModel):
    removed: bool
    node_id: str
    endpoint_id: int


class HealthResponse(BaseModel):
    ok: bool
    service: dict[str, Any]


class MatterDiscoveryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    device_id: str
    node_id: str
    endpoint_id: int
    name: str
    vendor_name: str | None = None
    product_name: str | None = None
    device_types: list[str]
    capabilities: list[str]
    command_bindings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any]


class MatterCommissionableRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    instance_name: str | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    device_type: int | str | None = None
    long_discriminator: int | None = None
    commissioning_mode: int | None = None
    name: str | None = None
    addresses: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfiguredDeviceRecord(BaseModel):
    node_id: str
    endpoint_id: int
    alias: str | None = None
    enabled: bool
    preferred_source: str


class RegistryDeviceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    node_id: str
    endpoint_id: int


class TelemetryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    config_key: str
    node_id: str
    endpoint_id: int
    preferred_source: str
    alias: str | None = None
    read_failed: bool
    sampled_at: str
    state: dict[str, Any] | None = None
    error: str | None = None


class InvokeCommandRequest(BaseModel):
    node_id: str
    endpoint_id: int
    command: str
    args: dict[str, Any] = Field(default_factory=dict)


def create_app(service: MatterSidecarService) -> FastAPI:
    service.mark_started()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service.mark_started()
        await service.start_background_runtime()
        try:
            yield
        finally:
            await service.stop_background_runtime()

    app = FastAPI(
        title="PiPhi Matter Sidecar",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service=service.snapshot())

    @app.get("/v1/snapshot")
    async def snapshot() -> dict[str, Any]:
        return service.snapshot()

    @app.get("/v1/devices/discover", response_model=list[MatterDiscoveryRecord])
    async def discover_devices(node_id: str | None = None) -> list[dict[str, Any]]:
        devices = await service.discover_devices(node_id=node_id)
        return [device.discovery_record() for device in devices]

    @app.get("/entities")
    async def list_entities() -> dict[str, Any]:
        return await service.list_entities()

    @app.get("/v1/discovery/commissionables", response_model=list[MatterCommissionableRecord])
    async def discover_commissionables(timeout_seconds: int = 5) -> list[dict[str, Any]]:
        try:
            return await service.discover_commissionables(timeout_seconds=timeout_seconds)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/v1/registry", response_model=list[RegistryDeviceRecord])
    async def list_registry() -> list[dict[str, Any]]:
        return await service.list_registry_devices()

    @app.post(
        "/v1/registry",
        response_model=RegistryDeviceRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def upsert_registry(payload: RegistryDeviceRequest) -> dict[str, Any]:
        try:
            return await service.upsert_registry_device(device=payload.model_dump())
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.post(
        "/v1/commission/code",
        response_model=RegistryDeviceRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def commission_with_code(payload: CommissionWithCodeRequest) -> dict[str, Any]:
        try:
            return await service.commission_device_with_code(
                node_id=payload.node_id,
                setup_payload=payload.setup_payload,
                device=payload.model_dump(exclude={"node_id", "setup_payload"}),
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/v1/registry/{node_id}/{endpoint_id}", response_model=RemoveConfigResponse)
    async def remove_registry(node_id: str, endpoint_id: int) -> RemoveConfigResponse:
        try:
            removed = await service.remove_registry_device(node_id=node_id, endpoint_id=endpoint_id)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Registry device {node_id}/{endpoint_id} was not found.",
            )
        return RemoveConfigResponse(removed=True, node_id=node_id, endpoint_id=endpoint_id)

    @app.get("/v1/configs", response_model=list[ConfiguredDeviceRecord])
    async def list_configs() -> list[dict[str, Any]]:
        return [item.to_dict() for item in service.list_configs()]

    @app.post(
        "/v1/configs",
        response_model=ConfiguredDeviceRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def configure_device(payload: ConfigureDeviceRequest) -> dict[str, Any]:
        try:
            configured = await service.configure_device(
                node_id=payload.node_id,
                endpoint_id=payload.endpoint_id,
                alias=payload.alias,
                preferred_source=payload.preferred_source,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return configured.to_dict()

    @app.delete("/v1/configs/{node_id}/{endpoint_id}", response_model=RemoveConfigResponse)
    async def remove_configured_device(node_id: str, endpoint_id: int) -> RemoveConfigResponse:
        removed = service.remove_configured_device(node_id=node_id, endpoint_id=endpoint_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Config {node_id}/{endpoint_id} was not found.",
            )
        return RemoveConfigResponse(removed=True, node_id=node_id, endpoint_id=endpoint_id)

    @app.post("/v1/telemetry/poll", response_model=list[TelemetryRecord])
    async def poll_telemetry() -> list[dict[str, Any]]:
        return await service.poll_configured_devices()

    @app.post("/v1/commands/invoke")
    async def invoke_command(payload: InvokeCommandRequest) -> dict[str, Any]:
        try:
            return await service.invoke_command(
                node_id=payload.node_id,
                endpoint_id=payload.endpoint_id,
                command=payload.command,
                args=payload.args,
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return app


def serve_api(service: MatterSidecarService) -> None:
    uvicorn.run(
        create_app(service),
        host=service.config.api_host,
        port=int(service.config.api_port),
        log_level=service.config.log_level.lower(),
    )
