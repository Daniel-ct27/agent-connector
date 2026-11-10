"""Provider-agnostic plan JSON schema shared by all LLM adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from agent_connector.agentic.tools import TOOL_FINISH, TOOL_NAMES


@dataclass(frozen=True)
class PlanDecision:
    tools: tuple[str, ...]
    reason: str = ""


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


def parse_plan_json(raw: str) -> PlanDecision:
    """Parse a model response into a PlanDecision."""
    text = (raw or "").strip()
    if not text:
        return PlanDecision(tools=(TOOL_FINISH,), reason="empty planner response")

    candidate = text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start : end + 1]

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        lowered = text.lower()
        if "finish" in lowered:
            return PlanDecision(tools=(TOOL_FINISH,), reason=text[:200])
        return PlanDecision(
            tools=(TOOL_FINISH,),
            reason="unparseable planner response",
        )

    tools_raw = data.get("tools", [])
    if isinstance(tools_raw, str):
        tools_raw = [tools_raw]
    if not isinstance(tools_raw, list):
        tools_raw = []

    tools: list[str] = []
    for item in tools_raw:
        name = str(item).strip()
        if name in TOOL_NAMES and name not in tools:
            tools.append(name)

    reason = str(data.get("reason", "") or "").strip()
    if not tools:
        return PlanDecision(tools=(TOOL_FINISH,), reason=reason or "no tools selected")
    return PlanDecision(tools=tuple(tools), reason=reason)
