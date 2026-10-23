"""Shared analyzer contract for Log Analysis summarization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_connector.domain.models import EvidenceItem, IncidentRequest


@dataclass(frozen=True)
class AnalyzerOutput:
    """Final summary fields produced after local evidence extraction."""

    summary: str
    likely_cause: str


class AnalyzerError(RuntimeError):
    """Raised when a live analyzer cannot produce a usable summary."""


class AnalyzerConfigError(ValueError):
    """Raised when analyzer selection or live-provider configuration is invalid."""


class Analyzer(Protocol):
    """Summarize an incident after deterministic preprocessing."""

    @property
    def name(self) -> str:
        """Stable selector name (for logs and configuration)."""

    def summarize(
        self,
        request: IncidentRequest,
        evidence: list[EvidenceItem],
    ) -> AnalyzerOutput:
        """Return summary and likely cause for the prepared evidence."""
