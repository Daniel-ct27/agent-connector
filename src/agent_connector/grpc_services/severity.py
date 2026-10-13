"""gRPC adapter for the Severity Agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

import grpc

from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import IncidentRequest, SeverityResponse
from agent_connector.domain.validation import (
    MAX_LOG_ENTRIES,
    IncidentValidationError,
    validate_incident_request,
)
from agent_connector.generated import incident_pb2 as pb
from agent_connector.generated import incident_pb2_grpc as pb_grpc
from agent_connector.grpc_services.limits import validate_grpc_request_size
from agent_connector.protocol.protobuf import (
    incident_request_from_proto,
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
        try:
            validate_grpc_request_size(request)
            if len(request.logs) > MAX_LOG_ENTRIES:
                raise IncidentValidationError(
                    f"logs must contain at most {MAX_LOG_ENTRIES} entries"
                )
            incident = incident_request_from_proto(request)
            validate_incident_request(incident)
        except IncidentValidationError as error:
            await self._abort_invalid(context, str(error))
        except ValueError:
            await self._abort_invalid(
                context,
                "request contains an invalid enum value",
            )

        try:
            result = await asyncio.to_thread(self._analyzer, incident)
        except Exception:
            LOGGER.exception(
                "unexpected Severity Agent failure for incident %s",
                incident.incident_id,
            )
            await context.abort(grpc.StatusCode.INTERNAL, "internal agent error")

        return severity_response_to_proto(result)

    @staticmethod
    async def _abort_invalid(
        context: grpc.aio.ServicerContext,
        message: str,
    ) -> None:
        LOGGER.info("Severity request rejected: %s", message)
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, message)
