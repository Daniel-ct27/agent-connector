"""Build a compact observation of an incident for the planner."""

from __future__ import annotations

from collections import Counter

from agent_connector.domain.models import IncidentRequest, LogLevel

_ERROR_LIKE = {LogLevel.ERROR, LogLevel.FATAL}


def observe_incident(request: IncidentRequest, *, sample_limit: int = 8) -> str:
    """Return a short text observation the planner can reason over."""
    levels = Counter(entry.level.value for entry in request.logs)
    services = sorted({entry.service for entry in request.logs if entry.service})
    error_like = [entry for entry in request.logs if entry.level in _ERROR_LIKE]
    samples = error_like[:sample_limit] or request.logs[:sample_limit]
    sample_lines = [
        f"- [{entry.level.value}] {entry.service}: {entry.message[:160]}"
        for entry in samples
    ]
    return "\n".join(
        [
            f"incident_id={request.incident_id}",
            f"scenario={request.scenario or '(none)'}",
            f"log_count={len(request.logs)}",
            f"levels={dict(levels)}",
            f"services={services}",
            f"error_like_count={len(error_like)}",
            "sample_logs:",
            *sample_lines,
        ]
    )


def has_error_like_logs(request: IncidentRequest) -> bool:
    return any(entry.level in _ERROR_LIKE for entry in request.logs)
