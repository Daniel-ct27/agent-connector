"""CLI entry point for incident orchestration workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from agent_connector.agentic import run_agentic
from agent_connector.config import (
    DEFAULT_ORCHESTRATOR_JSONL_PATH,
    DEFAULT_PLANNER,
    STREAM_DEADLINE_SECONDS,
    UNARY_DEADLINE_SECONDS,
)
from agent_connector.domain.models import AgenticStep, IncidentRequest, LogAnalysisEvent
from agent_connector.orchestrator.jsonl import normalize_jsonl_path
from agent_connector.orchestrator.orchestrate import AgentEndpoints, orchestrate
from agent_connector.orchestrator.orchestrate_unary import (
    HttpAgentEndpoints,
    orchestrate_unary,
)


def _print_stream_event(event: LogAnalysisEvent) -> None:
    evidence = ""
    if event.evidence is not None:
        evidence = f" [{event.evidence.service}: {event.evidence.summary}]"
    print(f"[stream] {event.type.value}: {event.message}{evidence}", flush=True)


def _print_agentic_step(step: AgenticStep) -> None:
    latency = (
        f" [{step.latency_ms:.1f} ms]"
        if step.latency_ms is not None
        else ""
    )
    print(
        f"[agentic] r{step.round} {step.phase}/{step.tool} "
        f"{step.status.value}{latency}: {step.detail}",
        flush=True,
    )
    if step.phase == "observe":
        for line in step.observation.splitlines()[:10]:
            print(f"          {line}", flush=True)
    elif step.decision and step.phase == "decide":
        print(f"          reason: {step.decision}", flush=True)


def _print_report(report) -> None:
    print()
    print("=== Incident Report ===")
    print(f"incident_id: {report.incident_id}")
    print(f"scenario:    {report.scenario}")
    print(f"partial:     {report.partial}")
    if report.agentic_mode:
        print(
            f"agentic:     {report.agentic_mode} "
            f"({len(report.agentic_steps)} steps)"
        )
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
            "Run a concurrent incident workflow. Default is the mixed gRPC "
            "stream demo; unary gRPC/HTTP paths support Stage 6 comparison."
        )
    )
    parser.add_argument(
        "fixture",
        type=Path,
        help="Path to an IncidentRequest JSON fixture",
    )
    parser.add_argument(
        "--transport",
        choices=("grpc-stream", "grpc-unary", "http-unary", "agentic"),
        default="grpc-stream",
        help=(
            "Workflow transport (default: grpc-stream). "
            "Use agentic for observe→decide→tool-call coordination."
        ),
    )
    parser.add_argument(
        "--planner",
        default=DEFAULT_PLANNER,
        help=(
            "Planner for --transport agentic: "
            "deterministic|openai|cloudflare|http"
        ),
    )
    parser.add_argument(
        "--severity-target",
        default=None,
        help="Severity target (gRPC host:port or HTTP base URL)",
    )
    parser.add_argument(
        "--runbook-target",
        default=None,
        help="Runbook target (gRPC host:port or HTTP base URL)",
    )
    parser.add_argument(
        "--log-analysis-target",
        default=None,
        help="Log Analysis target (gRPC host:port or HTTP base URL)",
    )
    parser.add_argument(
        "--jsonl",
        default=DEFAULT_ORCHESTRATOR_JSONL_PATH,
        help=(
            "Append structured JSONL logs here "
            "(empty string disables; --no-jsonl also disables)"
        ),
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
        help="Unary call deadline in seconds (must be > 0)",
    )
    parser.add_argument(
        "--stream-deadline",
        type=float,
        default=STREAM_DEADLINE_SECONDS,
        help="Log Analysis stream deadline in seconds (grpc-stream only)",
    )
    return parser


def resolve_jsonl_path(*, jsonl: str, no_jsonl: bool) -> Path | None:
    """Apply CLI flags to choose a JSONL destination or disable logging."""
    if no_jsonl:
        return None
    return normalize_jsonl_path(jsonl)


def _grpc_endpoints(args: argparse.Namespace) -> AgentEndpoints:
    defaults = AgentEndpoints()
    return AgentEndpoints(
        severity=args.severity_target or defaults.severity,
        runbook=args.runbook_target or defaults.runbook,
        log_analysis=args.log_analysis_target or defaults.log_analysis,
    )


def _http_endpoints(args: argparse.Namespace) -> HttpAgentEndpoints:
    defaults = HttpAgentEndpoints()
    return HttpAgentEndpoints(
        severity=args.severity_target or defaults.severity,
        runbook=args.runbook_target or defaults.runbook,
        log_analysis=args.log_analysis_target or defaults.log_analysis,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.fixture.is_file():
        print(f"fixture not found: {args.fixture}", file=sys.stderr)
        return 2

    if args.unary_deadline <= 0:
        print("deadlines must be greater than 0", file=sys.stderr)
        return 2
    if args.transport == "grpc-stream" and args.stream_deadline <= 0:
        print("deadlines must be greater than 0", file=sys.stderr)
        return 2

    request = IncidentRequest.model_validate(
        json.loads(args.fixture.read_text(encoding="utf-8"))
    )
    jsonl_path = resolve_jsonl_path(jsonl=args.jsonl, no_jsonl=args.no_jsonl)

    if args.transport == "agentic":
        report = run_agentic(
            request,
            planner=args.planner,
            on_step=_print_agentic_step,
        )
    elif args.transport == "grpc-stream":
        report = asyncio.run(
            orchestrate(
                request,
                endpoints=_grpc_endpoints(args),
                unary_deadline_s=args.unary_deadline,
                stream_deadline_s=args.stream_deadline,
                jsonl_path=jsonl_path,
                on_stream_event=_print_stream_event,
            )
        )
    elif args.transport == "grpc-unary":
        report = asyncio.run(
            orchestrate_unary(
                request,
                transport="grpc",
                grpc_endpoints=_grpc_endpoints(args),
                unary_deadline_s=args.unary_deadline,
                jsonl_path=jsonl_path,
            )
        )
    else:
        report = asyncio.run(
            orchestrate_unary(
                request,
                transport="http",
                http_endpoints=_http_endpoints(args),
                unary_deadline_s=args.unary_deadline,
                jsonl_path=jsonl_path,
            )
        )

    _print_report(report)
    return 1 if report.partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
