"""gRPC adapter for unary Log Analysis."""

from __future__ import annotations

from collections.abc import Callable
import logging

import grpc

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.domain.models import IncidentRequest, LogAnalysisResult
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.unary import execute_unary_agent
from agent_connector.protocol.protobuf import log_analysis_result_to_proto


LOGGER = logging.getLogger(__name__)
LogAnalyzer = Callable[[IncidentRequest], LogAnalysisResult]


class LogAnalysisGrpcService(pb_grpc.LogAnalysisServiceServicer):
    """Expose Log Analysis operations through gRPC."""

    def __init__(self, analyzer: LogAnalyzer = analyze_logs) -> None:
        self._analyzer = analyzer

    async def AnalyzeLogs(
        self,
        request: pb.IncidentRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.LogAnalysisResult:
        return await execute_unary_agent(
            request,
            context,
            agent_name="Log Analysis Agent",
            analyzer=self._analyzer,
            response_to_proto=log_analysis_result_to_proto,
            logger=LOGGER,
        )

    async def AnalyzeLogsStream(
        self,
        request: pb.IncidentRequest,
        context: grpc.aio.ServicerContext,
    ):
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "streaming log analysis is not available",
        )
        if False:
            yield pb.LogAnalysisEvent()
