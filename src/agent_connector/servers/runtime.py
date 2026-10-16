"""Shared async runner for independently launched agent gRPC processes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import grpc

from agent_connector.config import DEFAULT_GRPC_HOST, GRPC_SHUTDOWN_GRACE_SECONDS
from agent_connector.grpc_services.lifecycle import ServerBindError, start_server

LOGGER = logging.getLogger(__name__)
RegisterFn = Callable[[grpc.aio.Server], None]


async def serve_agent(
    register: RegisterFn,
    *,
    service_name: str,
    host: str = DEFAULT_GRPC_HOST,
    port: int,
) -> None:
    """Bind, start, and wait until the process is asked to stop."""
    running = await start_server(register, host=host, port=port)
    LOGGER.info("%s listening on %s", service_name, running.target)
    try:
        await running.server.wait_for_termination()
    finally:
        await running.stop(GRPC_SHUTDOWN_GRACE_SECONDS)


def run_agent_process(
    register: RegisterFn,
    *,
    service_name: str,
    host: str = DEFAULT_GRPC_HOST,
    port: int,
) -> None:
    """Process entry helper used by the three agent server modules."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(
            serve_agent(
                register,
                service_name=service_name,
                host=host,
                port=port,
            )
        )
    except ServerBindError as error:
        LOGGER.error("%s", error)
        raise SystemExit(1) from error
    except KeyboardInterrupt:
        LOGGER.info("%s shut down", service_name)
        raise SystemExit(0) from None
