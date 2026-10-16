"""Runbook Agent gRPC process (default 127.0.0.1:50052)."""

from __future__ import annotations

import grpc

from agent_connector.config import DEFAULT_GRPC_HOST, RUNBOOK_GRPC_PORT
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.runbook import RunbookGrpcService
from agent_connector.servers.runtime import run_agent_process


def register(server: grpc.aio.Server) -> None:
    pb_grpc.add_RunbookServiceServicer_to_server(RunbookGrpcService(), server)


def main() -> None:
    run_agent_process(
        register,
        service_name="Runbook Agent",
        host=DEFAULT_GRPC_HOST,
        port=RUNBOOK_GRPC_PORT,
    )


if __name__ == "__main__":
    main()
