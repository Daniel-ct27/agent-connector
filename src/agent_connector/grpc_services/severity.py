"""gRPC adapter for the Severity Agent."""

from __future__ import annotations

from collections.abc import Callable
import logging

import grpc

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, SeverityResponse
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.unary import execute_unary_agent
from agent_connector.protocol.protobuf import (
    severity_response_to_proto,
)


LOGGER = logging.getLogger(__name__)
SeverityAnalyzer = Callable[[IncidentRequest], SeverityResponse]


class SeverityGrpcService(pb_grpc.SeverityServiceServicer):
    """Expose the protocol-independent Severity Agent through gRPC."""

    def __init__(self, analyzer: SeverityAnalyzer = analyze_severity) -> None:
        self._analyzer = analyzer

    async def AnalyzeSeverity(
        self,
        request: pb.IncidentRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.SeverityResponse:
        return await execute_unary_agent(
            request,
            context,
            agent_name="Severity Agent",
            analyzer=self._analyzer,
            response_to_proto=severity_response_to_proto,
            logger=LOGGER,
        )
