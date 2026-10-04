"""Deterministic severity scoring for incident analysis.

Signals (from project spec):
- error / fatal frequency
- number of affected services
- incident duration
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from agent_connector.domain.models import (
    AgentStatus,
    EvidenceItem,
    IncidentRequest,
    LogEntry,
    LogLevel,
    SeverityLevel,
    SeverityResponse,
)

_ERROR_LIKE = {LogLevel.ERROR, LogLevel.FATAL}
_LEVEL_POINTS = {
    LogLevel.WARN: 2,
    LogLevel.ERROR: 8,
    LogLevel.FATAL: 20,
}

# Score → level thresholds (inclusive lower bounds).
_LEVEL_THRESHOLDS = (
    (75, SeverityLevel.CRITICAL),
    (50, SeverityLevel.HIGH),
    (25, SeverityLevel.MEDIUM),
    (0, SeverityLevel.LOW),
)


def analyze_severity(request: IncidentRequest) -> SeverityResponse:
    """Score an incident and return a SeverityResponse."""
    if not request.incident_id.strip():
        return SeverityResponse(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="incident_id is required",
        )
    if not request.logs:
        return SeverityResponse(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="logs must not be empty",
        )

    error_count = sum(1 for entry in request.logs if entry.level in _ERROR_LIKE)
    fatal_count = sum(1 for entry in request.logs if entry.level == LogLevel.FATAL)
    services = sorted({entry.service for entry in request.logs if entry.service})
    duration_seconds = _duration_seconds(request.logs)

    score = _compute_score(
        error_count=error_count,
        fatal_count=fatal_count,
        service_count=len(services),
        duration_seconds=duration_seconds,
        logs=request.logs,
    )
    level = _level_for_score(score)
    evidence = _build_evidence(request.logs)
    rationale = (
        f"score={score} from error_like={error_count}, fatal={fatal_count}, "
        f"services={len(services)}, duration_s={duration_seconds:.1f}"
    )

    return SeverityResponse(
        level=level,
        score=score,
        evidence=evidence,
        rationale=rationale,
        status=AgentStatus.OK,
    )


def _compute_score(
    *,
    error_count: int,
    fatal_count: int,
    service_count: int,
    duration_seconds: float,
    logs: list[LogEntry],
) -> int:
    # Frequency: capped contribution from error-like events.
    frequency_score = min(40, error_count * 8)
    # Breadth: more services → higher impact.
    service_score = min(30, max(0, service_count - 1) * 15)
    # Duration: longer open incidents score higher (minutes scale).
    if duration_seconds >= 300:
        duration_score = 20
    elif duration_seconds >= 60:
        duration_score = 12
    elif duration_seconds >= 10:
        duration_score = 6
    else:
        duration_score = 2
    # Fatal presence is a hard bump.
    fatal_score = min(20, fatal_count * 15)
    # Soft signal from warn/error/fatal point totals (keeps small incidents above 0).
    level_points = sum(_LEVEL_POINTS.get(entry.level, 0) for entry in logs)
    soft_score = min(10, level_points // 4)

    total = frequency_score + service_score + duration_score + fatal_score + soft_score
    return max(0, min(100, total))


def _level_for_score(score: int) -> SeverityLevel:
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return SeverityLevel.LOW


def _duration_seconds(logs: list[LogEntry]) -> float:
    timestamps: list[datetime] = []
    for entry in logs:
        parsed = _parse_timestamp(entry.timestamp)
        if parsed is not None:
            timestamps.append(parsed)
    if len(timestamps) < 2:
        return 0.0
    return (max(timestamps) - min(timestamps)).total_seconds()


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _build_evidence(logs: list[LogEntry]) -> list[EvidenceItem]:
    by_service: Counter[str] = Counter()
    samples: dict[str, str] = {}
    for entry in logs:
        if entry.level not in _ERROR_LIKE:
            continue
        by_service[entry.service] += 1
        samples.setdefault(entry.service, entry.message)

    evidence: list[EvidenceItem] = []
    for service, count in sorted(by_service.items()):
        evidence.append(
            EvidenceItem(
                service=service,
                summary=f"{count} error-like log(s)",
                count=count,
                sample_message=samples.get(service, ""),
            )
        )
    return evidence
