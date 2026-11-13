"""Agentic observe → decide → act loop over local incident tools."""

from __future__ import annotations

from collections.abc import Callable

from agent_connector.agentic.observe import observe_incident
from agent_connector.agentic.providers import PlannerContext, PlannerProvider, build_planner
from agent_connector.agentic.tools import (
    TOOL_FINISH,
    TOOL_HEADLINES,
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

    def record(step: AgenticStep) -> None:
        steps.append(step)
        if on_step is not None:
            on_step(step)

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
                f"{len(services)} service(s); {error_like} ERROR/FATAL events. "
                f"Incident {request.incident_id}."
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
            decide_detail = (
                f"Queue: {', '.join(tool_labels)}. {decide_detail}"
            )
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
            record(
                AgenticStep(
                    round=round_index,
                    phase="finish",
                    observation=observation,
                    decision=decision.reason or "finish",
                    tool=TOOL_FINISH,
                    headline=TOOL_HEADLINES[TOOL_FINISH],
                    status=(
                        AgentStatus.PARTIAL if decision.degraded else AgentStatus.OK
                    ),
                    detail=_finish_detail(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                        degraded=decision.degraded,
                        error=decision.error,
                    ),
                    artifact=_finish_artifact(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                    ),
                )
            )
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

            result = execute_tool(tool_name, request)
            acted = True
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
            record(
                AgenticStep(
                    round=round_index,
                    phase="act",
                    observation=observation,
                    decision=decision.reason,
                    tool=tool_name,
                    headline=result.headline or TOOL_HEADLINES.get(tool_name, tool_name),
                    status=result.status,
                    detail=result.detail,
                    artifact=result.artifact,
                    latency_ms=result.latency_ms,
                )
            )

        if TOOL_FINISH in tools:
            record(
                AgenticStep(
                    round=round_index,
                    phase="finish",
                    observation=observation,
                    decision=decision.reason or "finish",
                    tool=TOOL_FINISH,
                    headline=TOOL_HEADLINES[TOOL_FINISH],
                    status=AgentStatus.OK,
                    detail=_finish_detail(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                    ),
                    artifact=_finish_artifact(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                    ),
                )
            )
            finished = True
            break

        if not acted:
            implicit_ok = bool(outcomes)
            if not implicit_ok:
                planner_degraded = True
                planner_errors.append("planner repeated already-called tools")
            record(
                AgenticStep(
                    round=round_index,
                    phase="finish",
                    observation=observation,
                    decision="no new tools selected",
                    tool=TOOL_FINISH,
                    headline=TOOL_HEADLINES[TOOL_FINISH],
                    status=(
                        AgentStatus.OK if implicit_ok else AgentStatus.PARTIAL
                    ),
                    detail=_finish_detail(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                        note=(
                            "No unused tools remained."
                            if implicit_ok
                            else "Coordinator stalled on already-used tools."
                        ),
                    ),
                    artifact=_finish_artifact(
                        severity=severity,
                        runbook=runbook,
                        log_analysis=log_analysis,
                    ),
                )
            )
            finished = True
            if not implicit_ok:
                forced_finish = True
            break

    if not finished:
        forced_finish = True
        planner_degraded = True
        planner_errors.append("forced finish after max_rounds")
        record(
            AgenticStep(
                round=max_rounds + 1,
                phase="finish",
                observation=observation,
                decision="max rounds reached",
                tool=TOOL_FINISH,
                headline=TOOL_HEADLINES[TOOL_FINISH],
                status=AgentStatus.PARTIAL,
                detail=_finish_detail(
                    severity=severity,
                    runbook=runbook,
                    log_analysis=log_analysis,
                    note="Stopped at max coordinator rounds.",
                ),
                artifact=_finish_artifact(
                    severity=severity,
                    runbook=runbook,
                    log_analysis=log_analysis,
                ),
            )
        )

    ordered_outcomes = list(outcomes.values())
    partial = (
        forced_finish
        or planner_degraded
        or (not ordered_outcomes)
        or any(item.status != AgentStatus.OK for item in ordered_outcomes)
    )
    mode = active.name
    if planner_degraded and active.name != "deterministic":
        mode = f"{active.name}+fallback"

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
        parts.append(
            f"Cause: {log_analysis.likely_cause or 'unknown'}"
        )
    if severity is not None:
        parts.append(
            f"Severity {severity.level.value} (score {severity.score})"
        )
    if runbook is not None and runbook.recommendations:
        top = runbook.recommendations[0]
        parts.append(
            f"Runbook: {top.title} ({round(top.confidence * 100)}%)"
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
            "actions": [step.action for step in top.steps[:3]],
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
