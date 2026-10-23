"""Select an analyzer implementation from configuration."""

from __future__ import annotations

import os

from agent_connector.analyzers.base import Analyzer, AnalyzerConfigError
from agent_connector.analyzers.deterministic import DeterministicAnalyzer
from agent_connector.config import (
    ANALYZER_ENV_VAR,
    DEFAULT_ANALYZER,
    LLM_MODEL,
    LLM_MODEL_ENV_VAR,
    LLM_TIMEOUT_ENV_VAR,
    LLM_TIMEOUT_SECONDS,
    OPENAI_API_KEY_ENV_VARS,
)


def build_analyzer(name: str | None = None) -> Analyzer:
    """Return the analyzer selected by ``name`` or ``AGENT_CONNECTOR_ANALYZER``."""
    selected = (name or os.getenv(ANALYZER_ENV_VAR, DEFAULT_ANALYZER)).strip().lower()
    if selected in ("", "deterministic", "stub"):
        return DeterministicAnalyzer()
    if selected in ("openai", "live"):
        from agent_connector.analyzers.openai_provider import OpenAIAnalyzer

        try:
            return OpenAIAnalyzer(
                api_key=_resolve_openai_api_key(),
                model=os.getenv(LLM_MODEL_ENV_VAR, LLM_MODEL),
                timeout_s=_resolve_timeout(),
            )
        except AnalyzerConfigError:
            raise
        except Exception as error:
            raise AnalyzerConfigError(str(error)) from error
    raise AnalyzerConfigError(
        f"unknown analyzer {selected!r}; expected 'deterministic' or 'openai'"
    )


def _resolve_openai_api_key() -> str:
    for env_name in OPENAI_API_KEY_ENV_VARS:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    raise AnalyzerConfigError(
        "openai analyzer requires OPENAI_API_KEY or AGENT_CONNECTOR_OPENAI_API_KEY"
    )


def _resolve_timeout() -> float:
    raw = os.getenv(LLM_TIMEOUT_ENV_VAR)
    if raw is None or not raw.strip():
        return LLM_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError as error:
        raise AnalyzerConfigError(
            f"{LLM_TIMEOUT_ENV_VAR} must be a positive number, got {raw!r}"
        ) from error
    if timeout <= 0:
        raise AnalyzerConfigError(
            f"{LLM_TIMEOUT_ENV_VAR} must be greater than 0, got {raw!r}"
        )
    return timeout
