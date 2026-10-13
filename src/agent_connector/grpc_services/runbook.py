"""gRPC adapter for the Runbook Agent."""

from __future__ import annotations

from collections.abc import Callable
import logging

import grpc

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import IncidentRequest, RunbookResponse
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.unary import execute_unary_agent
from agent_connector.protocol.protobuf import runbook_response_to_proto


LOGGER = logging.getLogger(__name__)
RunbookAnalyzer = Callable[[IncidentRequest], RunbookResponse]


class RunbookGrpcService(pb_grpc.RunbookServiceServicer):
    """Expose the protocol-independent Runbook Agent through gRPC."""

    def __init__(self, analyzer: RunbookAnalyzer = recommend_actions) -> None:
        self._analyzer = analyzer

    async def RecommendActions(
        self,
        request: pb.IncidentRequest,
        context: grpc.aio.ServicerContext,
    ) -> pb.RunbookResponse:
        return await execute_unary_agent(
            request,
            context,
            agent_name="Runbook Agent",
            analyzer=self._analyzer,
            response_to_proto=runbook_response_to_proto,
            logger=LOGGER,
        )
