"""Agentic observe → decide → act loop over local incident tools."""

from __future__ import annotations

from collections.abc import Callable

from agent_connector.agentic.observe import observe_incident
from agent_connector.agentic.providers import PlannerContext, PlannerProvider, build_planner
from agent_connector.agentic.tools import (
    TOOL_ANALYZE_LOGS,
    TOOL_ANALYZE_SEVERITY,
    TOOL_FINISH,
    TOOL_HEADLINES,
    TOOL_RECOMMEND_RUNBOOK,
    ToolResult,
    execute_tool,
    outcome_from_result,
)
from agent_connector.config import PLANNER_MAX_ROUNDS
from agent_connector.domain.models import (
    AgentOutcome,
    AgentStatus,
    AgenticStep,
    IncidentReport,
    IncidentRequest,
    LogLevel,
)

StepHook = Callable[[AgenticStep], None]

_TOOL_LABELS = {
    "analyze_logs": "log forensics",
    "analyze_severity": "severity scoring",
    "recommend_runbook": "runbook match",
    "finish": "handoff",
}

# Always ship a full engineer helpdesk package, even if the planner under-calls.
_DESK_TOOLS = (
    TOOL_ANALYZE_LOGS,
    TOOL_ANALYZE_SEVERITY,
    TOOL_RECOMMEND_RUNBOOK,
)


def run_agentic(
    request: IncidentRequest,
    *,
    planner: PlannerProvider | str | None = None,
    max_rounds: int = PLANNER_MAX_ROUNDS,
    on_step: StepHook | None = None,
) -> IncidentReport:
    """Let a planner inspect logs and choose which agent tools to call."""
    if planner is None or isinstance(planner, str):
        active: PlannerProvider = build_planner(planner)
    else:
        active = planner

    observation = observe_incident(request)
    context = PlannerContext(observation=observation)
    steps: list[AgenticStep] = []
    outcomes: dict[str, AgentOutcome] = {}
    severity = None
    runbook = None
    log_analysis = None
    planner_degraded = False
    planner_errors: list[str] = []
    forced_finish = False
    desk_completed = False

    def record(step: AgenticStep) -> None:
        steps.append(step)
        if on_step is not None:
            on_step(step)

    def dispatch(tool_name: str, *, round_index: int, reason: str, desk_fill: bool = False):
        nonlocal severity, runbook, log_analysis
        result = execute_tool(tool_name, request)
        context.called_tools.add(tool_name)
        context.tool_notes.append(f"{tool_name}: {result.detail}")
        severity, runbook, log_analysis = _merge_result(
            result,
            severity=severity,
            runbook=runbook,
            log_analysis=log_analysis,
        )
        outcome = outcome_from_result(result)
        if outcome is not None:
            outcomes[outcome.name] = outcome
        headline = result.headline or TOOL_HEADLINES.get(tool_name, tool_name)
        if desk_fill:
            headline = f"{headline} · desk completion"
        record(
            AgenticStep(
                round=round_index,
                phase="act",
                observation=observation,
                decision=reason,
                tool=tool_name,
                headline=headline,
                status=result.status,
                detail=result.detail,
                artifact=result.artifact,
                latency_ms=result.latency_ms,
            )
        )
        return result

    def complete_helpdesk(*, round_index: int, note: str = "") -> None:
        """Guarantee logs + severity + runbook before handoff."""
        nonlocal desk_completed
        missing = [tool for tool in _DESK_TOOLS if tool not in context.called_tools]
        if missing:
            record(
                AgenticStep(
                    round=round_index,
                    phase="decide",
                    observation=observation,
                    decision="complete engineer helpdesk package",
                    tool="plan",
                    headline="Helpdesk completion",
                    status=AgentStatus.OK,
                    detail=(
                        "Coordinator under-dispatched. Completing the engineer package: "
                        + ", ".join(_TOOL_LABELS.get(tool, tool) for tool in missing)
                        + "."
                    ),
                    artifact={
                        "kind": "plan",
                        "tools": missing,
                        "reason": "helpdesk completion",
                        "degraded": False,
                    },
                )
            )
            for tool_name in missing:
                dispatch(
                    tool_name,
                    round_index=round_index,
                    reason="helpdesk completion",
                    desk_fill=True,
                )
            desk_completed = True

        record(
            AgenticStep(
                round=round_index,
                phase="finish",
                observation=observation,
                decision="engineer handoff",
                tool=TOOL_FINISH,
                headline="Engineer handoff",
                status=AgentStatus.OK,
                detail=_finish_detail(
                    severity=severity,
                    runbook=runbook,
                    log_analysis=log_analysis,
                    note=note or "Helpdesk package ready for the on-call engineer.",
                ),
                artifact=_finish_artifact(
                    severity=severity,
                    runbook=runbook,
                    log_analysis=log_analysis,
                ),
            )
        )

    services = sorted({entry.service for entry in request.logs if entry.service})
    error_like = sum(
        1
        for entry in request.logs
        if entry.level in {LogLevel.ERROR, LogLevel.FATAL}
    )
    record(
        AgenticStep(
            round=0,
            phase="observe",
            observation=observation,
            decision="ingest live incident signals",
            tool="observe",
            headline=TOOL_HEADLINES["observe"],
            status=AgentStatus.OK,
            detail=(
                f"Ingested {len(request.logs)} log lines across "
                f"{len(services)} service(s); {error_like} ERROR/FATAL events."
            ),
            artifact={
                "kind": "observe",
                "incident_id": request.incident_id,
                "scenario": request.scenario,
                "log_count": len(request.logs),
                "service_count": len(services),
                "error_like_count": error_like,
                "services": services[:8],
            },
        )
    )

    finished = False
    for round_index in range(1, max_rounds + 1):
        context.round_index = round_index
        decision = active.decide(request, context)
        if decision.degraded:
            planner_degraded = True
            if decision.error:
                planner_errors.append(decision.error)

        tool_labels = [
            _TOOL_LABELS.get(name, name) for name in decision.tools if name
        ]
        decide_detail = decision.reason or "Coordinator selected next actions."
        if tool_labels:
            decide_detail = f"Queue: {', '.join(tool_labels)}. {decide_detail}"
        if decision.error:
            decide_detail = f"{decide_detail} ({decision.error})"

        record(
            AgenticStep(
                round=round_index,
                phase="decide",
                observation=observation,
                decision=decision.reason or "planner selected tools",
                tool="plan",
                headline=TOOL_HEADLINES["plan"],
                status=(
                    AgentStatus.PARTIAL if decision.degraded else AgentStatus.OK
                ),
                detail=decide_detail,
                artifact={
                    "kind": "plan",
                    "tools": list(decision.tools),
                    "reason": decision.reason,
                    "degraded": decision.degraded,
                },
            )
        )

        tools = [name for name in decision.tools if name]
        if not tools or (TOOL_FINISH in tools and len(tools) == 1):
            complete_helpdesk(round_index=round_index)
            finished = True
            break

        acted = False
        for tool_name in tools:
            if tool_name == TOOL_FINISH:
                continue
            if tool_name in context.called_tools:
                record(
                    AgenticStep(
                        round=round_index,
                        phase="act",
                        observation=observation,
                        decision=decision.reason,
                        tool=tool_name,
                        headline=TOOL_HEADLINES.get(tool_name, tool_name),
                        status=AgentStatus.PARTIAL,
                        detail=(
                            f"{_TOOL_LABELS.get(tool_name, tool_name).title()} "
                            "already completed earlier in this response — skipping."
                        ),
                    )
                )
                continue

            dispatch(
                tool_name,
                round_index=round_index,
                reason=decision.reason or "planner selected tools",
            )
            acted = True

        if TOOL_FINISH in tools:
            complete_helpdesk(round_index=round_index)
            finished = True
            break

        if not acted:
            if not outcomes:
                planner_degraded = True
                planner_errors.append("planner repeated already-called tools")
                forced_finish = True
            complete_helpdesk(
                round_index=round_index,
                note=(
                    "Planner stalled; helpdesk completion filled the remaining package."
                    if outcomes
                    else "Planner stalled with no findings; helpdesk completion recovered the package."
                ),
            )
            finished = True
            break

    if not finished:
        forced_finish = True
        planner_degraded = True
        planner_errors.append("forced finish after max_rounds")
        complete_helpdesk(
            round_index=max_rounds + 1,
            note="Max rounds reached; helpdesk completion filled the remaining package.",
        )

    ordered_outcomes = list(outcomes.values())
    partial = (
        forced_finish
        or planner_degraded
        or (not ordered_outcomes)
        or any(item.status != AgentStatus.OK for item in ordered_outcomes)
    )
    # A completed desk package is useful even if the live planner under-called.
    if (
        desk_completed
        and severity is not None
        and runbook is not None
        and log_analysis is not None
        and all(item.status == AgentStatus.OK for item in ordered_outcomes)
    ):
        partial = planner_degraded or forced_finish

    mode = active.name
    if planner_degraded and active.name != "deterministic":
        mode = f"{active.name}+fallback"
    elif desk_completed and active.name != "deterministic":
        mode = f"{active.name}+desk"

    return IncidentReport(
        incident_id=request.incident_id,
        scenario=request.scenario,
        severity=severity,
        runbook=runbook,
        log_analysis=log_analysis,
        agent_outcomes=ordered_outcomes,
        partial=partial,
        agentic_mode=mode,
        agentic_steps=steps,
        planner_degraded=planner_degraded,
        planner_error="; ".join(dict.fromkeys(planner_errors)),
    )


def _finish_detail(
    *,
    severity,
    runbook,
    log_analysis,
    degraded: bool = False,
    error: str = "",
    note: str = "",
) -> str:
    parts: list[str] = []
    if note:
        parts.append(note)
    if log_analysis is not None:
        parts.append(f"Cause: {log_analysis.likely_cause or 'unknown'}")
    if severity is not None:
        parts.append(f"Severity {severity.level.value} (score {severity.score})")
    if runbook is not None and runbook.recommendations:
        top = runbook.recommendations[0]
        actions = "; ".join(step.action for step in top.steps[:3]) or "see runbook"
        parts.append(
            f"Recommended: {top.title} ({round(top.confidence * 100)}%) — {actions}"
        )
    elif runbook is not None:
        parts.append("No runbook match")
    if not parts:
        parts.append("No agent findings collected yet.")
    if degraded and error:
        parts.append(f"Degraded: {error}")
    return " · ".join(parts)


def _finish_artifact(*, severity, runbook, log_analysis) -> dict[str, object]:
    artifact: dict[str, object] = {"kind": "finish"}
    if severity is not None:
        artifact["severity"] = {
            "level": severity.level.value,
            "score": severity.score,
            "rationale": severity.rationale,
        }
    if runbook is not None and runbook.recommendations:
        top = runbook.recommendations[0]
        artifact["runbook"] = {
            "title": top.title,
            "confidence": top.confidence,
            "actions": [step.action for step in top.steps[:5]],
        }
    if log_analysis is not None:
        artifact["logs"] = {
            "likely_cause": log_analysis.likely_cause,
            "summary": (log_analysis.summary or "")[:280],
        }
    return artifact


def _merge_result(
    result: ToolResult,
    *,
    severity,
    runbook,
    log_analysis,
):
    if result.severity is not None:
        severity = result.severity
    if result.runbook is not None:
        runbook = result.runbook
    if result.log_analysis is not None:
        log_analysis = result.log_analysis
    return severity, runbook, log_analysis
