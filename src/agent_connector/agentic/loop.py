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
        record(
            AgenticStep(
                round=round_index,
                phase="decide",
                observation=observation,
                decision=decision.reason or "planner selected tools",
                tool="plan",
                status=AgentStatus.OK,
                detail=", ".join(decision.tools),
            )
        )

        tools = [name for name in decision.tools if name]
        if not tools or TOOL_FINISH in tools and len(tools) == 1:
            record(
                AgenticStep(
                    round=round_index,
                    phase="finish",
                    observation=observation,
                    decision=decision.reason or "finish",
                    tool=TOOL_FINISH,
                    status=AgentStatus.OK,
                    detail="planner requested finish",
                )
            )
            finished = True
            break

        for tool_name in tools:
            if tool_name == TOOL_FINISH:
                continue
            if tool_name in context.called_tools:
                continue
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

    if not finished:
        record(
            AgenticStep(
                round=max_rounds + 1,
                phase="finish",
                observation=observation,
                decision="max rounds reached",
                tool=TOOL_FINISH,
                status=AgentStatus.OK,
                detail="forced finish after max_rounds",
            )
        )

    ordered_outcomes = list(outcomes.values())
    partial = (not ordered_outcomes) or any(
        item.status != AgentStatus.OK for item in ordered_outcomes
    )
    if ordered_outcomes and all(item.status == AgentStatus.OK for item in ordered_outcomes):
        partial = False

    return IncidentReport(
        incident_id=request.incident_id,
        scenario=request.scenario,
        severity=severity,
        runbook=runbook,
        log_analysis=log_analysis,
        agent_outcomes=ordered_outcomes,
        partial=partial,
        agentic_mode=active.name,
        agentic_steps=steps,
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
