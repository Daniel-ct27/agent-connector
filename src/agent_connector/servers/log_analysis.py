"""Log Analysis Agent gRPC process (default 127.0.0.1:50053)."""

from __future__ import annotations

import grpc

from agent_connector.config import DEFAULT_GRPC_HOST, LOG_ANALYSIS_GRPC_PORT
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.servers.runtime import run_agent_process


def register(server: grpc.aio.Server) -> None:
    pb_grpc.add_LogAnalysisServiceServicer_to_server(LogAnalysisGrpcService(), server)


def main() -> None:
    run_agent_process(
        register,
        service_name="Log Analysis Agent",
        host=DEFAULT_GRPC_HOST,
        port=LOG_ANALYSIS_GRPC_PORT,
    )


if __name__ == "__main__":
    main()
