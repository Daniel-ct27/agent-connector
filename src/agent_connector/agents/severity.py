"""Deterministic severity scoring for incident analysis.

Signals (from project spec):
- error / fatal frequency
- number of affected services
- incident duration
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import log1p

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
_FREQUENCY_WEIGHT = 50
_BREADTH_WEIGHT = 25
_DURATION_WEIGHT = 15
_FATAL_WEIGHT = 10

_FREQUENCY_SATURATION_COUNT = 100
_BREADTH_SATURATION_SERVICES = 5
_DURATION_SATURATION_SECONDS = 300
_FATAL_SATURATION_COUNT = 2

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

    error_logs = [entry for entry in request.logs if entry.level in _ERROR_LIKE]
    error_count = len(error_logs)
    fatal_count = sum(1 for entry in error_logs if entry.level == LogLevel.FATAL)
    affected_services = {entry.service for entry in error_logs if entry.service}
    duration_seconds = _duration_seconds(error_logs)

    score = _compute_score(
        error_count=error_count,
        fatal_count=fatal_count,
        service_count=len(affected_services),
        duration_seconds=duration_seconds,
    )
    level = _level_for_score(score)
    evidence = _build_evidence(request.logs)
    rationale = (
        f"score={score} from error_like={error_count}, fatal={fatal_count}, "
        f"services={len(affected_services)}, duration_s={duration_seconds:.1f}"
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
) -> int:
    # Frequency: capped contribution from error-like events.
    frequency_signal = min(
        1.0,
        log1p(max(0, error_count)) / log1p(_FREQUENCY_SATURATION_COUNT),
    )
    # Breadth: more services → higher impact.
    breadth_signal = min(
        1.0,
        max(0, service_count - 1) / (_BREADTH_SATURATION_SERVICES - 1),
    )
    # Duration: longer open incidents score higher (minutes scale).
    duration_signal = min(
        1.0,
        max(0.0, duration_seconds) / _DURATION_SATURATION_SECONDS,
    )
    # Fatal presence is a hard bump.
    fatal_signal = min(1.0, max(0, fatal_count) / _FATAL_SATURATION_COUNT)
    total = (
        frequency_signal * _FREQUENCY_WEIGHT
        + breadth_signal * _BREADTH_WEIGHT
        + duration_signal * _DURATION_WEIGHT
        + fatal_signal * _FATAL_WEIGHT
    )
    return max(0, min(100, round(total)))


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
