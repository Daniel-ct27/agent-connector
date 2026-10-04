"""Keyword / rule-based runbook matching for incident analysis."""

from __future__ import annotations

from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    RunbookMatch,
    RunbookResponse,
    RunbookStep,
)
from agent_connector.runbooks.catalog import RUNBOOKS, RunbookDefinition


def recommend_actions(request: IncidentRequest) -> RunbookResponse:
    """Match incident evidence to local runbook entries."""
    if not request.incident_id.strip():
        return RunbookResponse(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="incident_id is required",
        )
    if not request.logs:
        return RunbookResponse(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message="logs must not be empty",
        )

    corpus = _build_corpus(request)
    matches: list[RunbookMatch] = []
    for definition in RUNBOOKS:
        match = _match_runbook(definition, corpus)
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda item: item.confidence, reverse=True)
    return RunbookResponse(
        recommendations=matches,
        status=AgentStatus.OK,
    )


def _build_corpus(request: IncidentRequest) -> str:
    parts = [request.scenario, request.incident_id]
    for entry in request.logs:
        parts.append(entry.service)
        parts.append(entry.message)
        parts.extend(entry.metadata.values())
    return " ".join(parts).lower()


def _match_runbook(definition: RunbookDefinition, corpus: str) -> RunbookMatch | None:
    matched = [keyword for keyword in definition.keywords if keyword.lower() in corpus]
    if not matched:
        return None

    confidence = min(1.0, len(matched) / max(3, len(definition.keywords) // 2))
    # Prefer stronger coverage when many keywords hit.
    if len(matched) >= 3:
        confidence = max(confidence, 0.75)
    if len(matched) >= 4:
        confidence = max(confidence, 0.9)

    return RunbookMatch(
        runbook_id=definition.runbook_id,
        title=definition.title,
        confidence=round(confidence, 3),
        matched_terms=matched,
        steps=[
            RunbookStep(order=order, action=action, detail=detail)
            for order, action, detail in definition.steps
        ],
    )
