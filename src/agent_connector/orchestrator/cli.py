"""CLI entry point for the mixed gRPC incident workflow."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from agent_connector.config import (
    DEFAULT_ORCHESTRATOR_JSONL_PATH,
    STREAM_DEADLINE_SECONDS,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.domain.models import IncidentRequest, LogAnalysisEvent
from agent_connector.orchestrator.orchestrate import AgentEndpoints, orchestrate


def _print_stream_event(event: LogAnalysisEvent) -> None:
    evidence = ""
    if event.evidence is not None:
        evidence = f" [{event.evidence.service}: {event.evidence.summary}]"
    print(f"[stream] {event.type.value}: {event.message}{evidence}", flush=True)


def _print_report(report) -> None:
    print()
    print("=== Incident Report ===")
    print(f"incident_id: {report.incident_id}")
    print(f"scenario:    {report.scenario}")
    print(f"partial:     {report.partial}")
    print()
    print("Agent outcomes:")
    for outcome in report.agent_outcomes:
        latency = (
            f"{outcome.latency_ms:.1f} ms"
            if outcome.latency_ms is not None
            else "n/a"
        )
        detail = f" ({outcome.error_message})" if outcome.error_message else ""
        print(f"  - {outcome.name}: {outcome.status.value} [{latency}]{detail}")

    if report.severity is not None:
        print()
        print(
            f"Severity: {report.severity.level.value} "
            f"(score={report.severity.score})"
        )
        if report.severity.rationale:
            print(f"  rationale: {report.severity.rationale}")

    if report.runbook is not None:
        print()
        print(f"Runbook recommendations: {len(report.runbook.recommendations)}")
        for match in report.runbook.recommendations:
            print(
                f"  - {match.title} "
                f"(confidence={match.confidence:.2f}, id={match.runbook_id})"
            )

    if report.log_analysis is not None:
        print()
        print("Log analysis:")
        print(f"  summary:      {report.log_analysis.summary}")
        print(f"  likely_cause: {report.log_analysis.likely_cause}")
    elif report.log_analysis_events:
        print()
        print(
            f"Log analysis: incomplete "
            f"({len(report.log_analysis_events)} event(s) retained)"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the concurrent mixed gRPC incident workflow "
            "(Severity + Runbook + Log Analysis stream)."
        )
    )
    parser.add_argument(
        "fixture",
        type=Path,
        help="Path to an IncidentRequest JSON fixture",
    )
    parser.add_argument(
        "--severity-target",
        default=AgentEndpoints().severity,
        help="Severity gRPC target (host:port)",
    )
    parser.add_argument(
        "--runbook-target",
        default=AgentEndpoints().runbook,
        help="Runbook gRPC target (host:port)",
    )
    parser.add_argument(
        "--log-analysis-target",
        default=AgentEndpoints().log_analysis,
        help="Log Analysis gRPC target (host:port)",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=Path(DEFAULT_ORCHESTRATOR_JSONL_PATH),
        help="Append structured JSONL logs here (use empty string to disable)",
    )
    parser.add_argument(
        "--no-jsonl",
        action="store_true",
        help="Disable JSONL logging",
    )
    parser.add_argument(
        "--unary-deadline",
        type=float,
        default=UNARY_DEADLINE_SECONDS,
        help="Unary RPC deadline in seconds",
    )
    parser.add_argument(
        "--stream-deadline",
        type=float,
        default=STREAM_DEADLINE_SECONDS,
        help="Log Analysis stream deadline in seconds",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.fixture.is_file():
        print(f"fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    request = IncidentRequest.model_validate(
        json.loads(args.fixture.read_text(encoding="utf-8"))
    )
    endpoints = AgentEndpoints(
        severity=args.severity_target,
        runbook=args.runbook_target,
        log_analysis=args.log_analysis_target,
    )
    jsonl_path: Path | None
    if args.no_jsonl:
        jsonl_path = None
    else:
        jsonl_path = args.jsonl

    report = asyncio.run(
        orchestrate(
            request,
            endpoints=endpoints,
            unary_deadline_s=args.unary_deadline,
            stream_deadline_s=args.stream_deadline,
            jsonl_path=jsonl_path,
            on_stream_event=_print_stream_event,
        )
    )
    _print_report(report)
    return 1 if report.partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
