"""Shared execution policy for unary HTTP agent endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
from typing import TypeVar

from fastapi import HTTPException

from agent_connector.domain.models import IncidentRequest
from agent_connector.domain.validation import (
    IncidentValidationError,
    validate_incident_request,
)


DomainResponse = TypeVar("DomainResponse")


async def execute_http_unary(
    request: IncidentRequest,
    *,
    agent_name: str,
    analyzer: Callable[[IncidentRequest], DomainResponse],
    logger: logging.Logger,
) -> DomainResponse:
    """Validate, analyze off the event loop, and map failures to HTTP errors."""
    try:
        validate_incident_request(request)
    except IncidentValidationError as error:
        logger.info("%s request rejected: %s", agent_name, error)
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        return await asyncio.to_thread(analyzer, request)
    except Exception:
        logger.exception(
            "unexpected %s failure for incident %s",
            agent_name,
            request.incident_id,
        )
        raise HTTPException(status_code=500, detail="internal agent error") from None
