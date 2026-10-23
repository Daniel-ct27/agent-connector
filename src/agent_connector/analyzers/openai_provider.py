"""Live OpenAI Chat Completions analyzer for Log Analysis demos."""

from __future__ import annotations

import json
import logging

from agent_connector.analyzers.base import AnalyzerError, AnalyzerOutput
from agent_connector.config import LLM_MAX_OUTPUT_TOKENS, LLM_TEMPERATURE
from agent_connector.domain.models import EvidenceItem, IncidentRequest

_LOG = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an incident analyst. Given structured evidence from logs, "
    "respond with a compact JSON object containing exactly two string fields: "
    "summary and likely_cause. Do not invent services that are not present in "
    "the evidence. Keep both fields to one or two sentences."
)


class OpenAIAnalyzer:
    """One lightweight Chat Completions call after local preprocessing."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float,
        max_output_tokens: int = LLM_MAX_OUTPUT_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        client: object | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        self._model = model
        self._timeout_s = timeout_s
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._client = client if client is not None else _build_client(api_key, timeout_s)

    @property
    def name(self) -> str:
        return "openai"

    def summarize(
        self,
        request: IncidentRequest,
        evidence: list[EvidenceItem],
    ) -> AnalyzerOutput:
        payload = {
            "incident_id": request.incident_id,
            "scenario": request.scenario,
            "evidence": [
                {
                    "service": item.service,
                    "summary": item.summary,
                    "count": item.count,
                    "sample_message": item.sample_message,
                }
                for item in evidence
            ],
        }
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_output_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(payload, separators=(",", ":")),
                    },
                ],
            )
            content = response.choices[0].message.content or ""
            return _parse_output(content)
        except AnalyzerError:
            raise
        except Exception as error:
            _LOG.exception("OpenAI analyzer failed for %s", request.incident_id)
            raise AnalyzerError("live log analysis failed") from error


def _build_client(api_key: str, timeout_s: float) -> object:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise AnalyzerError(
            "openai package is not installed; run: pip install -e \".[llm]\""
        ) from error
    return OpenAI(api_key=api_key, timeout=timeout_s)


def _parse_output(content: str) -> AnalyzerOutput:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise AnalyzerError("live log analysis returned invalid JSON") from error
    summary = str(data.get("summary", "")).strip()
    likely_cause = str(data.get("likely_cause", "")).strip()
    if not summary or not likely_cause:
        raise AnalyzerError("live log analysis returned incomplete fields")
    return AnalyzerOutput(summary=summary, likely_cause=likely_cause)
