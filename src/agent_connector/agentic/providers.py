"""LLM-agnostic planner providers (deterministic, OpenAI-compatible, CF, HTTP)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import Protocol

import httpx

from agent_connector.agentic.observe import has_error_like_logs
from agent_connector.agentic.schema import (
    PlanDecision,
    parse_plan_json,
    plan_system_prompt,
    plan_user_payload,
)
from agent_connector.agentic.tools import (
    TOOL_ANALYZE_LOGS,
    TOOL_ANALYZE_SEVERITY,
    TOOL_FINISH,
    TOOL_RECOMMEND_RUNBOOK,
)
from agent_connector.analyzers.base import AnalyzerConfigError
from agent_connector.config import (
    CLOUDFLARE_ACCOUNT_ID_ENV_VAR,
    CLOUDFLARE_API_TOKEN_ENV_VAR,
    DEFAULT_CLOUDFLARE_MODEL,
    DEFAULT_OPENAI_COMPAT_MODEL,
    DEFAULT_PLANNER,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_TEMPERATURE,
    OPENAI_API_KEY_ENV_VARS,
    OPENAI_BASE_URL_ENV_VAR,
    PLANNER_ENV_VAR,
    PLANNER_HTTP_TOKEN_ENV_VAR,
    PLANNER_HTTP_URL_ENV_VAR,
    PLANNER_MODEL_ENV_VAR,
    PLANNER_TIMEOUT_ENV_VAR,
    PLANNER_TIMEOUT_SECONDS,
)
from agent_connector.domain.models import IncidentRequest

_LOG = logging.getLogger(__name__)

_PLANNER_TRANSPORT_ERRORS = (
    httpx.HTTPError,
    TimeoutError,
    OSError,
    json.JSONDecodeError,
    ValueError,
    KeyError,
    IndexError,
    TypeError,
)


def _fallback_decision(
    request: IncidentRequest,
    context: PlannerContext,
    *,
    provider: str,
    error: Exception,
) -> PlanDecision:
    fallback = DeterministicPlanner().decide(request, context)
    message = f"{provider} planner failed ({type(error).__name__}); using deterministic fallback"
    return PlanDecision(
        tools=fallback.tools,
        reason=f"{message}: {fallback.reason}",
        degraded=True,
        error=message,
    )


@dataclass
class PlannerContext:
    observation: str
    called_tools: set[str] = field(default_factory=set)
    tool_notes: list[str] = field(default_factory=list)
    round_index: int = 1


class PlannerProvider(Protocol):
    @property
    def name(self) -> str: ...

    def decide(self, request: IncidentRequest, context: PlannerContext) -> PlanDecision: ...


class DeterministicPlanner:
    """Rule-based planner so demos/tests work without a live model."""

    @property
    def name(self) -> str:
        return "deterministic"

    def decide(self, request: IncidentRequest, context: PlannerContext) -> PlanDecision:
        remaining: list[str] = []
        if TOOL_ANALYZE_LOGS not in context.called_tools and has_error_like_logs(request):
            remaining.append(TOOL_ANALYZE_LOGS)
        if TOOL_ANALYZE_SEVERITY not in context.called_tools and request.logs:
            if TOOL_ANALYZE_LOGS in context.called_tools or not has_error_like_logs(
                request
            ):
                remaining.append(TOOL_ANALYZE_SEVERITY)
        if TOOL_RECOMMEND_RUNBOOK not in context.called_tools and (
            TOOL_ANALYZE_LOGS in context.called_tools or bool(request.scenario)
        ):
            remaining.append(TOOL_RECOMMEND_RUNBOOK)

        if not remaining:
            return PlanDecision(
                tools=(TOOL_FINISH,),
                reason="all useful tools already called",
            )
        if (
            context.round_index == 1
            and TOOL_ANALYZE_LOGS in remaining
            and TOOL_ANALYZE_LOGS not in context.called_tools
        ):
            return PlanDecision(
                tools=(TOOL_ANALYZE_LOGS,),
                reason="ERROR/FATAL evidence present; inspect logs first",
            )
        return PlanDecision(
            tools=tuple(remaining),
            reason="gather remaining severity and runbook evidence",
        )


class OpenAICompatiblePlanner:
    """Any OpenAI-compatible Chat Completions endpoint (OpenAI, Groq, Ollama, …)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float,
        base_url: str | None = None,
        client: object | None = None,
    ) -> None:
        if not api_key.strip():
            raise AnalyzerConfigError("openai-compatible planner requires an API key")
        self._model = model
        self._client = (
            client
            if client is not None
            else _build_openai_client(api_key, timeout_s, base_url)
        )

    @property
    def name(self) -> str:
        return "openai"

    def decide(self, request: IncidentRequest, context: PlannerContext) -> PlanDecision:
        payload = plan_user_payload(
            observation=context.observation,
            called_tools=sorted(context.called_tools),
            tool_notes=context.tool_notes,
            round_index=context.round_index,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": plan_system_prompt()},
                    {
                        "role": "user",
                        "content": json.dumps(payload, separators=(",", ":")),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            return parse_plan_json(content)
        except _PLANNER_TRANSPORT_ERRORS as error:
            _LOG.exception("OpenAI-compatible planner failed for %s", request.incident_id)
            return _fallback_decision(
                request,
                context,
                provider="openai",
                error=error,
            )


class CloudflareWorkersAIPlanner:
    """Cloudflare Workers AI REST adapter (free Neuron allowance friendly)."""

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model: str,
        timeout_s: float,
        transport: httpx.Client | None = None,
    ) -> None:
        if not account_id.strip() or not api_token.strip():
            raise AnalyzerConfigError(
                "cloudflare planner requires CLOUDFLARE_ACCOUNT_ID and "
                "CLOUDFLARE_API_TOKEN"
            )
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        )
        self._token = api_token
        self._timeout_s = timeout_s
        self._client = transport

    @property
    def name(self) -> str:
        return "cloudflare"

    def decide(self, request: IncidentRequest, context: PlannerContext) -> PlanDecision:
        payload = plan_user_payload(
            observation=context.observation,
            called_tools=sorted(context.called_tools),
            tool_notes=context.tool_notes,
            round_index=context.round_index,
        )
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        plan_system_prompt()
                        + " Return raw JSON only with no markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, separators=(",", ":")),
                },
            ]
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=body,
                    timeout=self._timeout_s,
                )
            else:
                with httpx.Client(timeout=self._timeout_s) as client:
                    response = client.post(
                        self._url,
                        headers={"Authorization": f"Bearer {self._token}"},
                        json=body,
                    )
            response.raise_for_status()
            data = response.json()
            content = _cloudflare_content(data)
            return parse_plan_json(content)
        except _PLANNER_TRANSPORT_ERRORS as error:
            _LOG.exception("Cloudflare planner failed for %s", request.incident_id)
            return _fallback_decision(
                request,
                context,
                provider="cloudflare",
                error=error,
            )


class HttpJsonPlanner:
    """Generic HTTP planner: POST JSON, expect {tools, reason}."""

    def __init__(
        self,
        *,
        url: str,
        token: str = "",
        timeout_s: float = PLANNER_TIMEOUT_SECONDS,
        transport: httpx.Client | None = None,
    ) -> None:
        if not url.strip():
            raise AnalyzerConfigError(
                "http planner requires AGENT_CONNECTOR_PLANNER_URL"
            )
        self._url = url
        self._token = token
        self._timeout_s = timeout_s
        self._client = transport

    @property
    def name(self) -> str:
        return "http"

    def decide(self, request: IncidentRequest, context: PlannerContext) -> PlanDecision:
        payload = {
            "system": plan_system_prompt(),
            **plan_user_payload(
                observation=context.observation,
                called_tools=sorted(context.called_tools),
                tool_notes=context.tool_notes,
                round_index=context.round_index,
            ),
        }
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            if self._client is not None:
                response = self._client.post(
                    self._url,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_s,
                )
            else:
                with httpx.Client(timeout=self._timeout_s) as client:
                    response = client.post(self._url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and "tools" in data:
                return parse_plan_json(json.dumps(data))
            if isinstance(data, dict):
                return parse_plan_json(json.dumps(data.get("result", data)))
            return PlanDecision(
                tools=(TOOL_FINISH,),
                reason="planner returned a non-object JSON value",
                degraded=True,
                error="planner returned a non-object JSON value",
            )
        except _PLANNER_TRANSPORT_ERRORS as error:
            _LOG.exception("HTTP planner failed for %s", request.incident_id)
            return _fallback_decision(
                request,
                context,
                provider="http",
                error=error,
            )


def build_planner(name: str | None = None) -> PlannerProvider:
    """Select a planner from ``name`` or ``AGENT_CONNECTOR_PLANNER``."""
    selected = (name or os.getenv(PLANNER_ENV_VAR, DEFAULT_PLANNER)).strip().lower()
    timeout_s = _resolve_timeout()
    model = os.getenv(PLANNER_MODEL_ENV_VAR, "").strip()

    if selected in ("", "deterministic", "rules"):
        return DeterministicPlanner()
    if selected in ("openai", "openai-compatible"):
        return OpenAICompatiblePlanner(
            api_key=_resolve_openai_api_key(),
            model=model or DEFAULT_OPENAI_COMPAT_MODEL,
            timeout_s=timeout_s,
            base_url=os.getenv(OPENAI_BASE_URL_ENV_VAR) or None,
        )
    if selected in ("cloudflare", "cf", "workers-ai"):
        return CloudflareWorkersAIPlanner(
            account_id=os.getenv(CLOUDFLARE_ACCOUNT_ID_ENV_VAR, ""),
            api_token=os.getenv(CLOUDFLARE_API_TOKEN_ENV_VAR, ""),
            model=model or DEFAULT_CLOUDFLARE_MODEL,
            timeout_s=timeout_s,
        )
    if selected in ("http", "custom"):
        return HttpJsonPlanner(
            url=os.getenv(PLANNER_HTTP_URL_ENV_VAR, ""),
            token=os.getenv(PLANNER_HTTP_TOKEN_ENV_VAR, ""),
            timeout_s=timeout_s,
        )
    raise AnalyzerConfigError(
        f"unknown planner {selected!r}; expected deterministic|openai|cloudflare|http"
    )


def _resolve_timeout() -> float:
    raw = os.getenv(PLANNER_TIMEOUT_ENV_VAR)
    if raw is None or not raw.strip():
        return PLANNER_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as error:
        raise AnalyzerConfigError(
            f"{PLANNER_TIMEOUT_ENV_VAR} must be a positive number, got {raw!r}"
        ) from error
    if value <= 0:
        raise AnalyzerConfigError(
            f"{PLANNER_TIMEOUT_ENV_VAR} must be greater than 0, got {raw!r}"
        )
    return value


def _resolve_openai_api_key() -> str:
    for env_name in OPENAI_API_KEY_ENV_VARS:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    raise AnalyzerConfigError(
        "openai planner requires OPENAI_API_KEY or AGENT_CONNECTOR_OPENAI_API_KEY"
    )


def _build_openai_client(api_key: str, timeout_s: float, base_url: str | None) -> object:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise AnalyzerConfigError(
            "openai package is not installed; run: pip install -e \".[llm]\""
        ) from error
    kwargs: dict = {"api_key": api_key, "timeout": timeout_s}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _cloudflare_content(data: object) -> str:
    if not isinstance(data, dict):
        return str(data)
    result = data.get("result", data)
    if isinstance(result, dict):
        response = result.get("response")
        if isinstance(response, str):
            return response
        message = result.get("message") or result.get("content")
        if isinstance(message, str):
            return message
        if isinstance(message, list) and message:
            first = message[0]
            if isinstance(first, dict):
                return str(first.get("content", first))
            return str(first)
        return json.dumps(result)
    if isinstance(result, str):
        return result
    return json.dumps(result)
