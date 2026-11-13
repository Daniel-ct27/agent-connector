"""Agentic observe → decide → act loop over local incident tools."""

from __future__ import annotations

from collections.abc import Callable

from agent_connector.agentic.observe import observe_incident
from agent_connector.agentic.providers import PlannerContext, PlannerProvider, build_planner
from agent_connector.agentic.tools import (
    TOOL_FINISH,
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
)

StepHook = Callable[[AgenticStep], None]


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

    record(
        AgenticStep(
            round=0,
            phase="observe",
            observation=observation,
            decision="observe incident logs",
            tool="observe",
            status=AgentStatus.OK,
            detail="built compact log observation for planner",
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

        record(
            AgenticStep(
                round=round_index,
                phase="decide",
                observation=observation,
                decision=decision.reason or "planner selected tools",
                tool="plan",
                status=(
                    AgentStatus.PARTIAL if decision.degraded else AgentStatus.OK
                ),
                detail=", ".join(decision.tools)
                + (
                    f" | {decision.error}"
                    if decision.error
                    else ""
                ),
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
                    status=(
                        AgentStatus.PARTIAL if decision.degraded else AgentStatus.OK
                    ),
                    detail=(
                        decision.error or "planner requested finish"
                        if decision.degraded
                        else "planner requested finish"
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
                        status=AgentStatus.PARTIAL,
                        detail="skipped; tool already called this run",
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
                    status=result.status,
                    detail=result.detail,
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
                    status=AgentStatus.OK,
                    detail="planner requested finish after tool calls",
                )
            )
            finished = True
            break

        if not acted:
            # Weak planners sometimes re-propose already-used tools. Treat that
            # as an implicit finish when we already have outcomes; otherwise
            # mark degraded so the UI can surface the stall.
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
                    status=(
                        AgentStatus.OK if implicit_ok else AgentStatus.PARTIAL
                    ),
                    detail=(
                        "finished after already-called tool proposals"
                        if implicit_ok
                        else "stopped after repeated already-called tools"
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
                status=AgentStatus.PARTIAL,
                detail="forced finish after max_rounds",
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
