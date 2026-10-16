"""Validation and conversion at the gRPC request boundary."""

from __future__ import annotations

from agent_connector.domain.models import IncidentRequest
from agent_connector.domain.validation import (
    MAX_LOG_ENTRIES,
    IncidentValidationError,
    validate_incident_request,
)
from agent_connector.generated import incident_pb2 as pb
from agent_connector.grpc_services.limits import validate_grpc_request_size
from agent_connector.protocol.protobuf import incident_request_from_proto


def incident_from_proto(request: pb.IncidentRequest) -> IncidentRequest:
    """Parse a proto request after transport checks; skip agent-level validation.

    Streaming Log Analysis applies domain validation itself so invalid incidents
    can emit an ``ERROR`` event instead of aborting the RPC.
    """
    validate_grpc_request_size(request)
    if len(request.logs) > MAX_LOG_ENTRIES:
        raise IncidentValidationError(
            f"logs must contain at most {MAX_LOG_ENTRIES} entries"
        )

    try:
        return incident_request_from_proto(request)
    except ValueError:
        raise IncidentValidationError(
            "request contains an invalid enum value"
        ) from None


def validated_incident_from_proto(request: pb.IncidentRequest) -> IncidentRequest:
    """Validate transport limits and return the corresponding domain request."""
    incident = incident_from_proto(request)
    validate_incident_request(incident)
    return incident
