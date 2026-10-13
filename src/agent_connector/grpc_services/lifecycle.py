"""Reusable lifecycle helpers for local async gRPC servers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import grpc

from agent_connector.config import (
    DEFAULT_GRPC_HOST,
    GRPC_SHUTDOWN_GRACE_SECONDS,
)


class ServerBindError(RuntimeError):
    """Raised when a gRPC server cannot bind its requested address."""


@dataclass(frozen=True)
class RunningServer:
    """A started server and the address selected by gRPC."""

    server: grpc.aio.Server
    host: str
    port: int

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"

    async def stop(self, grace: float = GRPC_SHUTDOWN_GRACE_SECONDS) -> None:
        await self.server.stop(grace)


async def start_server(
    register: Callable[[grpc.aio.Server], None],
    *,
    host: str = DEFAULT_GRPC_HOST,
    port: int,
) -> RunningServer:
    """Create, register, bind, and start one async gRPC server."""
    server = grpc.aio.server()
    register(server)
    address = f"{host}:{port}"
    try:
        bound_port = server.add_insecure_port(address)
    except RuntimeError:
        await server.stop(0)
        raise ServerBindError(f"unable to bind gRPC server to {address}") from None
    if bound_port == 0:
        await server.stop(0)
        raise ServerBindError(f"unable to bind gRPC server to {address}")

    try:
        await server.start()
    except BaseException:
        await server.stop(0)
        raise

    return RunningServer(server=server, host=host, port=bound_port)
