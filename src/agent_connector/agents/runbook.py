"""Keyword / rule-based runbook matching for incident analysis."""

from __future__ import annotations

from agent_connector.domain.models import (
    AgentStatus,
    IncidentRequest,
    LogLevel,
    RunbookMatch,
    RunbookResponse,
    RunbookStep,
)
from agent_connector.domain.validation import (
    IncidentValidationError,
    validate_incident_request,
)
from agent_connector.runbooks.catalog import RUNBOOKS, RunbookDefinition


def recommend_actions(request: IncidentRequest) -> RunbookResponse:
    """Match incident evidence to local runbook entries."""
    try:
        validate_incident_request(request)
    except IncidentValidationError as error:
        return RunbookResponse(
            status=AgentStatus.INVALID_ARGUMENT,
            error_message=str(error),
        )

    matches: list[RunbookMatch] = []
    for definition in RUNBOOKS:
        match = _match_runbook(definition, request)
        if match is not None:
            matches.append(match)

    matches.sort(key=lambda item: item.confidence, reverse=True)
    return RunbookResponse(
        recommendations=matches,
        status=AgentStatus.OK,
    )


def _match_runbook(
    definition: RunbookDefinition,
    request: IncidentRequest,
) -> RunbookMatch | None:
    matched_terms: set[str] = set()
    primary_match = False

    scenario_matches = _matching_keywords(definition, request.scenario)
    if scenario_matches:
        primary_match = True
        matched_terms.update(scenario_matches)

    for entry in request.logs:
        if entry.level not in {LogLevel.ERROR, LogLevel.FATAL}:
            continue

        contextual_matches = _matching_keywords(
            definition,
            f"{entry.service} {entry.message}",
        )
        if contextual_matches:
            primary_match = True
            matched_terms.update(contextual_matches)

        # Metadata can explain an existing match, but cannot create one alone.
        metadata_text = " ".join(entry.metadata.values())
        matched_terms.update(_matching_keywords(definition, metadata_text))

    if not primary_match:
        return None

    # Preserve catalog order so responses remain deterministic.
    matched = [term for term in definition.keywords if term in matched_terms]

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


def _matching_keywords(
    definition: RunbookDefinition,
    text: str,
) -> set[str]:
    searchable = text.lower()
    return {
        keyword
        for keyword in definition.keywords
        if keyword.lower() in searchable
    }
