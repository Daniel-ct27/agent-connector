"""Shared execution policy for unary agent RPCs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import TypeVar

import grpc
from google.protobuf.message import Message

from agent_connector.domain.models import IncidentRequest
from agent_connector.domain.validation import IncidentValidationError
from agent_connector.generated import incident_pb2 as pb
from agent_connector.grpc_services.requests import validated_incident_from_proto


DomainResponse = TypeVar("DomainResponse")
ProtoResponse = TypeVar("ProtoResponse", bound=Message)


async def execute_unary_agent(
    request: pb.IncidentRequest,
    context: grpc.aio.ServicerContext,
    *,
    agent_name: str,
    analyzer: Callable[[IncidentRequest], DomainResponse],
    response_to_proto: Callable[[DomainResponse], ProtoResponse],
    logger: logging.Logger,
) -> ProtoResponse:
    """Validate, analyze, and convert without blocking the event loop."""
    try:
        incident = await asyncio.to_thread(validated_incident_from_proto, request)
    except IncidentValidationError as error:
        logger.info("%s request rejected: %s", agent_name, error)
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))

    def analyze_and_convert() -> ProtoResponse:
        return response_to_proto(analyzer(incident))

    try:
        return await asyncio.to_thread(analyze_and_convert)
    except Exception:
        logger.exception(
            "unexpected %s failure for incident %s",
            agent_name,
            incident.incident_id,
        )
        await context.abort(grpc.StatusCode.INTERNAL, "internal agent error")
