"""Tools the agentic coordinator may choose after inspecting an incident."""

from __future__ import annotations

from dataclasses import dataclass
import time

from agent_connector.agents.log_analysis import analyze_logs
from agent_connector.agents.runbook import recommend_actions
from agent_connector.agents.severity import analyze_severity
from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    IncidentRequest,
    LogAnalysisResult,
    RunbookResponse,
    SeverityResponse,
)

TOOL_ANALYZE_SEVERITY = "analyze_severity"
TOOL_RECOMMEND_RUNBOOK = "recommend_runbook"
TOOL_ANALYZE_LOGS = "analyze_logs"
TOOL_FINISH = "finish"

TOOL_NAMES = (
    TOOL_ANALYZE_SEVERITY,
    TOOL_RECOMMEND_RUNBOOK,
    TOOL_ANALYZE_LOGS,
    TOOL_FINISH,
)


@dataclass
class ToolResult:
    tool: str
    status: AgentStatus
    detail: str
    latency_ms: float
    severity: SeverityResponse | None = None
    runbook: RunbookResponse | None = None
    log_analysis: LogAnalysisResult | None = None


def execute_tool(name: str, request: IncidentRequest) -> ToolResult:
    """Run one local agent function chosen by the planner."""
    started = time.perf_counter()
    if name == TOOL_ANALYZE_SEVERITY:
        response = analyze_severity(request)
        detail = (
            f"level={response.level.value} score={response.score}"
            if response.status == AgentStatus.OK
            else response.error_message
        )
        return ToolResult(
            tool=name,
            status=response.status,
            detail=detail,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            severity=response,
        )
    if name == TOOL_RECOMMEND_RUNBOOK:
        response = recommend_actions(request)
        titles = ", ".join(item.title for item in response.recommendations[:3]) or "none"
        detail = (
            f"recommendations={len(response.recommendations)} ({titles})"
            if response.status == AgentStatus.OK
            else response.error_message
        )
        return ToolResult(
            tool=name,
            status=response.status,
            detail=detail,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            runbook=response,
        )
    if name == TOOL_ANALYZE_LOGS:
        response = analyze_logs(request)
        detail = (
            (response.likely_cause or response.summary or "ok")
            if response.status == AgentStatus.OK
            else response.error_message
        )
        return ToolResult(
            tool=name,
            status=response.status,
            detail=detail,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            log_analysis=response,
        )
    if name == TOOL_FINISH:
        return ToolResult(
            tool=name,
            status=AgentStatus.OK,
            detail="finished",
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
    return ToolResult(
        tool=name,
        status=AgentStatus.INVALID_ARGUMENT,
        detail=f"unknown tool {name!r}",
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )


def outcome_from_result(result: ToolResult) -> AgentOutcome | None:
    if result.tool == TOOL_FINISH:
        return None
    name = {
        TOOL_ANALYZE_SEVERITY: "severity",
        TOOL_RECOMMEND_RUNBOOK: "runbook",
        TOOL_ANALYZE_LOGS: "log_analysis",
    }.get(result.tool, result.tool)
    return AgentOutcome(
        name=name,
        status=result.status,
        error_message="" if result.status == AgentStatus.OK else result.detail,
        latency_ms=result.latency_ms,
    )
