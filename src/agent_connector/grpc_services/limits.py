"""Shared gRPC transport limits."""

from __future__ import annotations

from google.protobuf.message import Message

from agent_connector.config import MAX_GRPC_REQUEST_BYTES
from agent_connector.domain.validation import IncidentValidationError


def validate_grpc_request_size(request: Message) -> None:
    """Reject requests at or above the project's gRPC byte ceiling."""
    size = request.ByteSize()
    if size >= MAX_GRPC_REQUEST_BYTES:
        raise IncidentValidationError(
            f"request must be smaller than {MAX_GRPC_REQUEST_BYTES} bytes"
        )
