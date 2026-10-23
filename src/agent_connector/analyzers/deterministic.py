"""Deterministic summarizer used for tests, benchmarks, and default demos."""

from __future__ import annotations

from agent_connector.analyzers.base import AnalyzerOutput
from agent_connector.domain.models import EvidenceItem, IncidentRequest

# Stable outputs used only by the three protocol-comparison fixtures.
_FIXTURE_SUMMARIES = {
    "db_connection_failure": (
        "Repeated database connection timeouts and connection saturation on orders-db.",
        "database connection failure on orders-db",
    ),
    "retry_storm": (
        "Payment retries amplified load until card-gateway rate limiting and checkout failures.",
        "retry storm against payment / rate limit",
    ),
    "expired_certificate": (
        "TLS handshakes failing because the auth-service certificate is expired.",
        "expired TLS certificate on auth-service",
    ),
}


class DeterministicAnalyzer:
    """Fixture-aware deterministic substitute for a live model call."""

    @property
    def name(self) -> str:
        return "deterministic"

    def summarize(
        self,
        request: IncidentRequest,
        evidence: list[EvidenceItem],
    ) -> AnalyzerOutput:
        if request.scenario in _FIXTURE_SUMMARIES:
            summary, likely_cause = _FIXTURE_SUMMARIES[request.scenario]
            return AnalyzerOutput(summary=summary, likely_cause=likely_cause)

        if not evidence:
            return AnalyzerOutput(
                summary="No error-like evidence found in the provided logs.",
                likely_cause="insufficient evidence",
            )

        top = evidence[0]
        summary = (
            f"Dominant signal from {top.service}: {top.sample_message} "
            f"(seen {top.count} time(s) across {len(evidence)} service(s))."
        )
        return AnalyzerOutput(
            summary=summary,
            likely_cause=f"repeated failures in {top.service}",
        )
