"""Shared validation rules for incident requests."""

from __future__ import annotations

from agent_connector.domain.models import IncidentRequest


MAX_LOG_ENTRIES = 5_000


class IncidentValidationError(ValueError):
    """Raised when an incident request cannot be analyzed."""


def validate_incident_request(request: IncidentRequest) -> None:
    """Raise ``IncidentValidationError`` for the first invalid field."""
    if not request.incident_id.strip():
        raise IncidentValidationError("incident_id is required")
    if not request.logs:
        raise IncidentValidationError("logs must not be empty")
    if len(request.logs) > MAX_LOG_ENTRIES:
        raise IncidentValidationError(
            f"logs must contain at most {MAX_LOG_ENTRIES} entries"
        )
