"""Log Analysis Agent gRPC process (default 127.0.0.1:50053)."""

from __future__ import annotations

import logging

import grpc

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.analyzers import build_analyzer
from agent_connector.config import DEFAULT_GRPC_HOST, LOG_ANALYSIS_GRPC_PORT
from agent_connector.domain.models import IncidentRequest
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.log_analysis import LogAnalysisGrpcService
from agent_connector.servers.runtime import run_agent_process

_LOG = logging.getLogger(__name__)


def register(server: grpc.aio.Server) -> None:
    analyzer = build_analyzer()
    _LOG.info("Log Analysis using analyzer=%s", analyzer.name)

    def unary(request: IncidentRequest):
        return analyze_logs(request, analyzer=analyzer)

    def stream(request: IncidentRequest):
        return analyze_logs_stream(request, analyzer=analyzer)

    pb_grpc.add_LogAnalysisServiceServicer_to_server(
        LogAnalysisGrpcService(unary, stream),
        server,
    )


def main() -> None:
    run_agent_process(
        register,
        service_name="Log Analysis Agent",
        host=DEFAULT_GRPC_HOST,
        port=LOG_ANALYSIS_GRPC_PORT,
    )


if __name__ == "__main__":
    main()
