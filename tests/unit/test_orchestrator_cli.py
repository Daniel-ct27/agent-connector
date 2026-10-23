"""Unit tests for orchestrator CLI validation helpers."""

from __future__ import annotations

from pathlib import Path

from agent_connector.orchestrator.cli import build_parser, main, resolve_jsonl_path


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scenarios"
    / "fixtures"
    / "inc-db-001.json"
)


def test_parser_accepts_empty_jsonl_string() -> None:
    args = build_parser().parse_args([str(FIXTURE), "--jsonl", ""])
    assert args.jsonl == ""


def test_resolve_jsonl_path_honors_no_jsonl_and_empty_string() -> None:
    assert resolve_jsonl_path(jsonl="logs/a.jsonl", no_jsonl=True) is None
    assert resolve_jsonl_path(jsonl="", no_jsonl=False) is None
    assert resolve_jsonl_path(jsonl="logs/a.jsonl", no_jsonl=False) == Path(
        "logs/a.jsonl"
    )


def test_main_rejects_non_positive_deadlines() -> None:
    assert main([str(FIXTURE), "--unary-deadline", "0", "--no-jsonl"]) == 2
    assert main([str(FIXTURE), "--stream-deadline", "-1", "--no-jsonl"]) == 2
