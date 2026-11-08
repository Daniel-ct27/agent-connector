"""CLI entry point for Stage 7 benchmark runs."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from agent_connector.benchmarks.aggregate import write_charts, write_summary_csv
from agent_connector.benchmarks.fixtures import write_generated_fixtures
from agent_connector.benchmarks.runner import BenchmarkTransports, run_benchmark_matrix
from agent_connector.config import (
    BENCHMARK_CONCURRENCY_LEVELS,
    BENCHMARK_PAYLOAD_SIZES,
    BENCHMARK_TIMED_TRIALS,
    BENCHMARK_WARMUP_TRIALS,
    DEFAULT_BENCHMARK_RESULTS_DIR,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Stage 7 benchmark matrix against already-running local "
            "agent processes and write raw trials.csv under benchmarks/results/."
        )
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(DEFAULT_BENCHMARK_RESULTS_DIR),
        help="Directory that receives run_id/ subfolders",
    )
    parser.add_argument(
        "--generate-fixtures",
        action="store_true",
        help="Write scenarios/generated fixtures before running",
    )
    parser.add_argument(
        "--skip-grpc-unary",
        action="store_true",
        help="Skip grpc unary cells",
    )
    parser.add_argument(
        "--skip-http-unary",
        action="store_true",
        help="Skip http unary cells",
    )
    parser.add_argument(
        "--skip-grpc-stream",
        action="store_true",
        help="Skip grpc-stream TTFE cells",
    )
    parser.add_argument(
        "--payload-sizes",
        type=int,
        nargs="+",
        default=list(BENCHMARK_PAYLOAD_SIZES),
        help="Payload sizes to measure",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=list(BENCHMARK_CONCURRENCY_LEVELS),
        help="Concurrency levels to measure",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=BENCHMARK_WARMUP_TRIALS,
        help="Warm-up trials discarded per cell",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=BENCHMARK_TIMED_TRIALS,
        help="Timed trials recorded per cell",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Write summary.csv and charts after the timed matrix",
    )
    parser.add_argument(
        "--summary-only",
        type=Path,
        default=None,
        help="Only aggregate an existing trials.csv path (no timed run)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.summary_only is not None:
        if not args.summary_only.is_file():
            print(f"trials csv not found: {args.summary_only}", file=sys.stderr)
            return 2
        summary_path = write_summary_csv(args.summary_only)
        chart_paths = write_charts(summary_path)
        print(f"wrote {summary_path}")
        for path in chart_paths:
            print(f"wrote {path}")
        return 0

    if args.warmup < 0 or args.trials < 1:
        print("warmup must be >= 0 and trials must be >= 1", file=sys.stderr)
        return 2
    if any(size < 1 for size in args.payload_sizes):
        print("payload sizes must be >= 1", file=sys.stderr)
        return 2
    if any(level < 1 for level in args.concurrency):
        print("concurrency levels must be >= 1", file=sys.stderr)
        return 2

    if args.generate_fixtures:
        paths = write_generated_fixtures(sizes=tuple(args.payload_sizes))
        print(f"wrote {len(paths)} fixture(s) under scenarios/generated/")

    transports = BenchmarkTransports(
        grpc_unary=not args.skip_grpc_unary,
        http_unary=not args.skip_http_unary,
        grpc_stream=not args.skip_grpc_stream,
    )
    if not any((transports.grpc_unary, transports.http_unary, transports.grpc_stream)):
        print("at least one transport must be enabled", file=sys.stderr)
        return 2

    out_dir = asyncio.run(
        run_benchmark_matrix(
            results_dir=args.results_dir,
            transports=transports,
            payload_sizes=tuple(args.payload_sizes),
            concurrency_levels=tuple(args.concurrency),
            warmup_trials=args.warmup,
            timed_trials=args.trials,
        )
    )
    print(f"wrote benchmark results to {out_dir}")
    if args.summarize:
        summary_path = write_summary_csv(out_dir / "trials.csv")
        chart_paths = write_charts(summary_path)
        print(f"wrote {summary_path}")
        for path in chart_paths:
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
