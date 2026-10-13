"""gRPC adapter for the Runbook Agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

import grpc

from agent_connector.agents.runbook import recommend_actions
from agent_connector.domain.models import IncidentRequest, RunbookResponse
from agent_connector.domain.validation import IncidentValidationError
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.requests import validated_incident_from_proto
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
        try:
            incident = validated_incident_from_proto(request)
        except IncidentValidationError as error:
            LOGGER.info("Runbook request rejected: %s", error)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))

        try:
            result = await asyncio.to_thread(self._analyzer, incident)
        except Exception:
            LOGGER.exception(
                "unexpected Runbook Agent failure for incident %s",
                incident.incident_id,
            )
            await context.abort(grpc.StatusCode.INTERNAL, "internal agent error")

        return runbook_response_to_proto(result)
