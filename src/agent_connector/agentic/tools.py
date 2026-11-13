"""Tools the agentic coordinator may choose after inspecting an incident."""

from __future__ import annotations

from dataclasses import dataclass, field
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

TOOL_HEADLINES = {
    TOOL_ANALYZE_SEVERITY: "Severity assessment",
    TOOL_RECOMMEND_RUNBOOK: "Runbook match",
    TOOL_ANALYZE_LOGS: "Log forensics",
    TOOL_FINISH: "Handoff",
    "observe": "Signal intake",
    "plan": "Coordinator decision",
}


@dataclass
class ToolResult:
    tool: str
    status: AgentStatus
    detail: str
    latency_ms: float
    headline: str = ""
    artifact: dict[str, object] = field(default_factory=dict)
    severity: SeverityResponse | None = None
    runbook: RunbookResponse | None = None
    log_analysis: LogAnalysisResult | None = None


def execute_tool(name: str, request: IncidentRequest) -> ToolResult:
    """Run one local agent function chosen by the planner."""
    started = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000.0

    if name == TOOL_ANALYZE_SEVERITY:
        response = analyze_severity(request)
        if response.status != AgentStatus.OK:
            return ToolResult(
                tool=name,
                status=response.status,
                headline=TOOL_HEADLINES[name],
                detail=response.error_message or "Severity agent failed",
                latency_ms=elapsed(),
                severity=response,
            )
        top_evidence = [
            f"{item.service}: {item.summary}"
            for item in response.evidence[:3]
            if item.summary
        ]
        detail = response.rationale or (
            f"{response.level.value} flag · {response.score}/100."
        )
        if top_evidence:
            detail += " Top signals: " + "; ".join(top_evidence)
        return ToolResult(
            tool=name,
            status=response.status,
            headline=TOOL_HEADLINES[name],
            detail=detail,
            latency_ms=elapsed(),
            severity=response,
            artifact={
                "kind": "severity",
                "level": response.level.value,
                "score": response.score,
                "rationale": response.rationale,
                "evidence": top_evidence,
            },
        )

    if name == TOOL_RECOMMEND_RUNBOOK:
        response = recommend_actions(request)
        if response.status != AgentStatus.OK:
            return ToolResult(
                tool=name,
                status=response.status,
                headline=TOOL_HEADLINES[name],
                detail=response.error_message or "Runbook agent failed",
                latency_ms=elapsed(),
                runbook=response,
            )
        top = response.recommendations[0] if response.recommendations else None
        if top is None:
            detail = "No runbook matched this incident signature."
            artifact: dict[str, object] = {"kind": "runbook", "matched": False}
        else:
            actions = [step.action for step in top.steps[:3]]
            detail = (
                f"Primary: {top.title} "
                f"({round(top.confidence * 100)}% confidence). "
                f"Next actions: " + ("; ".join(actions) if actions else "see runbook")
            )
            artifact = {
                "kind": "runbook",
                "matched": True,
                "title": top.title,
                "confidence": top.confidence,
                "actions": actions,
                "matched_terms": list(top.matched_terms[:5]),
            }
        return ToolResult(
            tool=name,
            status=response.status,
            headline=TOOL_HEADLINES[name],
            detail=detail,
            latency_ms=elapsed(),
            runbook=response,
            artifact=artifact,
        )

    if name == TOOL_ANALYZE_LOGS:
        response = analyze_logs(request)
        if response.status != AgentStatus.OK:
            return ToolResult(
                tool=name,
                status=response.status,
                headline=TOOL_HEADLINES[name],
                detail=response.error_message or "Log analysis failed",
                latency_ms=elapsed(),
                log_analysis=response,
            )
        cause = response.likely_cause or "cause unclear"
        summary = (response.summary or "").strip()
        detail = f"Likely cause: {cause}."
        if summary:
            detail += f" {summary[:220]}"
        return ToolResult(
            tool=name,
            status=response.status,
            headline=TOOL_HEADLINES[name],
            detail=detail,
            latency_ms=elapsed(),
            log_analysis=response,
            artifact={
                "kind": "logs",
                "likely_cause": cause,
                "summary": summary[:280],
            },
        )

    if name == TOOL_FINISH:
        return ToolResult(
            tool=name,
            status=AgentStatus.OK,
            headline=TOOL_HEADLINES[name],
            detail="Coordinator closed the loop — package findings for the on-call engineer.",
            latency_ms=elapsed(),
        )

    return ToolResult(
        tool=name,
        status=AgentStatus.INVALID_ARGUMENT,
        headline="Unknown tool",
        detail=f"Rejected unknown tool {name!r}",
        latency_ms=elapsed(),
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
