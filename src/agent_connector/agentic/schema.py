"""Provider-agnostic plan JSON schema shared by all LLM adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json

from agent_connector.agentic.tools import TOOL_FINISH, TOOL_NAMES


@dataclass(frozen=True)
class PlanDecision:
    tools: tuple[str, ...]
    reason: str = ""
    degraded: bool = False
    error: str = ""
    rejected_tools: tuple[str, ...] = ()


_PLAN_PROMPT = (
    "You are an incident-response coordinator. Given an observation of service "
    "logs and tools already used, choose zero or more next tools. Reply with "
    "ONLY a JSON object of the form "
    '{"tools":["analyze_logs"],"reason":"short reason"}. '
    "Allowed tools: analyze_logs, analyze_severity, recommend_runbook, finish. "
    "Prefer analyze_logs first when ERROR/FATAL lines exist. Call finish when "
    "enough evidence is collected. Do not invent tool names."
)


def plan_system_prompt() -> str:
    return _PLAN_PROMPT


def plan_user_payload(
    *,
    observation: str,
    called_tools: list[str],
    tool_notes: list[str],
    round_index: int,
) -> dict:
    return {
        "observation": observation,
        "already_called": called_tools,
        "tool_notes": tool_notes[-8:],
        "round": round_index,
        "allowed_tools": list(TOOL_NAMES),
    }


def _extract_json_object(text: str) -> str | None:
    """Extract the first top-level JSON object, respecting strings/escapes."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_plan_json(raw: str) -> PlanDecision:
    """Parse a model response into a PlanDecision.

    Invalid JSON or unknown tool names are marked ``degraded`` so callers do
    not treat them as a clean planner success.
    """
    text = (raw or "").strip()
    if not text:
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason="empty planner response",
            degraded=True,
            error="empty planner response",
        )

    candidate = _extract_json_object(text) or text
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason="unparseable planner response",
            degraded=True,
            error="planner response was not valid JSON",
        )

    if not isinstance(data, dict):
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason="planner returned a non-object JSON value",
            degraded=True,
            error="planner returned a non-object JSON value",
        )

    tools_raw = data.get("tools", [])
    if isinstance(tools_raw, str):
        tools_raw = [tools_raw]
    if not isinstance(tools_raw, list):
        tools_raw = []

    tools: list[str] = []
    rejected: list[str] = []
    for item in tools_raw:
        name = str(item).strip()
        if not name:
            continue
        if name in TOOL_NAMES:
            if name not in tools:
                tools.append(name)
        elif name not in rejected:
            rejected.append(name)

    reason = str(data.get("reason", "") or "").strip()
    if rejected and not tools:
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason=reason or "no valid tools selected",
            degraded=True,
            error=f"rejected unknown tools: {', '.join(rejected)}",
            rejected_tools=tuple(rejected),
        )
    if rejected and tools:
        suffix = f" (ignored unknown tools: {', '.join(rejected)})"
        reason = (reason + suffix).strip() if reason else suffix.strip()
        return PlanDecision(
            tools=tuple(tools),
            reason=reason,
            degraded=True,
            error=f"ignored unknown tools: {', '.join(rejected)}",
            rejected_tools=tuple(rejected),
        )
    if not tools:
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason=reason or "no tools selected",
            degraded=True,
            error="planner selected no tools",
        )
    return PlanDecision(tools=tuple(tools), reason=reason)
