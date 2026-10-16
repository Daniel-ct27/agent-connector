"""gRPC adapter for unary and server-streaming Log Analysis."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
import logging

import grpc

from agent_connector.agents.log_analysis import analyze_logs, analyze_logs_stream
from agent_connector.domain.models import (
    IncidentRequest,
    LogAnalysisEvent,
    LogAnalysisResult,
)
from agent_connector.domain.validation import IncidentValidationError
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.requests import incident_from_proto
from agent_connector.grpc_services.unary import execute_unary_agent
from agent_connector.protocol.protobuf import (
    log_analysis_event_to_proto,
    log_analysis_result_to_proto,
)


LOGGER = logging.getLogger(__name__)
LogAnalyzer = Callable[[IncidentRequest], LogAnalysisResult]
LogStreamAnalyzer = Callable[[IncidentRequest], Iterator[LogAnalysisEvent]]


class LogAnalysisGrpcService(pb_grpc.LogAnalysisServiceServicer):
    """Expose Log Analysis operations through gRPC."""

    def __init__(
        self,
        analyzer: LogAnalyzer = analyze_logs,
        stream_analyzer: LogStreamAnalyzer = analyze_logs_stream,
    ) -> None:
        self._analyzer = analyzer
        self._stream_analyzer = stream_analyzer

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
    ) -> AsyncIterator[pb.LogAnalysisEvent]:
        try:
            incident = await asyncio.to_thread(incident_from_proto, request)
        except IncidentValidationError as error:
            LOGGER.info("Log Analysis stream request rejected: %s", error)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
            return

        iterator = self._stream_analyzer(incident)

        def next_event() -> LogAnalysisEvent | None:
            try:
                return next(iterator)
            except StopIteration:
                return None

        while True:
            try:
                event = await asyncio.to_thread(next_event)
            except Exception:
                LOGGER.exception(
                    "unexpected Log Analysis stream failure for incident %s",
                    incident.incident_id,
                )
                await context.abort(grpc.StatusCode.INTERNAL, "internal agent error")
                return

            if event is None:
                return

            try:
                yield log_analysis_event_to_proto(event)
            except Exception:
                LOGGER.exception(
                    "unexpected Log Analysis stream conversion failure for incident %s",
                    incident.incident_id,
                )
                await context.abort(grpc.StatusCode.INTERNAL, "internal agent error")
                return
